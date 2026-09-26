"""Parcours W03, W04, W05, W09 — concurrence entre lots, péremption, revue, adaptation (J3.2).

R-PRI-02, R-PRI-04, R-PRI-07, R-EDI-05, R-EDI-08, R-CYC-02, R-SCH-06, T-ING-04 à T-ING-08, T-ING-18.
"""

from __future__ import annotations

import pytest

from support import VALMONT, base_world, edit
from worldkit.core.journal.models import EditStatus, Origin, RedefinitionKind
from worldkit.core.schema import parse_change
from worldkit.core.views import Filter, View
from worldkit.ingest import decide
from worldkit.ingest.batch import batch_documents, ingest
from worldkit.ingest.queue import load, load_one, refresh
from worldkit.periphery.extraction import OracleExtractor

ORACLE = OracleExtractor(VALMONT / "gold")


def docs(batch):
    return batch_documents(VALMONT / "docs" / "batches.yaml", batch)


def change(world, pid, op, attr=None):
    p = load_one(world, pid)
    return next(c for c in p.changes if c.change.op == op and (attr is None or
                getattr(c.change, "attribute", None) == attr or getattr(c.change, "relation", None) == attr))


@pytest.fixture
def after_b5():
    w = base_world()
    ingest(w, "b1", docs("b1"), ORACLE)
    ingest(w, "b5", docs("b5"), ORACLE)
    yield w
    w.close()


# --- W03 : lot b5 pendant que b1 est en attente ---

def test_w03_title_proposals_compete_with_priority_to_b1_R_PRI_07(after_b5):
    b5_title = change(after_b5, "b5.notes-conseil.p2.1", "set_attribute", "title")
    b1_title = change(after_b5, "b1.notes-baron.p7.1", "set_attribute", "title")
    assert "competing" in b5_title.tags and "competing" in b1_title.tags
    assert b5_title.detail["competes_with"] == ["b1.notes-baron.p7.1"]
    assert b5_title.detail["priority"] == "b1.notes-baron.p7.1"
    assert b1_title.detail["competes_with"] == ["b5.notes-conseil.p2.1"]


def test_w03_based_in_competes_with_hautval_not_with_same_value(after_b5):
    b5 = change(after_b5, "b5.notes-conseil.p1.1", "add_relation", "based_in")
    assert b5.detail["competes_with"] == ["b1.lieux-de-valmont.p2.1"]
    assert b5.detail["same_as"] == ["b1.notes-baron.p4.2"]


def test_w03_member_of_same_fingerprint_as_b1_T_ING_08(after_b5):
    b5 = change(after_b5, "b5.notes-conseil.p2.1", "add_relation", "member_of")
    b1 = change(after_b5, "b1.notes-baron.p4.1", "add_relation", "member_of")
    assert b5.fingerprint == b1.fingerprint and "duplicate" in b5.tags


def test_w03_council_resolved_to_the_pending_creation_T_ING_07(after_b5):
    b5 = load_one(after_b5, "b5.notes-conseil.p1.1")
    assert b5.changes[0].change.from_ == "conseil-marchands"
    assert "b1.notes-baron.p3.1" in b5.depends_on
    creations = [c for p in load(after_b5) for c in p.changes if c.change.op == "create_entity"
                 and c.change.entity.startswith("conseil")]
    assert len(creations) == 1


# --- W04 : péremption par une édition structurée ---

def test_w04_touched_proposal_requalified_as_support_others_rebased_T_ING_06(after_b5):
    e101 = edit({"op": "add_value", "entity": "brume", "attribute": "aliases", "value": "Brume-sur-Mer",
                 "visibility": "public"}, id="e101")
    assert after_b5.apply(e101).status == EditStatus.APPLIED
    assert refresh(after_b5) == ["b1.lieux-de-valmont.p1.1"]
    alias = load_one(after_b5, "b1.lieux-de-valmont.p1.1")
    assert alias.status is EditStatus.ABANDONED and alias.closed_reason == "support"
    head = after_b5.state().seq
    assert {p.base.seq for p in load(after_b5)} == {head}


# --- W05 : revue des lots b1 et b5 ---

@pytest.fixture
def reviewed(after_b5):
    w = after_b5
    w.apply(edit({"op": "add_value", "entity": "brume", "attribute": "aliases", "value": "Brume-sur-Mer",
                  "visibility": "public"}, id="e101"))
    steps = [
        decide.accept(w, "b1.notes-baron.p3.1", keep=[0, 1]),
        decide.accept(w, "b1.notes-baron.p4.1"),
        *decide.choose(w, "b1.notes-baron.p4.2"),
        decide.accept(w, "b1.notes-baron.p5.1"),
        decide.accept(w, "b1.notes-baron.p5.2"),
        decide.refuse(w, "b1.notes-baron.p7.1"),
        decide.refuse(w, "b5.notes-conseil.p2.1", [1]),
        decide.accept(w, "b1.lieux-de-valmont.p3.1"),
        decide.refuse(w, "b1.lieux-de-valmont.p3.2"),
        decide.accept(w, "b1.lieux-de-valmont.p4.1"),
    ]
    decide.dismiss(w, "notes-baron", 6)
    assert all(s.ok for s in steps), [str(i) for s in steps for i in s.issues]
    return w


def test_w05_council_partial_confirmation_is_a_derived_edit_R_EDI_08(reviewed):
    derived = reviewed.store.edit("b1.notes-baron.p3.1.d").edit
    assert derived.derived_from == "b1.notes-baron.p3.1" and derived.origin is Origin.ENRICHMENT
    assert [c.op for c in derived.changes] == ["create_entity", "set_attribute"]
    p3 = load_one(reviewed, "b1.notes-baron.p3.1")
    assert p3.status is EditStatus.APPLIED and [c.state for c in p3.changes] == ["accepted", "accepted", "refused"]


