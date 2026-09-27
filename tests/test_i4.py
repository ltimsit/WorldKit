"""Jalon I4 : pipeline en étapes, banc de pipeline, coût des modèles (I-PIP-01, I-LLM-01 ; décisions I4).

Aucun vrai modèle : l'extracteur LLM est branché sur un adaptateur factice.
"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path

import pytest

from support import VALMONT
from test_llm import BESTIAIRE, PROFILE, FakeAdapter
from test_service import make_world, snapshot
from worldkit.ingest.batch import batch_documents, ingest
from worldkit.ingest.stages import PipelineArt
from worldkit.core.world import World
from worldkit.periphery.extraction import OracleExtractor
from worldkit.periphery.llm_extractor import LLMExtractor
from worldkit.service import Session, jobs
from worldkit.service import pipeline as P

BATCHES = str(VALMONT / "docs" / "batches.yaml")
GOLD = str(VALMONT / "gold")
ORACLE = {"batches": BATCHES, "oracle": GOLD}
TABLES = ["batches", "batch_documents", "document_versions", "passages", "new_entities", "supports", "proposals",
          "proposal_changes", "proposal_keys", "proposal_deps", "edits", "changes", "extraction_cache"]


def tables(db: Path) -> dict[str, list[str]]:
    w = World.open(db)
    try:
        return {t: sorted(map(repr, w.store.conn.execute(f"SELECT * FROM {t}").fetchall())) for t in TABLES}
    finally:
        w.close()


@pytest.fixture
def session(tmp_path):
    s = Session(make_world(tmp_path / "valmont.db"))
    yield s
    s.close()


# --- T1 : le pipeline découpé est l'ingestion (I-PIP-01) ---

def test_staged_pipeline_with_json_at_every_boundary_equals_ingest_on_all_batches_T1(tmp_path):
    direct = make_world(tmp_path / "direct.db")
    staged = make_world(tmp_path / "staged.db")
    w = World.open(direct)
    for b in ["b1", "b2", "b3", "b4", "b5", "b6", "b7", "b8"]:
        ingest(w, b, batch_documents(BATCHES, b), OracleExtractor(Path(GOLD)))
    w.close()
    with Session(staged) as s:
        for b in ["b1", "b2", "b3", "b4", "b5", "b6", "b7", "b8"]:
            r = s.call("pipeline.run", {"batch_id": b, **ORACLE, "to": "E3"})
            for first, last in (("E4", "E4"), ("E5", "E6"), ("E7", "E9")):
                art = json.loads(s.runs.artifact(r.trace.run_id)[1])  # passage par le JSON à chaque frontière
                r = s.call("pipeline.run", {"batch_id": b, "oracle": GOLD, "from": first, "to": last, "artifact": art})
                assert r.status == "ok", r.issues
            assert s.call("pipeline.save", {"input": r.trace.run_id}).status == "ok"
    assert tables(staged) == tables(direct)


def test_stages_e1_to_e9_write_nothing_but_the_extraction_cache(session):
    before = snapshot(session.db)
    r = session.call("pipeline.run", {"batch_id": "b4", **ORACLE})
    assert r.status == "ok" and r.output["proposals"] == ["b4.bestiaire-loup-de-cendre.p2.1",
                                                          "b4.bestiaire-loup-de-cendre.p3.1",
                                                          "b4.bestiaire-loup-de-cendre.p6.1"]
    assert snapshot(session.db) == before
    t = tables(session.db)
    assert t["batches"] == [] and t["proposals"] == [] and t["passages"] == [] and len(t["extraction_cache"]) == 6
    assert session.runs.artifact_stages(r.trace.run_id) == ["E1", "E2", "E3", "E4", "E5", "E6", "E7", "E8", "E9"]


def test_a_rerun_is_identical_stage_by_stage_I_PRI_05(session):
    a = session.call("pipeline.run", {"batch_id": "b4", **ORACLE}).trace.run_id
    b = session.call("pipeline.run", {"batch_id": "b4", **ORACLE}).trace.run_id
    diff = session.call("runs.diff", {"a": a, "b": b})
    assert diff.output["first_difference"] is None and diff.indicators == {"compared": 9, "different": 0}


def test_hand_written_drafts_injected_at_e5_need_no_extractor(session):
    """Décision I4 : injecter une entrée intermédiaire. Ici, p6 reçoit à la main une forme réduite."""
    r = session.call("pipeline.run", {"batch_id": "b4", **ORACLE, "to": "E4"})
    art = json.loads(session.runs.artifact(r.trace.run_id, "E4")[1])
    p6 = next(p for p in art["documents"][0]["passages"] if p["index"] == 6)
    p6["extraction"]["drafts"] = [{"op": "sheet_values", "of": "loup-de-cendre", "system": "system-b",
                                   "values": {"level": 9}}]
    r = session.call("pipeline.run", {"batch_id": "b4", "from": "E5", "to": "E9", "artifact": art})
    assert r.status == "ok"
    final = PipelineArt.model_validate_json(session.runs.artifact(r.trace.run_id)[1])
    p6_prop = next(p for p in final.proposals if p["passage"] == 6)
    assert [q["item"]["change"].get("value") for q in p6_prop["items"]][-1] == 9


def test_a_stage_cannot_start_without_what_it_needs(session):
    r = session.call("pipeline.run", {"batch_id": "b4", "from": "E5"})
    assert r.status == "error" and "artefact" in r.issues[0].message
    r = session.call("pipeline.run", {"batch_id": "b4", "batches": BATCHES})
    assert r.status == "error" and "extracteur" in r.issues[0].message
    r = session.call("pipeline.run", {"batch_id": "b4", **ORACLE, "to": "E9+"})
    assert r.status == "error" and "pipeline.save" in r.issues[0].message


# --- Coût des modèles (I-LLM-01) ---

@pytest.fixture
def fake(monkeypatch):
    adapter = FakeAdapter(BESTIAIRE)
    monkeypatch.setattr(P, "extractor_of", lambda oracle, profile, cfg: OracleExtractor(Path(oracle)) if oracle
                        else LLMExtractor(adapter, PROFILE))
    return adapter


LLM = {"batch_id": "b4", "batches": BATCHES, "profile": "fake"}


def test_no_model_call_without_confirmation_estimate_first(session, fake):
    est = session.call("pipeline.estimate", LLM)
    assert est.output["calls"] == 6 and est.output["cached"] == 0
    r = session.call("pipeline.run", LLM)
    assert r.status == "pending" and r.output["estimate"]["calls"] == 6 and fake.calls == []
    assert r.issues[0].rule == "I-LLM-01"


def test_the_cap_stops_cleanly_and_a_rerun_pays_only_the_rest(session, fake):
    r = session.call("pipeline.run", {**LLM, "confirm": True, "max_calls": 2})
    assert len(fake.calls) == 2 and r.indicators["llm_calls"] == 2
    assert any("plafond" in i.message for i in r.issues)
    art = PipelineArt.model_validate_json(session.runs.artifact(r.trace.run_id, "E4")[1])
    assert sum(1 for p in art.documents[0].passages if p.source == "cap") == 4
    r = session.call("pipeline.run", {**LLM, "confirm": True, "max_calls": 10})
    assert len(fake.calls) == 6 and r.indicators["cached"] == 2 and r.indicators["llm_calls"] == 4


def test_two_extractors_compared_stage_by_stage(session, fake):
    a = session.call("pipeline.run", {"batch_id": "b4", **ORACLE, "to": "E4"}).trace.run_id
    b = session.call("pipeline.run", {**LLM, "confirm": True, "to": "E4"}).trace.run_id
    d = session.call("runs.diff", {"a": a, "b": b}).output
    assert d["first_difference"] == "E4"
    e4 = next(s for s in d["stages"] if s["stage"] == "E4")
    assert any("sheet_values" in k for k in e4["only_b"]) and any("loup-de-cendre@system-b" in k for k in e4["only_a"])


def test_saving_an_llm_run_in_a_sandbox_then_promoting_calls_no_model(session, fake):
    r = session.call("pipeline.run", {**LLM, "confirm": True})
    calls = len(fake.calls)
    n = session.call("sandbox.create").output["id"]
    saved = session.call("pipeline.save", {"input": r.trace.run_id}, n)
    assert saved.status == "ok" and saved.indicators["proposals"] >= 1
    promoted = session.call("sandbox.promote", {"id": n, "confirm": True})
    assert promoted.status == "ok" and len(fake.calls) == calls  # extraction relue depuis l'artefact
    assert len(tables(session.db)["proposals"]) == saved.indicators["proposals"]


# --- Tâches de fond (décision I4) ---

class Slow(FakeAdapter):
    def complete(self, system, prompt, schema):
        time.sleep(0.15)
        return super().complete(system, prompt, schema)


def test_background_run_reports_progress_and_can_be_cancelled(tmp_path, monkeypatch):
    db = make_world(tmp_path / "valmont.db")
    adapter = Slow(BESTIAIRE)
    extractor = LLMExtractor(adapter, PROFILE)
    extractor.profile.options["concurrency"] = 1
    monkeypatch.setattr(P, "extractor_of", lambda *a: extractor)
    run_id = jobs.start(db, "pipeline.run", {**LLM, "confirm": True})
    with pytest.raises(ValueError):  # un seul pipeline avec modèle à la fois par monde
        jobs.start(db, "pipeline.run", {**LLM, "confirm": True})
    deadline = time.time() + 5
    with Session(db) as s:
        while s.runs.progress(run_id)[1].get("stage") != "E4" and time.time() < deadline:
            time.sleep(0.05)
        assert s.runs.progress(run_id)[0] == "running"
    jobs.cancel(db, run_id)
    jobs.wait(db, run_id, 10)
    with Session(db) as s:
        status, _ = s.runs.progress(run_id)
        result = s.runs.result(run_id)
    assert status in ("ok", "pending") and len(adapter.calls) < 6
    art = result.output["stages"]
    assert art[-1]["stage"] in ("E4", "E5", "E6", "E7", "E8", "E9")
    extractor.profile.options.pop("concurrency", None)


def test_a_run_left_running_by_a_dead_server_is_marked_interrupted(tmp_path):
    db = make_world(tmp_path / "valmont.db")
    with Session(db) as s:
        rid = s.runs.begin("pipeline.run", "compute", "world", {})
    assert jobs.mark_interrupted(db) == 1
    with Session(db) as s:
        assert s.runs.progress(rid)[0] == "interrupted"
        assert s.call("runs.show", {"id": rid}).status == "pending"


# --- Interface et ligne de commande ---

def test_pipeline_pages(tmp_path):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    from worldkit.web import create_app
    db = make_world(tmp_path / "valmont.db")
    c = TestClient(create_app(db))
    assert c.get("/pipeline").status_code == 200
    r = c.post("/pipeline", data={"batch_id": "b4", "batches": BATCHES, "oracle": GOLD, "extractor": "oracle",
                                  "from": "E1", "to": "E9"}, follow_redirects=False)
    run_id = int(r.headers["location"].rsplit("/", 1)[1])
    jobs.wait(db, run_id, 30)
    page = c.get(f"/pipeline/{run_id}").text
    assert "Enregistrer le lot" in page and page.count('class="added"') == 9
    assert "p6" in c.get(f"/runs/{run_id}/artifact/E9").text
    before = snapshot(db)
    saved = c.post(f"/pipeline/{run_id}/save", data={"to": "E12", "destination": "new"}).text
    assert "Écrit dans le" in saved and snapshot(db) == before  # nouveau bac par défaut
    assert c.get(f"/runs-diff?a={run_id}&b={run_id}").status_code == 200


def test_cli_run_stages_save_and_diff(tmp_path, capsys):
    from worldkit.cli import main
    db = make_world(tmp_path / "valmont.db")
    run = lambda *a: main(["--db", str(db), *a])
    assert run("run", "stages", "--batch", "b4", "--batches", BATCHES, "--oracle", GOLD, "--to", "E9") == 0
    out = capsys.readouterr().out
    assert "E9   Propositions" in out and "worldkit run save 1" in out
    assert run("run", "stages", "--batch", "b4", "--batches", BATCHES, "--oracle", GOLD, "--to", "E4") == 0
    assert run("runs-diff", "1", "2") == 0
    assert "identiques sur les étapes communes" in capsys.readouterr().out
    assert run("run", "save", "1", "--to", "E11") == 0
    assert "pipeline.save [write] → world : ok" in capsys.readouterr().out
