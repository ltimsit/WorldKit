"""Lacunes L1, L2, L6 du corpus, tranchées avant J8.

- L1 : `counterpart_of`, du monde vers un système, au plus une contrepartie par système (R-MET-04).
- L2 : une fiche naît d'un seul changement qui porte son rattachement immuable ; une fiche par système
  (R-MET-01, R-MET-02) ; `has_sheet` et `conforms_to` sont calculées.
- L6 : la clé d'un élément de schéma est écrite par les seules éditions de schéma (R-FAI-05, R-SCH-03).
"""

from __future__ import annotations

import json

import pytest

from support import attr, base_world, edit, rel, unrel
from worldkit.core.conflicts import check_application
from worldkit.core.schema import IssueCode, fact_keys, parse_change
from worldkit.core.views import Filter, View, export_json

POWER = {"op": "schema_set_type", "scope": "system-b", "type": "Power",
         "definition": {"attributes": {"name": {"type": "text", "required": True}}}}


def power(entity: str, name: str) -> list[dict]:
    return [{"op": "create_entity", "scope": "system-b", "entity": entity, "type": "Power"},
            {"op": "set_attribute", "scope": "system-b", "entity": entity, "attribute": "name", "value": name}]


def sheet(entity: str, of: str, system: str, category: str) -> dict:
    return {"op": "create_entity", "entity": entity, "type": "Sheet",
            "sheet": {"of": of, "system": system, "category": category}}


@pytest.fixture
def world():
    w = base_world()
    yield w
    w.close()


def codes(outcome):
    return [(i.code, i.rule) for i in outcome.issues]


# --- L1 : contrepartie ---

def test_counterpart_key_is_per_system_L1(world):
    ctx = world.state().context()
    change = parse_change(rel("flamme-azur", "counterpart_of", "system-a:azure-flame"))
    assert fact_keys(change, ctx) == [("counterpart", "flamme-azur", "system-a")]
    assert ("counterpart", "flamme-azur", "system-a") in world.state().occupancy


def test_base_counterpart_is_no_longer_signalled_L1(world):
    assert world.store.edit("e006").edit  # e006 appliquée sans l'avertissement « provisoire »
    app = check_application([parse_change(rel("feu-sacre", "counterpart_of", "system-a:bite"))],
                            world.state(), "x")
    assert [i.code for i in app.issues] == [IssueCode.UNKNOWN_ENTITY]


def test_second_counterpart_in_the_same_system_collides_R_MET_04_R_FAI_05(world):
    world.apply(edit(*[{"op": "create_entity", "scope": "system-a", "entity": "sacred-fire", "type": "Ability"},
                       {"op": "set_attribute", "scope": "system-a", "entity": "sacred-fire", "attribute": "name",
                        "value": "Feu sacré"}], id="h1"))
    second = world.apply(edit(rel("flamme-azur", "counterpart_of", "system-a:sacred-fire"), id="h2"))
    assert codes(second) == [(IssueCode.KEY_COLLISION, "R-FAI-05")]
    replaced = world.apply(edit(unrel("flamme-azur", "counterpart_of", "system-a:azure-flame"),
                                rel("flamme-azur", "counterpart_of", "system-a:sacred-fire"), id="h3"))
    assert replaced.ok


def test_one_counterpart_per_system_and_a_shared_system_element_L1(world):
    assert world.apply(edit(POWER, *power("flamme-bleue", "Flamme bleue"),
                            rel("flamme-azur", "counterpart_of", "system-b:flamme-bleue"), id="h1")).ok
    # une capacité de système peut servir plusieurs éléments du monde (capacité générique)
    assert world.apply(edit(rel("loup-de-cendre", "counterpart_of", "system-a:azure-flame"), id="h2")).ok


def test_counterpart_goes_from_the_world_to_a_system_R_MET_04(world):
    backwards = check_application([parse_change(rel("system-a:azure-flame", "counterpart_of", "flamme-azur"))],
                                  world.state(), "x")
    assert [(i.code, i.rule) for i in backwards.issues] == [(IssueCode.INVALID_VALUE, "R-MET-04")] * 2
    world_to_world = check_application([parse_change(rel("flamme-azur", "counterpart_of", "brume"))],
                                       world.state(), "x")
    assert [(i.code, i.rule) for i in world_to_world.issues] == [(IssueCode.INVALID_VALUE, "R-MET-04")]


# --- L2 : fiches ---

