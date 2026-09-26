"""M2 et cœur de M4 : application, collisions, péremption, historique (J2).

R-FAI-05, R-EDI-03, R-EDI-04, R-EDI-07, R-EDI-09, R-HIS-01, R-HIS-04, R-CYC-01, R-CYC-04, T-ING-02, T-ING-06.
"""

from __future__ import annotations

import sqlite3

import pytest

from support import attr, base_world, create, edit, rel, unrel
from worldkit.core.conflicts import check_application
from worldkit.core.journal.models import EditStatus
from worldkit.core.schema import IssueCode
from worldkit.core.views import Filter, View, state_report


@pytest.fixture
def world():
    w = base_world()
    yield w
    w.close()


def codes(outcome):
    return {(i.code, i.rule) for i in outcome.issues}


# --- Collisions (décision J2 : refus, sauf retrait explicite dans la même édition) ---

def test_adding_on_an_occupied_key_is_refused_R_FAI_05(world):
    outcome = world.apply(edit(*create("conseil", "Faction", "le conseil des marchands"),
                               rel("conseil", "rules", "brume", visibility="public")))
    assert outcome.status is None
    assert codes(outcome) == {(IssueCode.KEY_COLLISION, "R-FAI-05")}
    assert "rules(odon, brume)" in outcome.issues[0].message


def test_explicit_removal_in_the_same_edit_replaces(world):
    outcome = world.apply(edit(*create("conseil", "Faction", "le conseil des marchands"),
                               unrel("odon", "rules", "brume"),
                               rel("conseil", "rules", "brume", visibility="public")))
    assert outcome.status == EditStatus.APPLIED
    state = world.state()
    assert state.occupancy[("rel_to", "rules", "brume")] == ("rel", "conseil", "rules", "brume")


def test_set_attribute_replaces_and_reads_old_value_T_ING_02(world):
    head = world.state()
    app = check_application(edit(attr("odon", "title", "régent")).changes, head, "x")
    assert app.applicable
    assert ("attr", "odon", "title") in app.effects.reads and ("entity", "odon") in app.effects.reads
    assert app.state.facts[("attr", "odon", "title")].value == "régent"


def test_replacing_a_value_keeps_its_visibility_T_FAI_01(world):
    world.apply(edit(attr("odon", "title", "régent")))
    assert world.state().facts[("attr", "odon", "title")].visibility == "public"


def test_internal_contradiction(world):
    outcome = world.apply(edit(attr("odon", "title", "régent"), attr("odon", "title", "comte")))
    assert codes(outcome) == {(IssueCode.INTERNAL_CONTRADICTION, "R-FAI-05")}


def test_removing_a_missing_fact_R_EDI_04(world):
    outcome = world.apply(edit(unrel("isabeau", "rules", "brume")))
    assert codes(outcome) == {(IssueCode.MISSING_FACT, "R-EDI-04")}


def test_creating_an_existing_entity(world):
    outcome = world.apply(edit(*create("odon", "Character", "Odon")))
    assert (IssueCode.KEY_COLLISION, "R-FAI-05") in codes(outcome)


def test_symmetric_one_to_one_collision_spouse_of(world):
    outcome = world.apply(edit(*create("zoe", "Character", "Zoé"), rel("zoe", "spouse_of", "mervin")))
    assert codes(outcome) == {(IssueCode.KEY_COLLISION, "R-FAI-05")}


def test_visibility_change_does_not_write_the_value_key_T_FAI_01(world):
    head = world.state()
    vis = check_application(edit({"op": "set_visibility", "target": "odon.title", "value": "secret"}).changes,
                            head, "a").effects
    val = check_application(edit(attr("odon", "title", "régent")).changes, head, "b").effects
    assert not (vis.writes & val.writes)


# --- Règles d'édition ---

def test_w16_delete_outside_correction_refused_R_EDI_07(world):
    outcome = world.apply(edit({"op": "delete_entity", "entity": "odon"}, id="e303"))
    assert codes(outcome) == {(IssueCode.EDIT_RULE, "R-EDI-07")}


def test_w16_duplicate_and_deletion_R_IDT_04_R_HIS_04(world):
    e301 = edit(*create("roi-gris", "Character", "le Roi Gris", "public"), *create("collines", "Place", "les collines"))
    assert world.apply(e301).status == EditStatus.APPLIED
    before = world.set_point("@before-e302")
    e302 = edit(rel("roi-gris", "same_as", "aldren-ii", kind="duplicate", visibility="public"),
                {"op": "delete_entity", "entity": "collines"}, origin="correction")
    assert world.apply(e302).status == EditStatus.APPLIED
    state = world.state()
    for flt in Filter:
        view = View(state, flt)
        assert "roi-gris" not in view.entity_ids() and "aldren-ii" in view.entity_ids()
        assert view.page("roi-gris").id == "aldren-ii"
        assert view.page("roi-gris").members == ["aldren-ii", "roi-gris"]
    assert "collines" not in state.entities
    assert "collines" in world.state(point=before).entities  # R-HIS-04


def test_curation_contains_only_document_status_R_EDI_09(world):
    assert codes(world.apply(edit(attr("odon", "title", "x"), origin="curation"))) == \
        {(IssueCode.EDIT_RULE, "R-EDI-09")}
    doc = {"op": "set_document_obsolete", "document": "vieilles-notes", "value": True}
    assert codes(world.apply(edit(doc))) == {(IssueCode.EDIT_RULE, "R-EDI-09")}
    assert world.apply(edit(doc, origin="curation")).status == EditStatus.APPLIED