def test_w05_b5_member_of_becomes_a_support(reviewed):
    b5 = load_one(reviewed, "b5.notes-conseil.p2.1")
    assert [c.state for c in b5.changes] == ["support", "refused"]
    assert b5.status is EditStatus.ABANDONED


def test_w05_hautval_refused_and_traced(reviewed):
    lieux = load_one(reviewed, "b1.lieux-de-valmont.p2.1")
    assert lieux.status is EditStatus.ABANDONED and lieux.changes[0].state == "refused"
    assert reviewed.state().occupancy[("rel_from", "conseil-marchands", "based_in")] == \
        ("rel", "conseil-marchands", "based_in", "brume")


def test_w05_odon_stays_baron_and_both_refusals_traced_R_PRI_04(reviewed):
    assert reviewed.state().facts[("attr", "odon", "title")].value == "baron"
    fps = {change(reviewed, "b1.notes-baron.p7.1", "set_attribute", "title").fingerprint,
           change(reviewed, "b5.notes-conseil.p2.1", "set_attribute", "title").fingerprint}
    traced = {fp for (fp,) in reviewed.store.conn.execute("SELECT fingerprint FROM decisions WHERE action = 'refuse'")}
    assert fps <= traced


def test_w05_views(reviewed):
    state = reviewed.state()
    player, author = View(state, Filter.PLAYER), View(state, Filter.AUTHOR)
    assert not {"taverne-du-heron", "conseil-marchands"} & set(player.entity_ids())
    assert not any(r.relation == "member_of" for r in player.page("odon").relations)
    assert ("aliases", "le Roi Gris") in {(a.name, a.value) for a in author.page("aldren-ii").attributes}


def test_w05_only_vassal_of_stays_pending(reviewed):
    assert [p.id for p in load(reviewed)] == ["b1.notes-baron.p2.1"]


def test_dependency_must_be_decided_first_T_ING_05(after_b5):
    result = decide.accept(after_b5, "b1.notes-baron.p4.1")
    assert not result.ok and result.issues[0].rule == "T-ING-05"


# --- Acceptation d'une anomalie : retrait explicite, origine redéfinition (décisions J3.2) ---

def test_accepting_an_anomaly_removes_the_occupant_explicitly(after_b5):
    result = decide.accept(after_b5, "b1.notes-baron.p3.1")
    assert result.ok and result.edit_id == "b1.notes-baron.p3.1.d"
    derived = after_b5.store.edit(result.edit_id).edit
    assert (derived.origin, derived.redefinition) == (Origin.REDEFINITION, RedefinitionKind.POINT)
    assert [c.op for c in derived.changes] == ["remove_relation", "create_entity", "set_attribute", "add_relation"]
    assert derived.changes[0].from_ == "odon"
    assert after_b5.state().occupancy[("rel_to", "rules", "brume")] == ("rel", "conseil-marchands", "rules", "brume")


def test_whole_acceptance_applies_the_proposal_itself_with_deduced_origin(after_b5):
    result = decide.accept(after_b5, "b1.notes-baron.p7.1")
    assert result.edit_id == "b1.notes-baron.p7.1"
    applied = after_b5.store.edit("b1.notes-baron.p7.1")
    assert applied.status is EditStatus.APPLIED
    assert (applied.edit.origin, applied.edit.redefinition) == (Origin.REDEFINITION, RedefinitionKind.POINT)
    b5 = change(after_b5, "b5.notes-conseil.p2.1", "set_attribute", "title")
    assert "anomaly" in b5.tags and "competing" in b5.tags  # l'autre passe à revérifier (T-ING-18)


# --- W09 : hors schéma, puis adaptation ---

def test_w09_out_of_schema_refused_then_adapted(after_b5):
    first = decide.accept(after_b5, "b1.notes-baron.p2.1")
    assert not first.ok and first.issues[0].rule == "R-SCH-06"
    schema = parse_change({"op": "schema_set_relation", "scope": "world", "relation": "vassal_of",
                           "definition": {"from": "Character", "to": "Character", "cardinality": "many_to_one",
                                          "labels": {"fr": "vassal de"}}})
    second = decide.adapt(after_b5, "b1.notes-baron.p2.1", [schema])
    assert second.ok
    derived = after_b5.store.edit(second.edit_id).edit
    assert derived.derived_from == "b1.notes-baron.p2.1"
    assert [c.op for c in derived.changes] == ["schema_set_relation", "add_relation"]
    assert "vassal_of" in after_b5.state().world.relations


def test_competing_proposals_do_not_depend_on_each_other_s6_3(after_b5):
    """Deux écritures de la même clé : contradiction, pas dépendance. Choisir « gouverneur » est possible."""
    assert "b1.notes-baron.p7.1" not in load_one(after_b5, "b5.notes-conseil.p2.1").depends_on
    decide.accept(after_b5, "b1.notes-baron.p3.1", keep=[0, 1])
    decide.accept(after_b5, "b1.notes-baron.p4.1")
    results = decide.choose(after_b5, "b5.notes-conseil.p2.1")
    assert all(r.ok for r in results)
    assert after_b5.state().facts[("attr", "odon", "title")].value == "gouverneur"
    assert load_one(after_b5, "b1.notes-baron.p7.1").status is EditStatus.ABANDONED