def test_sheet_key_one_sheet_per_system_R_MET_02(world):
    ctx = world.state().context()
    change = parse_change(sheet("loup-a2", "loup-de-cendre", "system-a", "Creature"))
    assert fact_keys(change, ctx) == [("entity", "loup-a2"), ("sheet", "loup-de-cendre", "system-a")]
    values = [attr("loup-a2", a, v) for a, v in (("hp", 6), ("strength", 12), ("dexterity", 12),
                                                   ("intelligence", 10))]
    second = world.apply(edit(sheet("loup-a2", "loup-de-cendre", "system-a", "Creature"), *values, id="h1"))
    collision = [i for i in second.issues if i.code == IssueCode.KEY_COLLISION]
    assert [i.rule for i in collision] == ["R-FAI-05"] and "loup-de-cendre@system-a" in collision[0].message


def test_reclassifying_a_sheet_closes_it_and_creates_another_L2(world):
    """Le rattachement est immuable : reclasser = clore l'ancienne fiche et en créer une autre, dans la
    même édition ; l'ancienne reste dans l'histoire, la page ne montre que la fiche ouverte."""
    before = world.state()
    outcome = world.apply(edit({"op": "close_entity", "entity": "loup-de-cendre@system-b"}, id="h0"))
    assert not outcome.ok  # pas encore de fiche B à l'état de base
    b = [sheet("loup-de-cendre@system-b", "loup-de-cendre", "system-b", "Monster"),
         attr("loup-de-cendre@system-b", "level", 4)]
    assert world.apply(edit(*b, id="h1")).ok
    assert not world.apply(edit(sheet("loup-b2", "loup-de-cendre", "system-b", "Monster"),
                                attr("loup-b2", "level", 5), id="h2")).ok
    swap = world.apply(edit({"op": "close_entity", "entity": "loup-de-cendre@system-b"},
                            sheet("loup-b2", "loup-de-cendre", "system-b", "Monster"),
                            attr("loup-b2", "level", 5), id="h3"))
    assert swap.ok
    page = View(world.state(), Filter.AUTHOR).page("loup-de-cendre")
    assert sorted(s.sheet for s in page.sheets) == ["loup-b2", "loup-de-cendre@system-a"]
    assert world.state(point=before.seq).entities.get("loup-b2") is None


def test_has_sheet_and_conforms_to_are_computed_never_written_L2(world):
    for relation, target in (("has_sheet", "loup-de-cendre@system-a"), ("conforms_to", "system-a:bite")):
        src = "loup-de-cendre" if relation == "has_sheet" else "loup-de-cendre@system-a"
        refused = world.apply(edit(rel(src, relation, target), id=f"h-{relation}"))
        assert codes(refused) == [(IssueCode.INVALID_VALUE, "R-MET-01")]


def test_export_exposes_sheets_with_computed_relations_L2(world):
    graph = json.loads(export_json(world.state(), Filter.AUTHOR))
    assert [s["id"] for s in graph["sheets"]] == ["loup-de-cendre@system-a"]
    assert graph["sheets"][0]["attributes"]["hp"] == 5
    s = graph["sheets"][0]  # has_sheet (of) et conforms_to (system, category), calculées
    assert (s["of"], s["system"], s["category"]) == ("loup-de-cendre", "system-a", "Creature")
    assert not [r for r in graph["relations"] if r["relation"] in ("has_sheet", "conforms_to")]
    player = json.loads(export_json(world.state(), Filter.PLAYER))  # fiche non qualifiée : absente (R-NOT-03)
    assert player["sheets"] == []


# --- L6 : éléments de schéma ---

def test_ordinary_edits_do_not_read_schema_keys_L6(world):
    app = check_application([parse_change(attr("loup-de-cendre@system-a", "hp", 6))], world.state(), "x")
    assert not [k for k in app.effects.reads | app.effects.writes if k[0] == "schema"]
    patch = parse_change({"op": "schema_set_type", "scope": "system-a", "type": "Creature", "attribute": "hp",
                          "constraint": {"min": 6, "max": 10}})
    assert fact_keys(patch, world.state().context()) == [("schema", "system-a", "type", "Creature", "hp")]


def test_schema_dependency_is_checked_by_revalidation_not_by_keys_L6(world):
    """La borne passe à 6–10 : le Loup (hp 5) devient non conforme, signalé (R-SCH-10) ; écrire hp 5
    ailleurs est refusé par M1 (valeur invalide), sans qu'aucune clé de schéma ne soit lue."""
    from worldkit.core.views import state_report
    assert world.apply(edit({"op": "schema_set_type", "scope": "system-a", "type": "Creature", "attribute": "hp",
                             "constraint": {"min": 6, "max": 10}}, id="h1")).ok
    assert IssueCode.NON_CONFORMING in {i.code for i in state_report(world.state())}
    refused = check_application([parse_change(attr("loup-de-cendre@system-a", "hp", 5))], world.state(), "x")
    assert IssueCode.INVALID_VALUE in {i.code for i in refused.issues}