def test_duplicate_edit_id_refused(world):
    assert codes(world.apply(edit(attr("odon", "title", "x"), id="e001"))) == {(IssueCode.EDIT_RULE, "R-CYC-01")}


def test_closure_carries_no_visibility():
    from worldkit.core.schema import parse_changes
    _, issues = parse_changes([{"op": "close_entity", "entity": "odon", "visibility": "secret"}])
    assert [i.code for i in issues] == [IssueCode.MALFORMED_CHANGE]


# --- Schéma dans l'état (W08, W09) ---

def test_w09_schema_extension_in_the_same_edit(world):
    vassal = {"op": "schema_set_relation", "relation": "vassal_of",
              "definition": {"from": "Character", "to": "Character", "cardinality": "many_to_one"}}
    assert world.apply(edit(rel("odon", "vassal_of", "mervin"))).status is None
    outcome = world.apply(edit(vassal, rel("odon", "vassal_of", "mervin", visibility="public")))
    assert outcome.status == EditStatus.APPLIED
    state = world.state()
    assert "vassal_of" in state.world.relations and state.schema_rev == outcome.seq


def test_w08_schema_change_makes_the_sheet_non_conforming(world):
    e102 = edit({"op": "schema_set_type", "scope": "system-a", "type": "Creature", "attribute": "hp",
                 "constraint": {"min": 6, "max": 10}}, id="e102")
    assert world.apply(e102).status == EditStatus.APPLIED
    found = [(i.code, i.path) for i in state_report(world.state())]
    assert (IssueCode.NON_CONFORMING, "loup-de-cendre@system-a.hp") in found
    assert world.state().facts[("attr", "loup-de-cendre@system-a", "hp")].value == 5


# --- Notoriété effective et levée de propagation (R-NOT-04, R-NOT-07) ---

def test_propagation_cap_masked_report_and_lifting(world):
    world.apply(edit(*create("conseil", "Faction", "le conseil des marchands"), unrel("odon", "rules", "brume"),
                     rel("conseil", "rules", "brume", visibility="public")))
    state = world.state()
    assert not any(r.relation == "rules" for r in View(state, Filter.PLAYER).page("brume").relations)
    assert any(i.code == IssueCode.MASKED_PUBLIC_FACT for i in state_report(state))
    world.apply(edit({"op": "set_visibility", "target": "conseil rules brume", "value": "public",
                      "propagation_lifted": True}))
    state = world.state()
    page = View(state, Filter.PLAYER).page("brume")
    assert [(r.relation, r.other) for r in page.relations if r.relation == "rules"] == [("rules", None)]
    assert "conseil" not in View(state, Filter.PLAYER).entity_ids()
    assert not any(i.code == IssueCode.MASKED_PUBLIC_FACT for i in state_report(state))


# --- Éditions en attente et péremption (T-ING-01, T-ING-06) ---

def test_independent_pending_edit_is_rebased_silently(world):
    pending = edit(attr("brume", "category", "cité franche"))
    assert world.submit(pending).status == EditStatus.PENDING
    world.apply(edit(attr("odon", "title", "comte")))
    outcome = world.confirm(pending.id)
    assert outcome.status == EditStatus.APPLIED and outcome.issues == []


def test_touched_pending_edit_needs_recheck_then_rebase(world):
    pending = edit(attr("odon", "title", "régent"))
    world.submit(pending)
    world.apply(edit(attr("odon", "title", "comte")))
    assert world.store.edit(pending.id).needs_recheck  # marquée dès l'application de l'autre édition
    outcome = world.confirm(pending.id)
    assert outcome.status == EditStatus.PENDING and codes(outcome) == {(IssueCode.STALE_EDIT, "T-ING-06")}
    assert world.rebase(pending.id).issues == []
    assert world.confirm(pending.id).status == EditStatus.APPLIED
    assert world.state().facts[("attr", "odon", "title")].value == "régent"


def test_out_of_schema_edit_is_kept_pending_R_SCH_06(world):
    pending = edit(rel("odon", "vassal_of", "mervin"))
    outcome = world.submit(pending)
    assert outcome.status == EditStatus.PENDING and (IssueCode.OUT_OF_SCHEMA, "R-SCH-06") in codes(outcome)
    assert world.confirm(pending.id).status == EditStatus.PENDING
    assert world.abandon(pending.id).status == EditStatus.ABANDONED
    assert world.confirm(pending.id).status == EditStatus.ABANDONED  # R-CYC-02 : tracée, close


# --- L'historique ne fait que s'allonger (R-HIS-01, R-CYC-01) ---

def test_journal_rows_cannot_be_modified_or_removed(world):
    conn = world.store.conn
    for sql in ("UPDATE journal SET edit_id = 'x' WHERE seq = 2", "DELETE FROM journal WHERE seq = 2",
                "DELETE FROM changes", "UPDATE edits SET status = 'abandoned' WHERE edit_id = 'e001'",
                "DELETE FROM edits WHERE edit_id = 'e001'"):
        with pytest.raises(sqlite3.DatabaseError):
            conn.execute(sql)


def test_earlier_states_stay_readable_R_HIS_04(world):
    base = world.state(point="@base")
    world.apply(edit(attr("odon", "title", "comte")))
    assert world.state(point="@base").facts[("attr", "odon", "title")].value == "baron"
    assert base.seq == world.resolve_point("@base")
