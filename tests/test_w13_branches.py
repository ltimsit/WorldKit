"""J5 : branches, redéfinition ponctuelle, transposition, déplacement de propositions.

Parcours W13 (hors transposition de scénario, J6) ; R-HIS-02 à R-HIS-05, R-MON-04, R-VUE-03, T-BRA-01,
T-ING-16 ; cadre de fondation §6.3.
"""

from __future__ import annotations

import json

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from support import VALMONT, attr, base_world, create, edit, read_yaml, rel, unrel
from worldkit.core.journal.models import EditStatus, parse_edit
from worldkit.core.projection.serialize import state_to_dict, state_to_json
from worldkit.core.views import Filter, View
from worldkit.ingest import decide
from worldkit.ingest.batch import batch_documents, ingest
from worldkit.ingest.queue import load, load_one
from worldkit.periphery.extraction import OracleExtractor

VAR = "variante-mj"


def e201():
    steps = read_yaml(VALMONT / "walkthroughs" / "walkthroughs.yaml")["walkthroughs"]
    w13 = next(w for w in steps if w["id"] == "W13")
    return parse_edit(next(s["edit"] for s in w13["steps"] if s.get("do") == "apply_edit"))


@pytest.fixture
def world():
    w = base_world()
    w.create_branch(VAR, point="@base")
    yield w
    w.close()


def council_edits():
    return (edit(*create("conseil", "Faction", "le conseil des marchands"), id="e150"),
            edit(unrel("odon", "rules", "brume"), rel("conseil", "rules", "brume", visibility="public"),
                 {"op": "unset_attribute", "entity": "odon", "attribute": "title"}, id="e151"))


# --- W13 : variante et redéfinition ponctuelle ---

def test_w13_variant_starts_from_base_and_reference_is_untouched(world):
    reference_before = state_to_json(world.state())
    assert world.store.head_seq(VAR) == world.resolve_point("@base")
    assert world.apply(e201()).status == EditStatus.APPLIED
    assert world.state(VAR).occupancy[("rel_to", "rules", "brume")] == ("rel", "mervin", "rules", "brume")
    assert world.state().occupancy[("rel_to", "rules", "brume")] == ("rel", "odon", "rules", "brume")
    assert state_to_json(world.state()) == reference_before


def test_w13_earlier_view_of_the_variant_says_redefined_later_R_VUE_03(world):
    world.apply(e201())
    base = world.resolve_point("@base", VAR)
    past = View(world.state(VAR, base), Filter.AUTHOR, redefined=world.redefined_after(VAR, base))
    rules = [r for r in past.page("brume").relations if r.relation == "rules"]
    assert [(r.other, r.redefined_later) for r in rules] == [("odon", True)]
    now = View(world.state(VAR), Filter.AUTHOR, redefined=world.redefined_after(VAR, world.state(VAR).seq))
    assert not any(r.redefined_later for r in now.page("brume").relations)
    reference = View(world.state(point="@base"), Filter.AUTHOR, redefined=world.redefined_after(None, base))
    assert not any(r.redefined_later for r in reference.page("brume").relations)


def test_variant_edits_continue_the_ranks_after_the_fork(world):
    outcome = world.apply(e201())
    assert outcome.seq == world.resolve_point("@base") + 1
    assert [e.id for _, e in world.store.journal(VAR)][-2:] == ["e006", "e201"]


def test_branch_of_a_branch_reads_its_whole_lineage(world):
    world.apply(e201())
    world.create_branch("sous-variante", VAR)
    world.apply(edit(attr("isabeau", "condition", "en exil"), id="e300", branch="sous-variante"))
    state = world.state("sous-variante")
    assert state.occupancy[("rel_to", "rules", "brume")] == ("rel", "mervin", "rules", "brume")
    assert state.facts[("attr", "isabeau", "condition")].value == "en exil"
    assert ("attr", "isabeau", "condition") not in world.state(VAR).facts


def test_branch_names_are_unique(world):
    with pytest.raises(ValueError):
        world.create_branch(VAR)


# --- Transposition (§6.3) ---

def test_independent_edit_is_transposed_automatically(world):
    world.apply(edit(attr("isabeau", "condition", "en exil"), id="e152"))
    outcome, analysis = world.transpose("e152", VAR)
    assert analysis.relation == "independent" and outcome.status == EditStatus.APPLIED
    applied = world.store.edit("e152@variante-mj").edit
    assert applied.transposed_from == "e152" and applied.branch == VAR
    assert world.state(VAR).facts[("attr", "isabeau", "condition")].value == "en exil"


def test_missing_dependency_blocks_even_keep(world):
    create_council, take_brume = council_edits()
    world.apply(create_council)
    world.apply(take_brume)
    outcome, analysis = world.transpose("e151", VAR)
    assert analysis.relation == "dependent" and outcome.status is None
    assert ("entity", "conseil") in {d.key for d in analysis.missing}
    outcome, _ = world.transpose("e151", VAR, "keep")
    assert outcome.status is None and "conseil" not in world.state(VAR).entities


