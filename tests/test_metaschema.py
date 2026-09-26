"""Méta-schéma et contrôles croisés (T-SCH-01, R-SCH-01, R-SCH-07, R-NOY-01)."""

from __future__ import annotations

import pytest

from worldkit.core.schema import IssueCode, build_schema, validate_schema
from worldkit.core.schema.metaschema import AttrType, ScalarKind


def schema(types=None, relations=None, **header):
    return {"schema": "test", **header, "types": types or {}, "relations": relations or {}}


CHAR = {"Character": {"attributes": {"name": {"type": "text", "required": True}}}}
PLACE = {"Place": {"attributes": {"name": {"type": "text"}}}}


def codes(doc):
    return {(i.code, i.rule) for i in validate_schema(doc)}


@pytest.mark.parametrize("text,kind,is_list,ref", [
    ("text", ScalarKind.TEXT, False, None),
    ("integer", ScalarKind.INTEGER, False, None),
    ("boolean", ScalarKind.BOOLEAN, False, None),
    ("list[text]", ScalarKind.TEXT, True, None),
    ("ref[Ability]", ScalarKind.REF, False, "Ability"),
    ("list[ref[Ability]]", ScalarKind.REF, True, "Ability"),
])
def test_attribute_type_grammar(text, kind, is_list, ref):
    t = AttrType.parse(text)
    assert (t.kind, t.is_list, t.ref_target) == (kind, is_list, ref)
    assert str(t) == text


@pytest.mark.parametrize("text", ["emotion", "list[list[text]]", "ref[]", "list[]", "Text", "ref[Ability"])
def test_attribute_type_outside_grammar_T_SCH_01(text):
    with pytest.raises(ValueError):
        AttrType.parse(text)


def test_bounds_only_on_integers_T_SCH_01():
    doc = schema({"Item": {"attributes": {"name": {"type": "text", "min": 1}}}})
    assert (IssueCode.MALFORMED_SCHEMA, "T-SCH-01") in codes(doc)


def test_unknown_key_is_rejected_not_defaulted_T_SCH_01():
    """« cardinalty » ne doit pas retomber silencieusement sur many_to_many."""
    doc = schema(PLACE, {"located_in": {"from": "Place", "to": "Place", "cardinalty": "many_to_one"}})
    assert (IssueCode.MALFORMED_SCHEMA, "T-SCH-01") in codes(doc)


def test_default_cardinality_is_many_to_many_R_SCH_01():
    s = build_schema(schema(CHAR, {"knows": {"from": "Character", "to": "Character"}}))
    assert s.relations["knows"].cardinality == "many_to_many"
    assert s.relations["knows"].from_ == ["Character"]


def test_core_relation_cannot_be_declared_R_NOY_01():
    doc = schema(CHAR, {"same_as": {"from": "Character", "to": "Character"}})
    assert (IssueCode.CORE_TYPE_DECLARED, "R-NOY-01") in codes(doc)


def test_core_type_rejected_in_rule_system_too_R_NOY_01():
    doc = schema({"Sheet": {"attributes": {}}}, kind="rule_system")
    assert (IssueCode.CORE_TYPE_DECLARED, "R-NOY-01") in codes(doc)


def test_inheritance_cycle_R_SCH_01():
    doc = schema({"A": {"extends": "B"}, "B": {"extends": "A"}})
    assert (IssueCode.INHERITANCE_CYCLE, "R-SCH-01") in codes(doc)


def test_inherited_attribute_cannot_be_redefined_T_SCH_01():
    doc = schema({**CHAR, "Knight": {"extends": "Character", "attributes": {"name": {"type": "integer"}}}})
    assert (IssueCode.INHERITED_ATTRIBUTE_REDEFINED, "T-SCH-01") in codes(doc)


def test_inheritance_merges_attributes_and_subtyping():
    s = build_schema(schema({**CHAR, "Knight": {"extends": "Character", "attributes": {"order": {"type": "text"}}}}))
    assert set(s.attributes_of("Knight")) == {"name", "order"}
    assert s.is_subtype("Knight", "Character") and not s.is_subtype("Character", "Knight")


def test_ref_to_undeclared_type_R_SCH_01():
    doc = schema({"Creature": {"attributes": {"abilities": {"type": "list[ref[Ability]]"}}}}, kind="rule_system")
    assert (IssueCode.UNDECLARED_REFERENCE, "R-SCH-01") in codes(doc)


def test_symmetric_relation_between_different_types_rejected_R_SCH_01():
    doc = schema({**CHAR, **PLACE}, {"bound_to": {"from": "Character", "to": "Place", "symmetric": True}})
    assert (IssueCode.ASYMMETRIC_SYMMETRIC_RELATION, "R-SCH-01") in codes(doc)


@pytest.mark.parametrize("cardinality", ["one_to_many", "many_to_one"])
def test_symmetric_relation_must_be_one_to_one_or_many_to_many_R_SCH_01(cardinality):
    doc = schema(CHAR, {"twin_of": {"from": "Character", "to": "Character", "symmetric": True,
                                    "cardinality": cardinality}})
    assert (IssueCode.ASYMMETRIC_SYMMETRIC_RELATION, "R-SCH-01") in codes(doc)


@pytest.mark.parametrize("doc", [
    schema({"Personnage_": {"attributes": {}}}),
    schema({"personnage": {"attributes": {}}}),
    schema({"Lieu": {"attributes": {"catégorie": {"type": "text"}}}}),
    schema({"Place": {"attributes": {"Name": {"type": "text"}}}}),
    schema(CHAR, {"frèreDe": {"from": "Character", "to": "Character"}}),
], ids=["type-underscore", "type-lowercase", "accent", "attr-capital", "relation-camel-accent"])
def test_world_identifiers_ascii_and_conventional_case_R_SCH_07(doc):
    assert (IssueCode.NON_ENGLISH_IDENTIFIER, "R-SCH-07") in codes(doc)


def test_R_SCH_07_applies_to_world_schemas_only():
    """R-SCH-07 vise les identifiants de monde ; un système de règles n'est pas contraint."""
    doc = schema({"Monstre": {"attributes": {"PV": {"type": "integer"}}}}, kind="rule_system")
    assert validate_schema(doc) == []


def test_prepared_labels_accepted_R_SCH_08():
    doc = schema({"Place": {"labels": {"fr": "Lieu"}, "attributes": {"name": {"type": "text", "labels": {"fr": "nom"}}}}})
    assert validate_schema(doc) == []


def test_non_mapping_document():
    assert validate_schema(["not", "a", "schema"])[0].code == IssueCode.MALFORMED_SCHEMA
