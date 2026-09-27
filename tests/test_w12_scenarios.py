"""J6 : pistes, scénarios, déroulés — parcours W12, fin de W13, W17.

R-SCN-01 à R-SCN-09, R-CYC-03, R-EDI-08, R-MET-05, R-VUE-02, R-NOT-04, R-NOT-07, R-HIS-06.
"""

from __future__ import annotations

import sqlite3

import pytest

from support import VALMONT
from test_w10_w11 import after_w05
from worldkit.core.journal.models import EditStatus
from worldkit.core.schema import IssueCode
from worldkit.core.views import Filter, View, state_report
from worldkit.core.workflows import scenarios as S

SCN = VALMONT / "scenarios"


def setup_world():
    """@after-b4 des parcours, réduit à ce que les scénarios supposent : conseil, taverne, fiche A du Loup."""
    w = after_w05()
    w.set_point("after-b4")
    S.load_scenario(w, SCN / "eveil-du-loup.yaml")
    S.load_scenario(w, SCN / "siege-de-brume.yaml")
    S.load_author_drafts(w, SCN / "author-drafts.yaml")
    return w


def play_fixture(w, playthrough, branch=None, **overrides):
    scenario, version, fixture_branch, confirmations, free = S.load_playthrough(SCN / "playthroughs.yaml", playthrough)
    return S.play(w, overrides.get("id", playthrough), scenario, overrides.get("version", version),
                  overrides.get("confirmations", confirmations), overrides.get("free", free), branch or fixture_branch)


@pytest.fixture
def world():
    w = setup_world()
    yield w
    w.close()


# --- W12 ---

def test_w12_open_drafts_on_odon_before_the_siege_R_VUE_02(world):
    page = View(world.state(), Filter.AUTHOR, drafts=S.open_drafts(world)).page("odon")
    ids = sorted(d.split(" — ")[0] for d in page.drafts)
    assert ids == ["ad-1", "x-d1", "x-d2", "x-d3"]
    mervin = View(world.state(), Filter.AUTHOR, drafts=S.open_drafts(world)).page("mervin")
    assert any(d.startswith("ad-2") for d in mervin.drafts)
    assert View(world.state(), Filter.PLAYER, drafts=S.open_drafts(world)).page("odon").drafts == []


def test_w12_alternatives_coexist_without_contradiction_R_CYC_03(world):
    sv = S.scenario_version(world, "siege-de-brume", 1)
    assert sv.drafts["x-d1"].alternatives == ("x-d2",) and sv.drafts["x-d2"].alternatives == ("x-d1",)
    assert not [i for i in state_report(world.state()) if i.severity == "error"]


def test_w12_pt1_one_edit_touches_lore_and_sheet_R_MET_05(world):
    report = play_fixture(world, "pt-1")
    assert [(i.draft, i.outcome) for i in report.items] == [("y-d1", "applied")]
    edit = world.store.edit("pt-1.y-d1").edit
    assert edit.origin == "scenario_consequence" and {c.entity for c in edit.changes} >= \
        {"coeur-de-braise", "loup-de-cendre", "loup-de-cendre@system-a"}
    state = world.state()
    assert state.entities["coeur-de-braise"].closed and state.facts[("attr", "loup-de-cendre@system-a", "hp")].value == 8


def test_w12_pt2_dependency_satisfied_adaptation_and_free_edit_R_SCN_06(world):
    play_fixture(world, "pt-1")
    report = play_fixture(world, "pt-2")
    assert report.warnings == []  # « X suppose Y » satisfaite
    assert [(i.draft, i.adapted, i.outcome) for i in report.items] == \
        [("x-d1", True, "applied"), ("x-d3", False, "applied"), (None, False, "applied")]
    state = world.state()
    assert state.occupancy[("rel_to", "rules", "brume")] == ("rel", "conseil-marchands", "rules", "brume")
    assert ("attr", "odon", "title") not in state.facts
    assert state.facts[("attr", "odon", "condition")].value == "rescapé du siège, mais a perdu un bras"
    assert state.entities["taverne-du-heron"].closed
    x_d1 = S.scenario_version(world, "siege-de-brume", 1).drafts["x-d1"]
    assert x_d1.changes[0].value == "rescapé du siège"  # la piste reste intacte (R-EDI-08)
    assert any(d.startswith("x-d1") for d in S.open_drafts(world)["odon"])


def test_w12_player_does_not_see_the_council_ruling_R_NOT_04_R_NOT_07(world):
    play_fixture(world, "pt-1")
    play_fixture(world, "pt-2")
    state = world.state()
    assert not any(r.relation == "rules" for r in View(state, Filter.PLAYER).page("brume").relations)
    assert any(i.code == IssueCode.MASKED_PUBLIC_FACT and "conseil" in i.message for i in state_report(state))


