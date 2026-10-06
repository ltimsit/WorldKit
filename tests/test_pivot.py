"""X-016 — schéma de genre « fantasy jdr » comme ontologie pivot de l'extraction (voie A) : hiérarchie, correspondance
sans modèle vers le schéma du monde (T-ARC-01), hors schéma laissé à l'auteur (R-SCH-06), prompt stable (cache)."""

from __future__ import annotations

from pathlib import Path

import pytest

from test_facts import PROFILE
from worldkit.periphery.pivot import load_map, load_pivot

ROOT = Path(__file__).resolve().parent.parent
VALMONT_MAP = ROOT / "corpus/valmont-v1/valmont/pivot-map.yaml"
CORBELLE_MAP = ROOT / "corpus/corbelle-v1/corbelle/pivot-map.yaml"


def test_the_genre_schema_is_a_consistent_hierarchy_X_016():
    pivot = load_pivot()
    assert pivot.signature == "fantasy-jdr-1" and len(pivot.relations) >= 50
    assert pivot.chain("mother_of") == ["mother_of", "parent_of", "kin_of"]
    for r in pivot.relations.values():
        assert r.broader is None or r.broader in pivot.relations
        assert set(r.from_) <= set(pivot.types) and set(r.to) <= set(pivot.types), r.id


def test_rendering_is_deterministic_for_the_prompt_cache_X_016():
    assert load_pivot().render() == load_pivot().render()
    assert "- near (" in load_pivot().render() and "⊂ parent_of" in load_pivot().render()


@pytest.mark.parametrize("path", [VALMONT_MAP, CORBELLE_MAP])
def test_world_maps_name_only_world_relations_and_types_X_016(path):
    import yaml
    m = load_map(path)
    schema = yaml.safe_load((path.parent / "schema.yaml").read_text(encoding="utf-8"))
    assert set(m.relations.values()) <= set(schema["relations"])
    assert set(m.types) == set(schema["types"]) and set(m.types.values()) <= set(m.pivot.types)


def test_a_relation_climbs_the_hierarchy_to_the_world_or_stays_out_of_schema_R_SCH_06():
    m = load_map(VALMONT_MAP)
    assert m.to_world("parent_of") == ("parent_of", "")
    assert m.to_world("mother_of") == ("parent_of", "mother_of")       # la forme exacte, pour le critique
    assert m.to_world("leader_of") == ("member_of", "leader_of")
    assert m.to_world("died_in") == ("involved_in", "died_in")
    assert m.to_world("enemy_of") == (None, "")                         # hors schéma : l'auteur décide
    assert m.to_world("near") == (None, "")                             # jamais ramenée à located_in


def test_pivot_facts_are_mapped_to_the_world_and_the_prompt_is_stable_X_016():
    from support import base_world
    from worldkit.ingest.batch import extraction_context
    from worldkit.periphery.facts import Confirmed, FactFinder
    from worldkit.periphery.mentions import Window
    world = base_world()
    context = extraction_context(world, world.state())
    text = "Odon dirige le conseil. Il hait les Veilleurs."
    window = Window("notes", text, [(1, 0, len(text))], {1: text})
    entities = [Confirmed("odon", "Character", "Odon de Brume"), Confirmed("new:conseil", "Faction", "le conseil"),
                Confirmed("veilleurs", "MonasticOrder", "les Veilleurs")]
    adapter = FixedAdapter({"relations": [
        {"subject": "odon", "relation": "leader_of", "object": "new:conseil", "evidence": "Odon dirige le conseil."},
        {"subject": "odon", "relation": "hostile_to", "object": "veilleurs", "evidence": "Il hait les Veilleurs."}],
        "attributes": []})
    finder = FactFinder(adapter, PROFILE, pivot_map=load_map(VALMONT_MAP))
    facts = finder.find(window, entities, context.schema, world.state())
    assert [(f.draft["relation"], f.exact) for f in facts] == [("member_of", "leader_of"), ("hostile_to", "")]
    system, user = adapter.calls[0][:2]
    other_system, _ = finder.prompt(Window("b", "x", [(1, 0, 1)], {1: "x"}), entities[:1], context.schema)
    assert system == other_system  # même prompt système d'un document à l'autre : mis en cache
    assert "(MonasticOrder → Group)" in user and "enum" in str(adapter.calls[0][2])


class FixedAdapter:
    """Modèle simulé : rend toujours la même réponse et garde les appels."""

    def __init__(self, answer):
        self.answer, self.calls, self.meter = answer, [], None

    def complete(self, system, prompt, schema):
        self.calls.append((system, prompt, schema))
        return self.answer
