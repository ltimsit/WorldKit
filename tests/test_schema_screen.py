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


# --- Ajouter une relation au schéma (chantier §6.6, I-ATL-09) ---

def add(db, **params):
    with Session(db) as s:
        return s.call("schema.add_relation", params, record=False)


def test_adding_a_relation_previews_then_writes_on_confirmation_R_CYC_01(db):
    params = {"relation": "hates", "subject": "odon", "object": "mervin", "label": "déteste"}
    preview = add(db, **params)
    assert preview.status == "pending" and preview.output["from"] == ["Character"] == preview.output["to"]
    assert not any(r["name"] == "hates" for r in show(db).output["schema"]["relations"])  # rien d'écrit
    done = add(db, **params, confirm=True)
    assert done.ok and done.output["edit"] == "schema-hates"
    hates = next(r for r in show(db).output["schema"]["relations"] if r["name"] == "hates")
    assert hates["label"] == "déteste" and hates["provenance"] == "schema-hates"
    assert "existe déjà" in add(db, **params).issues[0].message


def test_an_invalid_relation_is_refused_before_anything_is_written(db):
    r = add(db, relation="hates", **{"from": ["Charactre"]}, to=["Character"], confirm=True)
    assert not r.ok and not any(x["name"] == "hates" for x in show(db).output["schema"]["relations"])
    assert not add(db, relation="hates", subject="odon", object="mervin", cardinality="beaucoup").ok


def test_adding_from_an_atelier_fact_attaches_the_fact_I_ATL_09(db):
    """« elle deteste les bateliers » : relation hors schéma `detests` ; l'auteur l'ajoute sous le nom `hates`, le
    fait est rattaché d'un geste et partira avec « Proposer »."""
    from worldkit.atelier import gestures, layers, store
    w = World.open(db)
    doc = store.import_source(w, "# Notes\n\nOdon de Brume déteste Mervin.\n")
    layers.run_mentions(w, "reference", doc.doc_id)
    gestures.fact_gesture(w, "reference", doc.doc_id, "add", passage=1,
                          draft={"op": "add_relation", "from": "odon", "relation": "detests", "to": "mervin"})
    fact = next(a for a in layers.effective(w, "reference", doc) if a.kind == "fact")
    w.close()
    r = add(db, relation="hates", subject="odon", object="mervin", label="déteste", doc_id=doc.doc_id,
            ann_id=fact.ann_id, confirm=True)
    assert r.ok and r.output["attached"]
    w = World.open(db)
    current = next(a for a in layers.effective(w, "reference", store.source(w, doc.doc_id)) if a.kind == "fact")
    assert current.value["draft"]["relation"] == "hates" and current.status == "corrected"
    w.close()


def atelier_with_out_of_schema_fact(db):
    from worldkit.atelier import gestures, layers, store
    w = World.open(db)
    doc = store.import_source(w, "# Notes\n\nOdon de Brume déteste Mervin.\n")
    layers.run_mentions(w, "reference", doc.doc_id)
    gestures.fact_gesture(w, "reference", doc.doc_id, "add", passage=1,
                          draft={"op": "add_relation", "from": "odon", "relation": "detests", "to": "mervin"})
    fact = next(a for a in layers.effective(w, "reference", doc) if a.kind == "fact")
    w.close()
    return doc, fact


def test_from_the_atelier_to_the_schema_and_back_I_ATL_09(db):
    """Panneau d'un fait hors schéma → formulaire prérempli (nom, types) → vérifier → confirmer → retour à
    l'atelier, fait rattaché."""
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    from urllib.parse import parse_qs, urlparse
    from worldkit.web import create_app
    doc, fact = atelier_with_out_of_schema_fact(db)
    client = TestClient(create_app(db))
    panel = client.get(f"/atelier/{doc.doc_id}?fact={fact.ann_id}").text
    link = re.search(r'href="(/schema/add\?[^"]+)">Ajouter une relation au schéma', panel).group(1)
    query = {k: v[0] for k, v in parse_qs(urlparse(link.replace("&amp;", "&")).query).items()}
    assert query["relation"] == "detests" and query["subject"] == "odon" and query["ann_id"] == str(fact.ann_id)
    form = client.get(link.replace("&amp;", "&")).text
    assert 'name="from" value="Character" checked' in form and 'name="to" value="Character" checked' in form
    data = {**query, "relation": "hates", "label": "déteste", "from": "Character", "to": "Character",
            "cardinality": "many_to_many"}
    checked = client.post("/schema/add", data={**data, "action": "check"}).text
    assert "Confirmer : écrire schema-hates au journal" in checked
    done = client.post("/schema/add", data={**data, "action": "confirm"}, follow_redirects=False)
    assert done.status_code == 303 and done.headers["location"] == query["back"]
    assert "déteste" in client.get(done.headers["location"]).text
    assert any(r["name"] == "hates" for r in show(db).output["schema"]["relations"])


def test_an_out_of_schema_change_in_the_review_links_to_the_form(db):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    from worldkit.atelier import propose
    from worldkit.web import create_app
    doc, _ = atelier_with_out_of_schema_fact(db)
    w = World.open(db)
    propose.propose(w, "reference", doc.doc_id)
    w.close()
    page = TestClient(create_app(db)).get("/review").text
    assert "ajouter au schéma…" in page and "relation=detests" in page


def test_export_round_trips_the_projected_schema_including_added_relations_R_SCH_03(db, tmp_path, capsys):
    """`worldkit schema export --out` : le fichier relu par le validateur redonne le schéma projeté (pour le
    reporter dans un monde d'auteur, `mondes/`)."""
    from worldkit.cli import main
    from worldkit.core.schema import load_schema
    assert add(db, relation="hates", subject="odon", object="mervin", label="déteste", confirm=True).ok
    for scope in (None, "system-a"):
        out = tmp_path / f"{scope or 'world'}.yaml"
        argv = ["--db", str(db), "schema", "export", "--out", str(out)] + (["--scope", scope] if scope else [])
        assert main(argv) == 0
        w = World.open(db)
        projected = w.state().world if scope is None else w.state().systems[scope]
        w.close()
        assert load_schema(out).model_dump() == projected.model_dump()
    assert "schema-hates" in capsys.readouterr().out
    assert "hates: " in (tmp_path / "world.yaml").read_text(encoding="utf-8")
