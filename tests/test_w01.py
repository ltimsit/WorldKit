"""Parcours W01 — état de base et vues (J2).

R-FAI-03, R-LLM-01, R-HIS-02, R-VUE-01, R-VUE-02, R-NOT-03, R-NOT-04, R-IDT-03, R-IDT-05, R-MET-06, R-FAI-05.
"""

from __future__ import annotations

import json

import pytest

from support import base_world
from worldkit.core.projection.serialize import state_to_json
from worldkit.core.schema import IssueCode
from worldkit.core.views import Filter, View, export_graph, render_page, state_report


@pytest.fixture(scope="module")
def world():
    w = base_world()
    yield w
    w.close()


@pytest.fixture(scope="module")
def state(world):
    return world.state(point="@base")


def author(state):
    return View(state, Filter.AUTHOR)


def player(state):
    return View(state, Filter.PLAYER)


def names(lines):
    return {(line.name, line.value) for line in lines}


def rels(page):
    return {(r.direction, r.relation, r.other) for r in page.relations}


def test_w01_projection_is_deterministic_R_HIS_02(world):
    """Rejouer e000–e006 deux fois donne deux états identiques ; la tête en cache aussi (T1)."""
    first, second = world.replay(), world.replay()
    assert state_to_json(first) == state_to_json(second) == state_to_json(world.state())


def test_w01_author_brume_ruled_by_odon(state):
    page = author(state).page("brume")
    assert ("in", "rules", "odon") in rels(page)
    assert "Odon de Brume (`odon`) rules" in render_page(page, author(state))


def test_w01_author_aldren_closed_poisoned_killed_by_mervin(state):
    page = author(state).page("aldren-ii")
    assert page.closed
    assert ("death_cause", "poison") in names(page.attributes)
    assert ("in", "killed", "mervin") in rels(page)


def test_w01_player_aldren_closed_without_secrets_R_NOT_03(state):
    """La clôture suit la notoriété de l'entité (décision J2) ; cause et meurtrier restent secrets."""
    page = player(state).page("aldren-ii")
    assert page.closed
    assert "death_cause" not in {a.name for a in page.attributes}
    assert not any(r.relation == "killed" for r in page.relations)


def test_w01_player_mervin_not_member_of_the_circle_R_NOT_04(state):
    """Fait non qualifié, et propagation depuis une entité secrète : invisible."""
    page = player(state).page("mervin")
    assert not any(r.relation == "member_of" for r in page.relations)
    assert any(r.relation == "member_of" and r.other == "cercle-des-cendres" for r in author(state).page("mervin").relations)


def test_w01_player_has_no_page_for_the_circle(state):
    assert player(state).page("cercle-des-cendres") is None
    assert "cercle-des-cendres" not in player(state).entity_ids()
    assert "cercle-des-cendres" in author(state).entity_ids()


def test_w01_player_corvin_and_brother_ash_are_distinct_R_IDT_03(state):
    corvin, brother = player(state).page("corvin"), player(state).page("frere-cendre")
    assert corvin.members == ["corvin"] and brother.members == ["frere-cendre"]
    assert corvin.identities == [] and brother.identities == []


def test_w01_author_consolidated_page_with_provenance_R_IDT_05(state):
    page = author(state).page("corvin")
    assert page.members == ["corvin", "frere-cendre"]
    assert {(a.entity, a.name, a.value) for a in page.attributes} >= {
        ("corvin", "name", "Corvin"), ("frere-cendre", "name", "Frère Cendre")}
    assert all(a.provenance for a in page.attributes) and all(r.provenance for r in page.relations)
    assert [(i.other, i.kind) for i in page.identities] == [("frere-cendre", "revelation")]


def test_w01_missing_system_b_sheet_and_conforming_system_a_sheet_R_MET_06(state):
    issues = state_report(state)
    assert [(i.code, i.path) for i in issues] == [(IssueCode.MISSING_SHEET, "loup-de-cendre@system-b")]
    sheets = author(state).page("loup-de-cendre").sheets
    assert [(s.system, s.category) for s in sheets] == [("system-a", "Creature")]
    assert ("hp", 5) in names(sheets[0].attributes)


def test_w01_fact_keys_occupied(state):
    """(rules, brume) occupée par odon ; (veilleurs, vows, silence) est une clé à part entière."""
    assert state.occupancy[("rel_to", "rules", "brume")] == ("rel", "odon", "rules", "brume")
    assert ("value", "veilleurs", "vows", "silence") in state.occupancy


def test_w01_diegetic_window_kept_without_effect_R_FAI_03(world, state):
    e003 = world.store.edit("e003").edit
    kept = [c for c in e003.changes if getattr(c, "relation", None) == "rules" and c.from_ == "mervin"]
    assert kept[0].diegetic_window == {"from": "an 1492"}
    assert state.facts[("rel", "mervin", "rules", "valmont")].diegetic_window == {"from": "an 1492"}
    assert ("out", "rules", "valmont") in rels(player(state).page("mervin"))


def test_w01_player_llm_export_leaks_nothing_R_LLM_01(state):
    graph = export_graph(state, Filter.PLAYER)
    text = json.dumps(graph, ensure_ascii=False)
    for secret in ("poison", "cercle-des-cendres", "killed", "same_as", "revelation", "worships", "system-a"):
        assert secret not in text
    assert graph["identities"] == []
    assert {"from": "odon", "relation": "rules", "to": "brume"} in graph["relations"]
