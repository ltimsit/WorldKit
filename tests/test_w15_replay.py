"""J7 : redéfinition rétroactive et rejeu — parcours W15 (« Aldren est mort de fièvre »).

R-RED-01 à R-RED-05, R-HIS-01, R-HIS-03, R-HIS-04, R-MON-02, T-ING-12, T-ING-16 ; cadre de fondation §6.4.
"""

from __future__ import annotations

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from support import VALMONT, attr, base_world, edit, read_yaml
from test_w06_w07 import docs
from test_w10_w11 import ORACLE, after_w05
from worldkit.core.conflicts import check_application
from worldkit.core.journal.models import EditStatus
from worldkit.core.projection.serialize import state_to_json
from worldkit.core.schema import IssueCode, parse_change
from worldkit.core.world import World
from worldkit.core.workflows import replay as R
from worldkit.core.workflows import scenarios as S
from worldkit.ingest import decide
from worldkit.ingest.batch import ingest
from worldkit.ingest.queue import load

SCN = VALMONT / "scenarios"
NEW = "reference-r1"
QUALIFICATION = "b2.chronique-de-la-chute-extraits.p1.1.d"  # « mort au combat : fausse » (W06)
DEATH = ("attr", "aldren-ii", "death_cause")


def w15_changes():
    steps = read_yaml(VALMONT / "walkthroughs" / "walkthroughs.yaml")["walkthroughs"]
    w15 = next(w for w in steps if w["id"] == "W15")
    return [parse_change(c) for c in w15["steps"][0]["changes"]]


def setup_w15(world: World | None = None) -> World:
    """Référence : W05, @after-b4, pistes d'auteur, W06 (Chronique qualifiée), pt-1 joué ; variante-mj à @base."""
    w = world or after_w05()
    w.set_point("after-b4")
    S.load_scenario(w, SCN / "eveil-du-loup.yaml")
    S.load_scenario(w, SCN / "siege-de-brume.yaml")
    S.load_author_drafts(w, SCN / "author-drafts.yaml")
    ingest(w, "b2", docs("b2"), ORACLE)
    claims = {p.changes[0].change.text: p.id for p in load(w) if p.kind == "claim"}
    assert decide.qualify(w, claims["Aldren est mort en combattant les pillards de Cendrelande."], "false").ok
    w.create_branch("variante-mj", point="@base")
    scenario, version, _, confirmations, free = S.load_playthrough(SCN / "playthroughs.yaml", "pt-1")
    S.play(w, "pt-1", scenario, version, confirmations, free)
    w.set_point("after-siege")
    return w


def snapshot(w: World, branch: str) -> list[str]:
    """Chaque état de la branche, rang par rang (R-HIS-04)."""
    return [state_to_json(w.state(branch, s)) for s in range(w.store.head_seq(branch) + 1)]


@pytest.fixture(scope="module")
def replayed():
    w = setup_w15()
    before = {"reference": snapshot(w, "reference"), "variante-mj": snapshot(w, "variante-mj")}
    impact = R.preview(w, w15_changes(), "e003")
    first = R.start(w, w15_changes(), "e003")
    kept = R.decide(w, first.replay.id, "keep")
    yield w, before, impact, first, kept
    w.close()


# --- Aperçu d'impact (R-RED-01) ---

def test_w15_impact_preview_counts_the_w06_qualification_R_RED_01(replayed):
    _, _, impact, _, _ = replayed
    assert impact.applicable and impact.anchor_seq == 4
    assert [t.edit_id for t in impact.edits] == [QUALIFICATION]
    assert impact.edits[0].keys == (DEATH,)
    assert impact.later > len(impact.edits)


def test_w15_impact_preview_names_ad2_not_ad1_R_RED_03(replayed):
    _, _, impact, _, _ = replayed
    assert [t.edit_id for t in impact.pending] == ["ad-2"]


def test_preview_writes_nothing():
    w = setup_w15()
    before = (w.store.branches(), snapshot(w, "reference"))
    R.preview(w, w15_changes(), "e003")
    assert (w.store.branches(), snapshot(w, "reference")) == before
    w.close()


# --- Rejeu (§6.4, R-HIS-05) ---

def test_w15_replay_stops_only_on_the_w06_qualification(replayed):
    _, _, _, first, _ = replayed
    assert first.current == QUALIFICATION and first.conflict is not None
    assert [(d.key, d.kind, d.written) for d in first.conflict.divergences] == [(DEATH, "different", False)]
    assert first.replayed and all(s.action == "auto" for s in first.replayed)


def test_w15_keeping_the_qualification_keeps_fever_and_combat_stays_false(replayed):
    w, _, _, _, kept = replayed
    assert kept.ok and kept.conflict is None and kept.replay.status == R.FINISHED
    state = w.state(NEW)
    assert state.facts[DEATH].value == "fièvre"
    claim = w.store.edit(f"{QUALIFICATION}@{NEW}").edit.changes[-1]
    assert (claim.op, claim.value) == ("qualify_claim", "false")
    assert state.qualifications[claim.claim]["value"] == "false"
    assert [s.action for s in R.steps(w, "r1") if s.action != "auto"] == ["keep"]


