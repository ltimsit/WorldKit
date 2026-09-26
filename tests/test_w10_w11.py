"""Parcours W10 (ré-ingestion de notes-baron v2) et W11 (mode edit en diff, abandonné) — J3.4.

R-DOC-04, R-PRI-04, R-FAI-01, R-FAI-06, R-ING-01, R-PRI-01, R-CYC-02, R-CYC-04, T-ING-08 à T-ING-11.
"""

from __future__ import annotations

import pytest

from support import VALMONT, base_world, edit
from worldkit.core.journal.models import EditStatus
from worldkit.core.schema import IssueCode
from worldkit.ingest import decide
from worldkit.ingest.batch import batch_documents, ingest
from worldkit.ingest.queue import load, load_one
from worldkit.ingest.review import orphan_facts
from worldkit.periphery.extraction import OracleExtractor

ORACLE = OracleExtractor(VALMONT / "gold")


def docs(batch):
    return batch_documents(VALMONT / "docs" / "batches.yaml", batch)


def after_w05():
    """État @after-b1 des parcours : b1 et b5 ingérés, e101 appliquée, revue W05 faite."""
    w = base_world()
    ingest(w, "b1", docs("b1"), ORACLE)
    ingest(w, "b5", docs("b5"), ORACLE)
    w.apply(edit({"op": "add_value", "entity": "brume", "attribute": "aliases", "value": "Brume-sur-Mer",
                  "visibility": "public"}, id="e101"))
    steps = [decide.accept(w, "b1.notes-baron.p3.1", keep=[0, 1]), decide.accept(w, "b1.notes-baron.p4.1"),
             *decide.choose(w, "b1.notes-baron.p4.2"), decide.accept(w, "b1.notes-baron.p5.1"),
             decide.accept(w, "b1.notes-baron.p5.2"), decide.refuse(w, "b1.notes-baron.p7.1"),
             decide.refuse(w, "b5.notes-conseil.p2.1", [1]), decide.accept(w, "b1.lieux-de-valmont.p3.1"),
             decide.refuse(w, "b1.lieux-de-valmont.p3.2"), decide.accept(w, "b1.lieux-de-valmont.p4.1")]
    assert all(s.ok for s in steps)
    w.set_point("@after-b1")
    return w


@pytest.fixture
def w10():
    w = after_w05()
    report = ingest(w, "b6", docs("b6"), ORACLE)
    yield w, report
    w.close()


def test_w10_unchanged_passages_extract_nothing_and_ask_nothing_T_ING_09_R_PRI_04(w10):
    w, report = w10
    assert (report.unchanged, report.extracted) == (4, 2)
    assert {p.passage for p in load(w) if p.batch == "b6"} == {5, 6}


def test_w10_orphan_fact_is_signalled_and_kept_R_FAI_06(w10):
    w, _ = w10
    orphans = [i for i in orphan_facts(w) if i.code == IssueCode.ORPHAN_FACT]
    assert [i.path for i in orphans] == ["member_of(odon, cercle-des-cendres)"]
    assert ("rel", "odon", "member_of", "cercle-des-cendres") in w.state().facts


def test_w10_structured_facts_are_never_orphans(w10):
    w, _ = w10
    assert not any("odon.title" == i.path for i in orphan_facts(w))  # base.yaml : édition structurée


def test_w10_interim_regent_is_a_new_question_T_ING_08(w10):
    w, _ = w10
    [p5] = [p for p in load(w) if p.id == "b6.notes-baron.p5.1"]
    assert p5.changes[0].change.value == "régent par intérim" and "anomaly" in p5.changes[0].tags
    assert "remembered" not in p5.changes[0].tags


def test_w10_maelle_created_ward_of_refused_and_traced(w10):
    w, _ = w10
    assert decide.accept(w, "b6.notes-baron.p6.1", keep=[0, 1]).ok
    assert decide.accept(w, "b6.notes-baron.p6.2").ok
    state = w.state()
    assert state.facts[("rel", "odon", "parent_of", "maelle")]
    p6 = load_one(w, "b6.notes-baron.p6.1")
    assert [c.state for c in p6.changes] == ["accepted", "accepted", "refused"]
    assert w.store.conn.execute("SELECT COUNT(*) FROM decisions WHERE proposal = ? AND action = 'refuse'",
                                ("b6.notes-baron.p6.1",)).fetchone()[0] == 1


def test_refused_change_is_not_asked_again_on_reingestion_R_PRI_04(tmp_path):
    """Un passage modifié qui répète un changement déjà refusé : la décision est reprise, sans question."""
    w = after_w05()
    v1 = docs("b1")[0].read_text(encoding="utf-8")
    v3 = v1.replace("Depuis la Chute, Odon porte le titre de régent de Brume.",
                    "Depuis la Chute, Odon porte le titre de régent de Brume, dit-on.")
    path = tmp_path / "notes-baron.v3.md"
    path.write_text(v3, encoding="utf-8")
    report = ingest(w, "b9", [path], ORACLE)
    assert report.remembered == 1
    [p7] = [p for p in load(w, status=None) if p.batch == "b9"]
    assert p7.status is EditStatus.ABANDONED and p7.closed_reason == "remembered"


# --- W11 : mode edit ---

@pytest.fixture
def w11():
    w = after_w05()
    ingest(w, "b7", docs("b7"), ORACLE)
    yield w
    w.close()


def test_w11_changes_are_intentions_shown_as_diff_R_ING_01(w11):
    props = {p.passage: p for p in load(w11) if p.batch == "b7"}
    rules, title = props[1].changes[0], props[2].changes[0]
    assert "intention" in rules.tags and rules.detail["occupied_by"]["fact"] == ["rel", "odon", "rules", "brume"]
    assert "intention" in title.tags and title.detail["occupied_by"]["value"] == "baron"


def test_w11_nothing_applied_until_confirmed_then_abandon_is_traced_R_CYC_02(w11):
    before = w11.state().seq
    for p in [p for p in load(w11) if p.batch == "b7"]:
        assert decide.abandon(w11, p.id, "le siège sera joué en scénario").ok
    assert w11.state().seq == before
    closed = [p for p in load(w11, status=None) if p.batch == "b7"]
    assert {p.status for p in closed} == {EditStatus.ABANDONED}
    actions = {a for (a,) in w11.store.conn.execute(
        "SELECT action FROM decisions WHERE proposal LIKE 'b7.%'")}
    assert actions == {"abandon"}


def test_accepting_an_intention_is_an_evolution(w11):
    [rules] = [p for p in load(w11) if p.batch == "b7" and p.passage == 1]
    result = decide.accept(w11, rules.id)
    applied = w11.store.edit(result.edit_id).edit
    assert applied.origin == "evolution" and [c.op for c in applied.changes] == ["remove_relation", "add_relation"]