def test_w12_adopting_an_author_draft(world):
    outcome = S.adopt(world, "ad-1")
    assert outcome.status == EditStatus.APPLIED
    assert world.store.edit("ad-1").edit.origin == "adopted_draft"
    assert ("rel", "isabeau", "sibling_of", "odon") in world.state().facts


def test_playthrough_ids_are_unique_and_versions_frozen(world):
    play_fixture(world, "pt-1")
    with pytest.raises(ValueError):
        play_fixture(world, "pt-1")
    with pytest.raises(sqlite3.DatabaseError):
        world.store.conn.execute("UPDATE scenario_versions SET changelog = 'x'")
    changed = SCN / "eveil-du-loup.yaml"
    text = changed.read_text(encoding="utf-8").replace("value: 8", "value: 9")
    tmp = changed.parent / "_tmp_eveil.yaml"
    try:
        tmp.write_text(text, encoding="utf-8")
        with pytest.raises(ValueError):
            S.load_scenario(world, tmp)  # R-SCN-04 : v1 déjà enregistrée, différente
    finally:
        tmp.unlink()


# --- Fin de W13 : transposer le siège vers la variante ---

def test_w13_scenario_transposed_to_the_variant(world):
    world.create_branch("variante-mj", point="base")
    from test_w13_branches import e201
    world.apply(e201())
    confirmations = [S.Confirmation("x-d1"), S.Confirmation("x-d3")]
    report = play_fixture(world, "pt-2", "variante-mj", id="pt-2-variante", version=2,
                          confirmations=confirmations, free=[])
    assert any(i.code == IssueCode.SCENARIO_DEPENDENCY for i in report.warnings)  # Y non jouée : signalé
    items = {i.draft: i for i in report.items}
    assert items["x-d1"].outcome == "applied"  # v2 : exil, indépendante
    assert items["x-d3"].outcome == "conflict"
    missing = {d.key for d in items["x-d3"].analysis.missing}
    different = {d.key: d.found for d in items["x-d3"].analysis.contradictions}
    assert ("entity", "conseil-marchands") in missing
    assert different[("rel_to", "rules", "brume")] == ("rel", "mervin", "rules", "brume")
    assert world.state("variante-mj").facts[("attr", "odon", "condition")].value == "exilé à Hautval"
    assert world.state().occupancy[("rel_to", "rules", "brume")] == ("rel", "odon", "rules", "brume")  # référence intacte


# --- W17 : changer l'ordre des scénarios ---

def test_w17_reverse_order_signals_then_converges_R_HIS_06(world):
    world.create_branch("ordre-inverse", point="after-b4")
    first = play_fixture(world, "pt-2", "ordre-inverse", id="pt-2-inv")
    assert any(i.code == IssueCode.SCENARIO_DEPENDENCY for i in first.warnings)
    assert all(i.outcome == "applied" for i in first.items)
    play_fixture(world, "pt-1", "ordre-inverse", id="pt-1-inv")
    play_fixture(world, "pt-1")
    play_fixture(world, "pt-2")
    a, b = world.state(), world.state("ordre-inverse")
    touched = [("rel_to", "rules", "brume"), ("attr", "odon", "condition"), ("attr", "loup-de-cendre", "flame_bearer"),
               ("attr", "loup-de-cendre@system-a", "hp")]
    for key in touched:
        fa, fb = a.facts.get(a.occupancy.get(key)), b.facts.get(b.occupancy.get(key))
        assert (fa.value if fa else None, fa.target if fa else None) == (fb.value if fb else None, fb.target if fb else None)
    for entity in ("coeur-de-braise", "taverne-du-heron"):
        assert a.entities[entity].closed == b.entities[entity].closed


def test_cli_scenario_play_with_conflict_decisions(tmp_path, capsys):
    from worldkit.cli import main
    w = setup_world()
    db = tmp_path / "w.db"
    backup = __import__("sqlite3").connect(db)
    w.store.conn.backup(backup)
    backup.close()
    w.close()
    run = lambda *a: main(["--db", str(db), *a])  # noqa: E731
    assert run("scenario", "list") == 0
    assert run("branch", "create", "variante-mj", "--at", "base") == 0
    assert run("scenario", "play", "siege-de-brume", "--version", "2", "--draft", "x-d1", "--draft", "x-d3",
               "--branch", "variante-mj", "--id", "essai") == 1
    out = capsys.readouterr().out
    assert "EN CONFLIT" in out and "suppose eveil-du-loup" in out
    assert run("scenario", "play", "pt-1", "--file", str(SCN / "playthroughs.yaml")) == 0
    assert run("draft", "list") == 0 and "ad-1" in capsys.readouterr().out
