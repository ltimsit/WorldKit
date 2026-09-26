"""Vérification des changements et des éditions (R-SCH-06, R-SCH-10, R-SCH-03, R-MET-05, décision A)."""

from __future__ import annotations

import pytest

from support import base_context
from worldkit.core.schema import IssueCode, Severity, check_change, check_edit, parse_change


@pytest.fixture(scope="module")
def ctx():
    return base_context()


def issues(ctx, **change):
    return check_change(parse_change(change), ctx)


def codes(ctx, **change):
    return {(i.code, i.rule) for i in issues(ctx, **change)}


def rel(src, relation, dst, **extra):
    return {"op": "add_relation", "from": src, "relation": relation, "to": dst, **extra}


OUT = (IssueCode.OUT_OF_SCHEMA, "R-SCH-06")
INVALID = (IssueCode.INVALID_VALUE, "R-SCH-06")


# --- Hors schéma (R-SCH-06) : exemples du corpus ---

def test_vassal_of_out_of_schema_b1_p2(ctx):
    assert codes(ctx, **rel("odon", "vassal_of", "mervin")) == {OUT}


def test_constitution_out_of_schema_for_system_a_b4_p3(ctx):
    assert codes(ctx, op="set_attribute", entity="loup-de-cendre@system-a", attribute="constitution", value=13) == {OUT}


def test_undeclared_type_out_of_schema(ctx):
    assert codes(ctx, op="create_entity", entity="guilde", type="Guild") == {OUT}


def test_unknown_scope_out_of_schema(ctx):
    assert codes(ctx, op="create_entity", scope="system-z", entity="x", type="Ability") == {OUT}


# --- Valeur invalide à l'écriture (décision A : R-SCH-06 élargie, non applicable) ---

def test_hp_above_bound_is_refused(ctx):
    assert codes(ctx, op="set_attribute", entity="loup-de-cendre@system-a", attribute="hp", value=12) == {INVALID}


def test_wrong_scalar_type_is_refused(ctx):
    assert codes(ctx, op="set_attribute", entity="loup-de-cendre@system-a", attribute="hp", value="cinq") == {INVALID}
    assert codes(ctx, op="set_attribute", entity="loup-de-cendre", attribute="flame_bearer", value="oui") == {INVALID}


def test_relation_endpoint_type_is_checked(ctx):
    """rules va vers un Place : « Odon gouverne Aldren » est refusé."""
    assert codes(ctx, **rel("odon", "rules", "aldren-ii")) == {INVALID}


def test_subtype_accepted_where_parent_expected(ctx):
    """MonasticOrder étend Faction : les Veilleurs peuvent posséder un objet."""
    assert issues(ctx, **rel("veilleurs", "owns", "coeur-de-braise")) == []


def test_list_attribute_only_via_add_remove_value_R_SCH_01(ctx):
    assert codes(ctx, op="set_attribute", entity="veilleurs", attribute="vows", value="silence") == \
        {(IssueCode.INVALID_VALUE, "R-SCH-01")}
    assert codes(ctx, op="add_value", entity="odon", attribute="title", value="régent") == \
        {(IssueCode.INVALID_VALUE, "R-SCH-01")}


def test_unset_required_attribute_is_refused(ctx):
    assert codes(ctx, op="unset_attribute", entity="odon", attribute="name") == {INVALID}
    assert issues(ctx, op="unset_attribute", entity="odon", attribute="title") == []


def test_ref_value_must_point_to_declared_type(ctx):
    ok = issues(ctx, op="add_value", entity="loup-de-cendre@system-a", attribute="abilities", value="system-a:azure-flame")
    assert ok == []
    assert codes(ctx, op="add_value", entity="loup-de-cendre@system-a", attribute="abilities", value="odon") == {INVALID}


def test_created_entity_without_required_attribute_is_refused(ctx):
    edit = [parse_change({"op": "create_entity", "entity": "conseil", "type": "Faction"})]
    assert {(i.code, i.rule) for i in check_edit(edit, ctx).issues} == {INVALID}
    edit.append(parse_change({"op": "set_attribute", "entity": "conseil", "attribute": "name",
                              "value": "le conseil des marchands"}))
    assert check_edit(edit, ctx).issues == []