def test_contradiction_needs_a_human_decision_then_keep_removes_the_occupant(world):
    world.apply(e201())
    create_council, take_brume = council_edits()
    world.apply(create_council)
    world.apply(take_brume)
    assert world.transpose("e150", VAR)[0].status == EditStatus.APPLIED
    outcome, analysis = world.transpose("e151", VAR)
    assert analysis.relation == "contradictory" and outcome.status is None
    assert [d.found for d in analysis.contradictions if d.key == ("rel_to", "rules", "brume")] == \
        [("rel", "mervin", "rules", "brume")]
    kept, _ = world.transpose("e151", VAR, "keep")
    assert kept.status == EditStatus.APPLIED
    changes = world.store.edit("e151@variante-mj").edit.changes
    assert changes[0].op == "remove_relation" and changes[0].from_ == "mervin"
    assert world.state(VAR).occupancy[("rel_to", "rules", "brume")] == ("rel", "conseil", "rules", "brume")


def test_discard_and_adapt_are_traced(world):
    world.apply(e201())
    create_council, take_brume = council_edits()
    world.apply(create_council)
    world.apply(take_brume)
    world.transpose("e150", VAR)
    assert world.transpose("e151", VAR, "discard", reason="Mervin garde Brume")[0].status == EditStatus.ABANDONED
    from worldkit.core.schema import parse_change
    adapted, _ = world.transpose("e151", VAR, "adapt", [parse_change(
        {"op": "set_attribute", "entity": "odon", "attribute": "condition", "value": "déchu"})])
    assert adapted.status == EditStatus.APPLIED
    actions = [a for (a,) in world.store.conn.execute("SELECT action FROM transpositions ORDER BY 1")]
    assert actions == ["adapt", "auto", "discard"]


def test_transposition_never_modifies_the_source_nor_earlier_states_R_HIS_04(world):
    world.apply(edit(attr("isabeau", "condition", "en exil"), id="e152"))
    reference, past = state_to_json(world.state()), state_to_json(world.state(VAR, world.resolve_point("@base")))
    world.transpose("e152", VAR)
    assert state_to_json(world.state()) == reference
    assert state_to_json(world.state(VAR, world.resolve_point("@base", VAR))) == past


def _without_provenance(state):
    d = state_to_dict(state)
    for f in d["facts"]:
        f["established_by"] = ""
    for e in d["entities"]:
        e["established_by"], e["created_seq"] = "", 0
    d["seq"] = 0
    return json.dumps(d, sort_keys=True, default=str)


CHARACTERS = ["isabeau", "corvin", "mervin", "odon"]


@settings(max_examples=15, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(st.permutations(CHARACTERS), st.text(alphabet="abcde", min_size=1, max_size=5))
def test_independent_transpositions_commute(order, value):
    a, b = order[0], order[1]
    results = []
    for first, second in ((a, b), (b, a)):
        w = base_world()
        w.create_branch(VAR, point="@base")
        w.apply(edit(attr(a, "condition", value), id="ta"))
        w.apply(edit(attr(b, "condition", value + "!"), id="tb"))
        ids = {a: "ta", b: "tb"}
        for character in (first, second):
            assert w.transpose(ids[character], VAR)[0].status == EditStatus.APPLIED
        results.append(_without_provenance(w.state(VAR)))
        w.close()
    assert results[0] == results[1]


# --- Déplacer une proposition (T-ING-16) ---

def test_moving_a_proposal_requalifies_it_on_the_target(world):
    world.apply(e201())
    ingest(world, "b1", batch_documents(VALMONT / "docs" / "batches.yaml", "b1"), OracleExtractor(VALMONT / "gold"))
    result = decide.move(world, "b1.notes-baron.p7.1", VAR)
    assert result.ok and result.edit_id == "b1.notes-baron.p7.1@variante-mj"
    assert load_one(world, "b1.notes-baron.p7.1").closed_reason == "moved:b1.notes-baron.p7.1@variante-mj"
    moved = load(world, VAR)
    assert [p.id for p in moved] == ["b1.notes-baron.p7.1@variante-mj"]
    assert decide.accept(world, moved[0].id).ok
    assert world.state(VAR).facts[("attr", "odon", "title")].value == "régent"
    assert world.state().facts[("attr", "odon", "title")].value == "baron"


def test_cli_branch_and_transpose(tmp_path, capsys):
    from worldkit.cli import main
    db = str(tmp_path / "v.db")
    run = lambda *a: main(["--db", db, *a])  # noqa: E731
    run("world", "init", str(VALMONT / "world.yaml"))
    run("edit", "apply", str(VALMONT / "edits" / "base.yaml"))
    assert run("branch", "create", VAR) == 0
    change = tmp_path / "e152.yaml"
    change.write_text("id: e152\norigin: enrichment\nchanges:\n"
                      "  - { op: set_attribute, entity: isabeau, attribute: condition, value: exil }\n", "utf-8")
    assert run("edit", "apply", str(change)) == 0
    assert run("edit", "transpose", "e152", "--to", VAR) == 0
    assert run("branch", "list") == 0
    out = capsys.readouterr().out
    assert "indépendante" in out and "variante-mj : depuis reference au rang 7" in out
