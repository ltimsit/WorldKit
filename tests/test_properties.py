"""Propriétés T1 du calcul des clés (hypothesis) — R-FAI-05, T-FAI-01, T-ARC-01."""

from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st

from support import base_context
from worldkit.core.schema import fact_keys, parse_change

CTX = base_context()
ids = st.text(alphabet="abcdefghijklmnopqrstuvwxyz-0123456789", min_size=1, max_size=12)
values = st.one_of(st.text(max_size=20), st.integers(), st.booleans())
relations = st.sampled_from(sorted(CTX.world.relations))


def rel(src, relation, dst):
    return parse_change({"op": "add_relation", "from": src, "relation": relation, "to": dst})


@given(ids, relations, ids)
def test_keys_are_deterministic(a, relation, b):
    assert fact_keys(rel(a, relation, b), CTX) == fact_keys(rel(a, relation, b), base_context())


@given(ids, st.sampled_from(["sibling_of", "spouse_of"]), ids)
def test_symmetric_relation_key_ignores_endpoint_order(a, relation, b):
    assert fact_keys(rel(a, relation, b), CTX) == fact_keys(rel(b, relation, a), CTX)


@given(ids, st.text(max_size=20), st.text(max_size=20))
def test_distinct_list_values_have_distinct_keys(entity, v1, v2):
    k1 = fact_keys(parse_change({"op": "add_value", "entity": entity, "attribute": "vows", "value": v1}), CTX)
    k2 = fact_keys(parse_change({"op": "add_value", "entity": entity, "attribute": "vows", "value": v2}), CTX)
    assert (k1 == k2) == (v1 == v2)


@given(ids, ids, ids)
def test_one_to_many_target_has_one_source(a, b, place):
    assert set(fact_keys(rel(a, "rules", place), CTX)) & set(fact_keys(rel(b, "rules", place), CTX))


@given(ids, ids, ids, st.booleans(), st.booleans())
def test_symmetric_one_to_one_facts_sharing_an_endpoint_collide(shared, x, y, flip1, flip2):
    """spouse_of : deux faits qui partagent une extrémité se contredisent, dans n'importe quel sens."""
    f1 = rel(x, "spouse_of", shared) if flip1 else rel(shared, "spouse_of", x)
    f2 = rel(y, "spouse_of", shared) if flip2 else rel(shared, "spouse_of", y)
    assert set(fact_keys(f1, CTX)) & set(fact_keys(f2, CTX))


@given(ids, st.sampled_from(["title", "name", "condition"]), values, values)
def test_attribute_key_independent_of_value(entity, attribute, v1, v2):
    set1 = parse_change({"op": "set_attribute", "entity": entity, "attribute": attribute, "value": v1})
    set2 = parse_change({"op": "set_attribute", "entity": entity, "attribute": attribute, "value": v2})
    assert fact_keys(set1, CTX) == fact_keys(set2, CTX)