def test_w15_earlier_views_of_the_new_branch_reflect_the_redefinition(replayed):
    w, _, _, _, _ = replayed
    red = w.store.locate("r1.redefinition")[1]
    assert w.state(NEW, 4).facts[DEATH].value == "poison"  # l'ancrage lui-même précède la redéfinition
    for point in (red, "@base", "@after-b1", "@after-b4", "head"):
        state = w.state(NEW, point)
        assert state.facts[DEATH].value == "fièvre"
        assert not any(f[0] == "rel" and f[2] == "killed" for f in state.facts)


# --- Finalisation (R-MON-02, R-HIS-04, R-RED-03, R-RED-04) ---

def test_w15_new_branch_becomes_reference_old_one_archived_and_readable(replayed):
    w, before, _, _, _ = replayed
    assert w.reference_branch == NEW
    assert [(b, r) for _, b, r in w.store.reference_history()] == [(NEW, "r1")]
    assert w.store.branch_status("reference") == "archived"
    assert snapshot(w, "reference") == before["reference"]  # T1 : ancienne branche identique, rang par rang
    refused = w.apply(edit(attr("odon", "condition", "las"), id="t-archived", branch="reference"))
    assert not refused.ok and refused.issues[0].rule == "R-HIS-04"


def test_w15_ad2_to_recheck_ad1_not_concerned_R_RED_03(replayed):
    w, _, _, _, _ = replayed
    ad1, ad2 = w.store.edit(f"ad-1@{NEW}"), w.store.edit(f"ad-2@{NEW}")
    assert (ad1.status, ad2.status) == (EditStatus.PENDING, EditStatus.PENDING)
    assert ad2.needs_recheck and not ad1.needs_recheck
    assert w.store.edit("ad-2").status is EditStatus.ABANDONED
    assert S.open_drafts(w)["aldren-ii"] and all("@" in d for d in S.open_drafts(w)["aldren-ii"] if "piste d'auteur" in d)


def test_w15_named_points_and_playthroughs_are_carried(replayed):
    w, _, _, _, _ = replayed
    assert set(w.store.named_points(NEW)) == {"@base", "@after-b1", "@after-b4", "@after-siege"}
    assert w.resolve_point("@base", NEW) == w.resolve_point("@base", "reference") + 1
    assert w.resolve_point("@after-siege", NEW) == w.store.head_seq(NEW)
    assert S.played_on(w, NEW) == S.played_on(w, "reference") == {"eveil-du-loup"}
    row = w.store.conn.execute("SELECT branch_id FROM playthroughs WHERE playthrough_id = ?", (f"pt-1@{NEW}",))
    assert row.fetchone() == (NEW,)


def test_w15_pending_proposals_moved_with_decision_memory_T_ING_16(replayed):
    w, _, _, _, _ = replayed
    assert load(w, "reference") == []
    moved = load(w, NEW)
    assert moved and all(p.id.endswith(f"@{NEW}") for p in moved)
    n = lambda b: w.store.conn.execute("SELECT COUNT(*) FROM decisions WHERE branch_id = ?", (b,)).fetchone()[0]
    assert n(NEW) >= n("reference") > 0


def test_w15_variant_is_notified_not_modified_R_RED_04(replayed):
    w, before, _, _, _ = replayed
    assert snapshot(w, "variante-mj") == before["variante-mj"]
    assert w.store.branch_status("variante-mj") == "active"
    notices = R.lineage_notices(w, "variante-mj")
    assert [(i.code, i.rule) for i in notices] == [(IssueCode.ARCHIVED_BRANCH, "R-RED-04")]
    assert NEW in notices[0].message and "d'avant la redéfinition" in notices[0].message
    assert R.lineage_notices(w, NEW) == []
    assert [i.rule for i in R.lineage_notices(w, "reference")] == ["R-HIS-04"]


# --- Propriétés T1 ---

def test_replay_is_deterministic_T1():
    results = []
    for _ in range(2):
        w = setup_w15()
        report = R.start(w, w15_changes(), "e003")
        R.decide(w, report.replay.id, "keep")
        results.append(([e for _, e in w.store.journal_ids(NEW)], state_to_json(w.state(NEW)),
                         w.store.named_points(NEW)))
        w.close()
    assert results[0] == results[1]


CHARACTERS = ["isabeau", "corvin", "odon"]


