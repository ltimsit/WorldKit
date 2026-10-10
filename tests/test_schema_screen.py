"""Écran « Schéma » (I-VUE-12) : `schema.show`, `/schema`, `worldkit schema show`. Le schéma d'un état est sa
projection (R-SCH-03) : provenance relue dans le journal, schéma lu à un point."""

from __future__ import annotations

import re

import pytest

from test_service import make_world
from worldkit.core.world import World
from worldkit.service import Session

ON_RIVER = {"op": "schema_set_relation", "relation": "on_river",
            "definition": {"from": "Place", "to": "Place", "labels": {"fr": "au bord de"}}}


@pytest.fixture
def db(tmp_path):
    return make_world(tmp_path / "valmont.db")


def show(db, **params):
    with Session(db) as s:
        return s.call("schema.show", params, record=False)


def test_relations_say_from_which_types_to_which_R_SCH_01(db):
    o = show(db).output
    rules = next(r for r in o["schema"]["relations"] if r["name"] == "rules")
    assert rules["label"] == "gouverne" and rules["from"] == ["Character", "Faction"] and rules["to"] == ["Place"]
    assert rules["provenance"] == "e000" and rules["facts"] >= 1
    character = next(t for t in o["schema"]["types"] if t["name"] == "Character")
    assert character["label"] == "Personnage" and "title" in {a["name"] for a in character["attributes"]}
    assert "flowchart LR" in o["mermaid"] and re.search(r"Character -->\|gouverne\| Place", o["mermaid"])


def test_inherited_attributes_and_subtypes(db):
    o = show(db).output
    child = next(t for t in o["schema"]["types"] if t["extends"])
    parent = next(t for t in o["schema"]["types"] if t["name"] == child["extends"])
    assert child["name"] in parent["subtypes"] and child["ancestors"][0] == parent["name"]
    assert {a["name"] for a in child["inherited"]} >= {a["name"] for a in parent["attributes"]} - \
        {a["name"] for a in child["attributes"]}


def test_a_schema_edit_is_dated_and_absent_before_its_point_R_SCH_03(db):
    from worldkit.core.journal.models import parse_edit
    w = World.open(db)
    outcome = w.apply(parse_edit({"id": "s1", "origin": "enrichment", "changes": [ON_RIVER]}))
    assert outcome.ok, [str(i) for i in outcome.issues]
    w.close()
    now = next(r for r in show(db).output["schema"]["relations"] if r["name"] == "on_river")
    assert now["provenance"] == "s1" and now["label"] == "au bord de"
    assert not any(r["name"] == "on_river" for r in show(db, point="@base").output["schema"]["relations"])


def test_a_rule_system_and_its_required_sheets_R_MET_06(db):
    o = show(db, scope="system-a").output
    assert {t["name"] for t in o["schema"]["types"]} == {"Ability", "Creature"}
    assert {"world_type": "Creature", "system": "system-a", "category": "Creature"} in o["sheets"]
    hp = next(a for t in o["schema"]["types"] for a in t["attributes"] if a["name"] == "hp")
    assert (hp["min"], hp["max"], hp["required"]) == (1, 10, True)
    assert show(db, scope="nope").output is None


def test_the_screen_and_the_command(db, capsys):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    from worldkit.cli import main
    from worldkit.web import create_app
    page = TestClient(create_app(db)).get("/schema").text
    assert "gouverne" in page and 'class="mermaid"' in page and 'href="#type-Place"' in page
    assert "Fiches exigées" in TestClient(create_app(db)).get("/schema?scope=system-a").text
    assert main(["--db", str(db), "schema", "show"]) == 0
    assert "- gouverne (rules) : Character, Faction → Place · one_to_many" in capsys.readouterr().out
