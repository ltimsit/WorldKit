"""Jalon I6 : graphe et mesures T2 (cadre d'interface I-GRA-01, I-VUE-06, I-VUE-09 ; décisions I6).

Aucun vrai modèle : l'extracteur LLM est branché sur un adaptateur factice.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from support import VALMONT
from test_llm import BESTIAIRE, PROFILE, FakeAdapter
from test_service import make_world
from test_w15_replay import file_world, w15_changes
from worldkit.core.workflows import replay as R
from worldkit.periphery.extraction import OracleExtractor
from worldkit.periphery.llm_extractor import LLMExtractor
from worldkit.service import Session
from worldkit.service import pipeline as P

ALL = ["world", "system", "sheet", "identity", "claim", "document"]
BATCHES = str(VALMONT / "docs" / "batches.yaml")
GOLD = str(VALMONT / "gold")


@pytest.fixture
def session(tmp_path):
    s = Session(make_world(tmp_path / "valmont.db"))
    s.call("ingest.batch", {"batch_id": "b2", "batches": BATCHES, "oracle": GOLD})
    s.call("review.qualify", {"target": "b2.chronique-de-la-chute-extraits.p1.1", "value": "false"})
    yield s
    s.close()


# --- Graphe ---

def test_player_graph_shows_nothing_secret_or_unqualified_T1_R_NOT_03(session):
    g = session.call("graph.view", {"layers": ALL, "filter": "player"}).output
    assert g["nodes"] and all(n["visibility"] == "public" for n in g["nodes"])
    for e in g["edges"]:
        assert e.get("computed") or e["relation"] in ("asserts", "source") or e["effective"] == "public", e
    assert not any(e["relation"] == "killed" for e in g["edges"])
    for n in g["nodes"]:
        for a in n["attributes"]:
            assert a.get("visibility") in (None, "public") or a.get("effective") == "public" or n["layer"] == "claim"
    claim = next(n for n in g["nodes"] if n["layer"] == "claim" and "combattant" in str(n["attributes"][0]["value"]))
    assert claim["attributes"][1]["value"] is None  # la qualification n'est pas publique (R-DOC-07)


def test_author_graph_has_every_layer_with_computed_sheet_relations(session):
    g = session.call("graph.view", {"layers": ALL}).output
    layers = {n["layer"] for n in g["nodes"]}
    assert {"world", "system", "sheet", "claim"} <= layers
    rels = {e["relation"] for e in g["edges"]}
    assert {"has_sheet", "conforms_to", "counterpart_of", "asserts", "killed"} <= rels
    claim = next(n for n in g["nodes"] if n["layer"] == "claim" and "combattant" in str(n["attributes"][0]["value"]))
    assert claim["attributes"][1]["value"] == "false"


def test_neighbourhood_is_bounded_by_depth(session):
    zero = session.call("graph.view", {"entity": "aldren-ii", "depth": 0}).output
    one = session.call("graph.view", {"entity": "aldren-ii", "depth": 1}).output
    two = session.call("graph.view", {"entity": "aldren-ii", "depth": 2}).output
    assert [n["id"] for n in zero["nodes"]] == ["aldren-ii"] and zero["edges"] == []
    assert {n["id"] for n in one["nodes"]} == {"aldren-ii", "mervin", "corvin", "la-chute"}
    assert len(two["nodes"]) > len(one["nodes"])


def test_an_earlier_view_marks_what_is_redefined_later_R_VUE_03(tmp_path):
    with Session(make_world(tmp_path / "valmont.db")) as s:
        s.call("branch.create", {"name": "variante-mj", "point": "@base"})
        s.call("edit.apply", {"edit": {"id": "e201", "branch": "variante-mj", "origin": "redefinition",
                                       "redefinition": "point", "changes": [
                                           {"op": "remove_relation", "from": "odon", "relation": "rules", "to": "brume"},
                                           {"op": "add_relation", "from": "mervin", "relation": "rules", "to": "brume"}]}})
        g = s.call("graph.view", {"entity": "brume", "branch": "variante-mj", "point": "@base"}).output
    rules = next(e for e in g["edges"] if e["relation"] == "rules")
    assert rules["source"] == "odon" and "redefined_later" in rules["marks"]


def test_graph_compare_shows_the_aldren_retcon(tmp_path):
    db = tmp_path / "valmont.db"
    w = file_world(db)
    R.decide(w, R.start(w, w15_changes(), "e003").replay.id, "keep")
    w.close()
    with Session(db) as s:
        r = s.call("graph.compare", {"entity": "aldren-ii", "left": {"branch": "reference"},
                                     "right": {"branch": "reference-r1"}})
    status = {x["id"]: x["status"] for x in [*r.output["nodes"], *r.output["edges"]]}
    assert status["rel|mervin|killed|aldren-ii"] == "removed"
    aldren = next(n for n in r.output["nodes"] if n["id"] == "aldren-ii")
    assert aldren["status"] == "changed" and {"name": "death_cause", "before": "poison", "after": "fièvre"} in \
        aldren["changed_attributes"]


# --- Mesures T2 ---

def test_oracle_measured_against_itself_is_perfect_and_kept_in_history(session):
    r = session.call("eval.run", {"batch": ["b4"]})
    assert r.status == "ok" and (r.indicators["precision"], r.indicators["recall"]) == (1.0, 1.0)
    assert all(not p["missed"] and not p["extra"] for p in r.output["passages"])
    history = session.call("eval.history").output
    assert [h["run"] for h in history] == [r.trace.run_id] and history[0]["precision"] == 1.0


@pytest.fixture
def fake(monkeypatch):
    adapter = FakeAdapter(BESTIAIRE)
    monkeypatch.setattr(P, "extractor_of", lambda oracle, profile, cfg: OracleExtractor(Path(oracle)) if oracle
                        else LLMExtractor(adapter, PROFILE))
    return adapter


def test_a_model_measure_estimates_first_then_uses_the_cache(session, fake):
    pending = session.call("eval.run", {"batch": ["b4"], "profile": "fake"})
    assert pending.status == "pending" and pending.output["estimate"]["calls"] == 6 and fake.calls == []
    capped = session.call("eval.run", {"batch": ["b4"], "profile": "fake", "max_calls": 3})
    assert capped.status == "refused" and "plafond" in capped.issues[0].message and fake.calls == []
    done = session.call("eval.run", {"batch": ["b4"], "profile": "fake", "confirm": True})
    assert done.status == "ok" and len(fake.calls) == 6 and done.indicators["recall"] < 1.0
    again = session.call("eval.run", {"batch": ["b4"], "profile": "fake"})  # tout en cache : rien à confirmer
    assert again.status == "ok" and again.indicators["calls"] == 0 and len(fake.calls) == 6


def test_two_measures_compared_passage_by_passage(session, fake):
    a = session.call("eval.run", {"batch": ["b4"]}).trace.run_id
    b = session.call("eval.run", {"batch": ["b4"], "profile": "fake", "confirm": True}).trace.run_id
    c = session.call("eval.compare", {"a": a, "b": b}).output
    p3 = next(p for p in c["passages"] if p["index"] == 3)
    assert any("constitution" in x for x in p3["a_right"])  # l'oracle trouve la constitution, pas le faux modèle
    assert c["a"]["summary"]["recall"] == 1.0 and c["b"]["summary"]["recall"] < 1.0


# --- Interface ---

def test_graph_and_measures_pages(tmp_path):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    from worldkit.service import jobs
    from worldkit.web import create_app
    db = make_world(tmp_path / "valmont.db")
    c = TestClient(create_app(db))
    page = c.get("/graph?entity=aldren-ii&layer=world&filter=player").text
    assert "cytoscape(" in page and "aldren-ii" in page and "killed" not in page
    compared = c.get("/graph?compare=1&cmp.branch=reference&entity=aldren-ii")
    assert compared.status_code == 200 and "0 ajoutés" in compared.text  # même état des deux côtés
    r = c.post("/measures", data={"batch": ["b4"], "extractor": "oracle"}, follow_redirects=False)
    run_id = int(r.headers["location"].rsplit("/", 1)[1])
    jobs.wait(db, run_id, 60)
    assert "aucun écart" in c.get(f"/measures/{run_id}").text
    assert f'href="/measures/{run_id}"' in c.get("/measures").text