@settings(max_examples=10, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(st.lists(st.tuples(st.sampled_from(CHARACTERS), st.text(alphabet="abcde", min_size=1, max_size=4)),
                min_size=1, max_size=5))
def test_independent_edits_replay_without_intervention_T1(later):
    """Une redéfinition sur une clé que rien ne lit : tout est rejoué seul, dans l'ordre, et la tête de la
    nouvelle branche = redéfinition + mêmes faits."""
    w = base_world()
    for i, (who, value) in enumerate(later):
        assert w.apply(edit(attr(who, "condition", value), id=f"h{i}")).ok
    report = R.start(w, [parse_change(attr("mervin", "condition", "fiévreux"))], "e003")
    assert report.ok and report.conflict is None and report.replay.status == R.FINISHED
    assert [s.action for s in R.steps(w, "r1")] == ["auto"] * (len(later) + 3)  # e004–e006, puis h*
    old, new = w.state("reference"), w.state(NEW)
    for who in CHARACTERS:
        key = ("attr", who, "condition")
        assert (old.facts.get(key) and old.facts[key].value) == (new.facts.get(key) and new.facts[key].value)
    assert new.facts[("attr", "mervin", "condition")].value == "fiévreux"
    w.close()


# --- Suspendre, reprendre, abandonner (R-RED-02) ---

def test_replay_suspends_and_resumes_after_reopening_the_world_R_RED_02(tmp_path):
    db = tmp_path / "valmont.db"
    w = World.create(db, VALMONT / "world.yaml")
    base = base_world()
    for _, e in base.store.journal("reference")[1:]:
        assert w.apply(e).ok
    base.close()
    w.set_point("@base")
    setup_w15(w)
    report = R.start(w, w15_changes(), "e003", limit=2)
    assert len(report.replayed) == 2 and report.conflict is None and report.replay.status == R.OPEN
    w.close()

    w = World.open(db)
    assert w.reference_branch == "reference"  # rien ne bascule avant la fin
    status = R.pending_conflict(w, "r1")
    assert status.current is not None and status.conflict is None
    report = R.advance(w, "r1")
    assert report.current == QUALIFICATION
    w.close()

    w = World.open(db)
    assert R.pending_conflict(w, "r1").conflict is not None
    report = R.decide(w, "r1", "keep")
    assert report.replay.status == R.FINISHED and w.reference_branch == NEW
    w.close()


def test_abandoning_a_replay_keeps_everything_traced_R_RED_02_R_HIS_01():
    w = setup_w15()
    before = snapshot(w, "reference")
    report = R.start(w, w15_changes(), "e003")
    assert report.current == QUALIFICATION
    assert R.abandon(w, "r1").replay.status == R.ABANDONED
    assert w.reference_branch == "reference" and w.store.branch_status("reference") == "active"
    assert w.store.branch_status(NEW) == "abandoned" and w.store.head_seq(NEW) > 4  # rien n'est retiré
    assert snapshot(w, "reference") == before
    assert not R.decide(w, "r1", "keep").ok
    assert not w.apply(edit(attr("odon", "condition", "las"), id="t-abandoned", branch=NEW)).ok
    # un nouveau rejeu reste possible depuis la même source
    again = R.start(w, w15_changes(), "e003")
    assert again.replay.id == "r2" and again.replay.branch == "reference-r2"
    w.close()


def test_discarding_an_edit_then_a_dependent_one_stops_R_HIS_05():
    """Écarter une édition : celles qui en dépendent deviennent des dépendances absentes (§6.3)."""
    w = base_world()
    assert w.apply(edit(attr("odon", "condition", "blessé"), id="h1")).ok
    assert w.apply(edit(attr("odon", "condition", "guéri"), id="h2")).ok
    report = R.start(w, [parse_change(attr("odon", "condition", "mort"))], "e006")
    assert report.current == "h1" and report.conflict.relation == "contradictory"
    report = R.decide(w, "r1", "discard", reason="Odon meurt à la place")
    assert report.current == "h2"
    report = R.decide(w, "r1", "adapt", [parse_change(attr("odon", "condition", "enterré"))])
    assert report.replay.status == R.FINISHED
    assert w.state().facts[("attr", "odon", "condition")].value == "enterré"
    assert [(s.source_edit, s.action, s.result_edit) for s in R.steps(w, "r1")] == [
        ("h1", "discard", None), ("h2", "adapt", f"h2@{NEW}")]
    w.close()


def test_retroactive_schema_change_uses_the_same_replay_R_RED_05():
    w = base_world()
    assert w.apply(edit(attr("odon", "condition", "las"), id="h1")).ok
    change = parse_change({"op": "schema_set_type", "type": "Character", "attribute": "epithet",
                           "definition": {"type": "text"}})
    report = R.start(w, [change], "e003")
    assert report.replay.status == R.FINISHED
    epithet = [parse_change(attr("odon", "epithet", "le Gris"))]
    assert check_application(epithet, w.state(NEW, "@base"), "x").applicable
    assert not check_application(epithet, w.state("reference", "@base"), "x").applicable
    w.close()


def test_refusals():
    w = setup_w15()
    bad = R.start(w, [parse_change(attr("nobody", "condition", "x"))], "e003")
    assert not bad.ok and w.store.branches() == ["reference", "variante-mj"]
    R.start(w, w15_changes(), "e003")
    assert not R.start(w, w15_changes(), "e003").ok  # un seul rejeu ouvert par source
    assert not R.decide(w, "r1", "adapt").ok
    w.close()
