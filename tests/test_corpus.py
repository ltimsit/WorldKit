"""Le corpus Valmont contre M1 : état de base, gold, non-conformité (W01 partiel, W08)."""

from __future__ import annotations

import pytest

from support import (
    VALMONT, base_changes, base_context, base_edits, empty_context, naive_snapshot, parse_ok, strip_gold,
)
from worldkit.core.schema import (
    IssueCode, Severity, check_conformity, check_edit, fact_keys, parse_change, read_yaml,
)


def test_base_edits_are_all_in_schema_except_counterpart_of_L1():
    ctx = empty_context()
    found = []
    for edit in base_edits():
        result = check_edit(parse_ok(edit["changes"]), ctx)
        found += result.issues
        ctx = result.context
    assert [(i.code, i.severity) for i in found] == [(IssueCode.PROVISIONAL_CORE_RELATION, Severity.WARNING)]


def test_base_state_has_no_key_collision_R_FAI_05():
    ctx = base_context()
    written = [k for c in base_changes() if c.op in ("add_relation", "set_attribute", "add_value")
               for k in fact_keys(c, ctx)]
    assert len(written) == len(set(written))


def test_w01_base_state_conforms_and_wolf_misses_its_system_b_sheet_R_MET_06():
    """W01 : fiche système A du Loup conforme ; fiche système B manquante, signalée."""
    ctx = base_context()
    found = check_conformity(naive_snapshot(base_changes(), ctx), ctx)
    assert [(i.code, i.path, i.rule, i.severity) for i in found] == \
        [(IssueCode.MISSING_SHEET, "loup-de-cendre@system-b", "R-MET-06", Severity.WARNING)]


def test_missing_sheet_signal_disappears_once_created_b4_p6():
    ctx = base_context()
    sheet = [
        parse_change({"op": "create_entity", "entity": "loup-de-cendre@system-b", "type": "Sheet",
                      "sheet": {"of": "loup-de-cendre", "system": "system-b", "category": "Monster"}}),
        parse_change({"op": "set_attribute", "entity": "loup-de-cendre@system-b", "attribute": "level", "value": 4}),
    ]
    result = check_edit(sheet, ctx)
    assert result.applicable
    assert check_conformity(naive_snapshot(base_changes() + sheet, result.context), result.context) == []


def test_sheet_requirement_follows_subtypes_and_flags_stale_mapping():
    """Une exigence sur Faction vaut pour MonasticOrder ; une catégorie inconnue est signalée."""
    from dataclasses import replace
    ctx = base_context()
    ctx = replace(ctx, sheet_requirements={"system-b": {"Faction": "Guild"}})
    found = check_conformity(naive_snapshot(base_changes(), ctx), ctx)
    assert {i.path for i in found if i.code == IssueCode.MISSING_SHEET} == \
        {"veilleurs@system-b", "cercle-des-cendres@system-b"}
    assert [(i.code, i.path) for i in found if i.code == IssueCode.NON_CONFORMING] == \
        [(IssueCode.NON_CONFORMING, "rule_systems.system-b.sheets.Faction")]


def test_w08_sheet_becomes_non_conforming_after_e102_R_SCH_10():
    """Fiche du Loup (PV 5) après passage du système A à « PV de 6 à 10 » : signalée, non modifiée."""
    ctx = base_context()
    state = naive_snapshot(base_changes(), ctx)
    e102 = parse_change({"op": "schema_set_type", "scope": "system-a", "type": "Creature", "attribute": "hp",
                         "constraint": {"min": 6, "max": 10}})
    after = check_edit([e102], ctx)
    assert after.applicable  # la modification du schéma est permise (R-SCH-04)
    found = [i for i in check_conformity(state, after.context) if i.code == IssueCode.NON_CONFORMING]
    assert [(i.path, i.rule, i.severity) for i in found] == [("loup-de-cendre@system-a.hp", "R-SCH-10", Severity.WARNING)]
    assert state.attributes[("loup-de-cendre@system-a", "hp")] == 5  # rien n'est modifié


def test_cardinality_change_reveals_collision_as_non_conformity():
    """Passer member_of en many_to_one : Mervin dans deux factions devient non conforme."""
    ctx = base_context()
    changes = base_changes() + [parse_change({"op": "add_relation", "from": "mervin", "relation": "member_of",
                                              "to": "veilleurs"})]
    state = naive_snapshot(changes, ctx)
    redefine = parse_change({"op": "schema_set_relation", "relation": "member_of",
                             "definition": {"from": "Character", "to": "Faction", "cardinality": "many_to_one"}})
    found = check_conformity(state, check_edit([redefine], ctx).context)
    assert any(i.code == IssueCode.NON_CONFORMING and "même clé" in i.message for i in found)


def _gold_changes():
    for path in sorted((VALMONT / "gold").glob("*.yaml")):
        for passage in read_yaml(path)["passages"]:
            for change in passage.get("changes") or []:
                yield f"{path.stem}:p{passage['index']}:{change['op']}", change


GOLD = list(_gold_changes())


@pytest.mark.parametrize("raw", [c for _, c in GOLD], ids=[i for i, _ in GOLD])
def test_gold_changes_parse_and_out_of_schema_detected(raw):
    """Chaque changement annoté out_of_schema est détecté comme tel, et seulement ceux-là (R-SCH-06)."""
    ctx = base_context()
    change = parse_change(strip_gold(raw))
    found = {i.code for i in check_edit([change], ctx).issues}
    assert (IssueCode.OUT_OF_SCHEMA in found) == (raw["outcome"] == "out_of_schema")


def test_gold_has_the_three_expected_out_of_schema_changes():
    assert sorted(i for i, c in GOLD if c["outcome"] == "out_of_schema") == [
        "b1-notes-baron.v1:p2:add_relation",
        "b4-bestiaire-loup-de-cendre:p3:set_attribute",
        "b6-notes-baron.v2:p6:add_relation",
    ]