def test_same_as_requires_kind_R_IDT_02(ctx):
    assert codes(ctx, **rel("corvin", "same_as", "frere-cendre")) == {(IssueCode.INVALID_VALUE, "R-IDT-02")}
    assert issues(ctx, **rel("corvin", "same_as", "frere-cendre", kind="duplicate")) == []


def test_unknown_entity_R_EDI_04(ctx):
    assert codes(ctx, **rel("conseil", "rules", "brume")) == {(IssueCode.UNKNOWN_ENTITY, "R-EDI-04")}


def test_counterpart_of_is_a_provisional_core_relation_L1(ctx):
    found = issues(ctx, **rel("flamme-azur", "counterpart_of", "system-a:azure-flame"))
    assert [(i.code, i.rule, i.severity) for i in found] == \
        [(IssueCode.PROVISIONAL_CORE_RELATION, "R-MET-04", Severity.WARNING)]


def test_prepared_fields_accepted_and_ignored_invariant_10(ctx):
    change = rel("mervin", "rules", "valmont", diegetic_window={"from": "an 1492"}, authority="high",
                 labels={"fr": "gouverne"}, visibility="public")
    assert issues(ctx, **change) == []
    assert parse_change(change).diegetic_window == {"from": "an 1492"}  # conservé


def test_sheet_creation_checks_system_and_category(ctx):
    sheet = {"op": "create_entity", "entity": "loup-de-cendre@system-b", "type": "Sheet"}
    ok = {**sheet, "sheet": {"of": "loup-de-cendre", "system": "system-b", "category": "Monster"}}
    edit = [parse_change(ok), parse_change({"op": "set_attribute", "entity": "loup-de-cendre@system-b",
                                             "attribute": "level", "value": 4})]
    assert check_edit(edit, ctx).issues == []
    bad = {**sheet, "sheet": {"of": "loup-de-cendre", "system": "system-b", "category": "Creature"}}
    assert codes(ctx, **bad) == {OUT}
    assert codes(ctx, **sheet) == {(IssueCode.INVALID_VALUE, "R-MET-01")}


# --- Extension du schéma dans la même édition (R-SCH-03, R-MET-05, W09) ---

VASSAL_DEF = {"op": "schema_set_relation", "scope": "world", "relation": "vassal_of",
              "definition": {"from": "Character", "to": "Character", "cardinality": "many_to_one",
                             "labels": {"fr": "vassal de"}}}


@pytest.mark.parametrize("order", ["schema_first", "schema_last"])
def test_w09_edit_validated_against_its_own_schema_changes(ctx, order):
    changes = [parse_change(VASSAL_DEF), parse_change(rel("odon", "vassal_of", "mervin"))]
    if order == "schema_last":
        changes.reverse()
    result = check_edit(changes, ctx)
    assert result.issues == [] and result.applicable
    assert "vassal_of" in result.context.world.relations
    assert "vassal_of" not in ctx.world.relations  # l'original n'est pas modifié


def test_w09_first_attempt_refused(ctx):
    result = check_edit([parse_change(rel("odon", "vassal_of", "mervin"))], ctx)
    assert not result.applicable


def test_schema_change_producing_invalid_schema_is_refused(ctx):
    bad = {**VASSAL_DEF, "definition": {"from": "Character", "to": "Vassal"}}
    result = check_edit([parse_change(bad)], ctx)
    assert {(i.code, i.rule) for i in result.issues} == {(IssueCode.UNDECLARED_REFERENCE, "R-SCH-01")}


def test_constraint_patch_with_inconsistent_bounds_is_refused(ctx):
    patch = {"op": "schema_set_type", "scope": "system-a", "type": "Creature", "attribute": "hp",
             "constraint": {"min": 12}}
    assert not check_edit([parse_change(patch)], ctx).applicable


def test_malformed_change_R_EDI_06():
    from worldkit.core.schema import parse_changes
    _, found = parse_changes([{"op": "teleport", "entity": "odon"}, {"op": "set_attribute", "entity": "odon"}])
    assert [(i.code, i.rule) for i in found] == [(IssueCode.MALFORMED_CHANGE, "R-EDI-06")] * 2
