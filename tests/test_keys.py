"""Clés de fait (R-FAI-05, T-FAI-01) — tableau du brief J1 §3 et exemples de Valmont."""

from __future__ import annotations

import pytest

from support import base_context
from worldkit.core.schema import UnknownRelation, fact_keys, format_key, parse_change


@pytest.fixture(scope="module")
def ctx():
    return base_context()


def keys(ctx, **change):
    return fact_keys(parse_change(change), ctx)


def shown(ctx, **change):
    return [format_key(k) for k in keys(ctx, **change)]


@pytest.mark.parametrize("op", ["create_entity", "close_entity", "delete_entity"])
def test_entity_existence_key(ctx, op):
    extra = {"type": "Faction"} if op == "create_entity" else {}
    assert keys(ctx, op=op, entity="conseil", **extra) == [("entity", "conseil")]


def test_simple_attribute_key(ctx):
    assert keys(ctx, op="set_attribute", entity="odon", attribute="title", value="régent") == \
        keys(ctx, op="unset_attribute", entity="odon", attribute="title") == [("attr", "odon", "title")]


def test_list_attribute_one_key_per_value_R_FAI_05(ctx):
    """Vœux « silence » et « pauvreté » des Veilleurs : deux clés distinctes, pas de collision."""
    silence = keys(ctx, op="add_value", entity="veilleurs", attribute="vows", value="silence")
    poverty = keys(ctx, op="add_value", entity="veilleurs", attribute="vows", value="pauvreté")
    assert silence == [("value", "veilleurs", "vows", "silence")]
    assert set(silence).isdisjoint(poverty)
    assert keys(ctx, op="remove_value", entity="veilleurs", attribute="vows", value="silence") == silence


def test_one_to_many_rules_collision_odon_vs_council_R_FAI_05(ctx):
    """« Odon gouverne Brume » et « le conseil gouverne Brume » : même clé (rules, brume)."""
    odon = keys(ctx, op="add_relation", **{"from": "odon"}, relation="rules", to="brume")
    council = keys(ctx, op="add_relation", **{"from": "conseil"}, relation="rules", to="brume")
    assert odon == council == [("rel_to", "rules", "brume")]
    assert shown(ctx, op="add_relation", **{"from": "odon"}, relation="rules", to="brume") == ["(rules, brume)"]


def test_many_to_one_located_in(ctx):
    assert shown(ctx, op="add_relation", **{"from": "brume"}, relation="located_in", to="valmont") == \
        ["(brume, located_in)"]


def test_many_to_many_member_of(ctx):
    assert keys(ctx, op="add_relation", **{"from": "mervin"}, relation="member_of", to="cercle-des-cendres") == \
        [("rel", "mervin", "member_of", "cercle-des-cendres")]


def test_symmetric_sibling_of_order_independent(ctx):
    """« Aldren frère de Mervin » et « Mervin frère d'Aldren » : même clé."""
    a = keys(ctx, op="add_relation", **{"from": "aldren-ii"}, relation="sibling_of", to="mervin")
    b = keys(ctx, op="add_relation", **{"from": "mervin"}, relation="sibling_of", to="aldren-ii")
    assert a == b == [("rel", "aldren-ii", "sibling_of", "mervin")]


def test_one_to_one_spouse_of_two_keys(ctx):
    assert shown(ctx, op="add_relation", **{"from": "mervin"}, relation="spouse_of", to="isabeau") == \
        ["(isabeau, spouse_of)", "(mervin, spouse_of)"]


@pytest.mark.parametrize("other", ["anna", "zoe"])
def test_symmetric_one_to_one_collides_whatever_the_sort_order(ctx, other):
    """Mervin ne peut avoir deux conjoints, qu'il soit rangé avant ou après l'autre extrémité."""
    isabeau = keys(ctx, op="add_relation", **{"from": "mervin"}, relation="spouse_of", to="isabeau")
    second = keys(ctx, op="add_relation", **{"from": other}, relation="spouse_of", to="mervin")
    assert set(isabeau) & set(second) == {("rel_from", "mervin", "spouse_of")}


def test_non_symmetric_one_to_one_two_keys():
    from worldkit.core.schema.keys import relation_keys
    from worldkit.core.schema import Cardinality
    assert relation_keys("a", "r", "b", Cardinality.ONE_TO_ONE, False) == [("rel_from", "a", "r"), ("rel_to", "r", "b")]


def test_visibility_is_a_sub_key_T_FAI_01(ctx):
    """Changer la notoriété ne collisionne pas avec la modification de la valeur."""
    vis = keys(ctx, op="set_visibility", target="odon member_of cercle-des-cendres", value="secret")
    assert vis == [("visibility", ("rel", "odon", "member_of", "cercle-des-cendres"))]
    vis_attr = keys(ctx, op="set_visibility", target="coeur-de-braise.origin", value="secret")
    assert vis_attr == [("visibility", ("attr", "coeur-de-braise", "origin"))]
    assert vis_attr[0] != ("attr", "coeur-de-braise", "origin")


def test_claim_and_qualification_keys_T_FAI_01(ctx):
    assert keys(ctx, op="add_claim", claim="c1") == [("claim", "c1")]
    assert keys(ctx, op="qualify_claim", claim="c1", value="false") == [("qualification", "c1")]


def test_system_scope_qualifies_entities(ctx):
    assert keys(ctx, op="set_attribute", scope="system-a", entity="bite", attribute="damage", value="1d8") == \
        [("attr", "system-a:bite", "damage")]


def test_schema_element_keys_provisional_L6(ctx):
    assert keys(ctx, op="schema_set_type", scope="system-a", type="Creature", attribute="hp",
                constraint={"min": 6, "max": 10}) == [("schema", "system-a", "type", "Creature", "hp")]


def test_out_of_schema_relation_has_no_key_R_SCH_06(ctx):
    with pytest.raises(UnknownRelation):
        keys(ctx, op="add_relation", **{"from": "odon"}, relation="vassal_of", to="mervin")


def test_tagged_keys_never_mix_forms(ctx):
    """Un attribut nommé comme une relation ne partage pas sa clé."""
    attr = keys(ctx, op="set_attribute", entity="rules", attribute="brume", value="x")
    rel = keys(ctx, op="add_relation", **{"from": "odon"}, relation="rules", to="brume")
    assert set(attr).isdisjoint(rel)
