"""Atelier sans rechargement et suivi poussé des passes (I-WEB-04) : progression des couches, arrêt entre deux appels,
flux d'événements d'une exécution, zone de travail remplacée seule."""

from __future__ import annotations

import threading

import pytest

from test_atelier_faits import HAUNTS, MEMBER, NOTES, TITLE, FakeCritic, FakeFinder, facts_of, source_with_ostrel
from worldkit.atelier import layers


def test_the_facts_layer_announces_each_model_call_I_WEB_04():
    world, doc = source_with_ostrel()
    steps = []
    layers.run_facts(world, "reference", doc.doc_id, FakeFinder([MEMBER, TITLE]),
                     critic=FakeCritic({}), on_step=lambda stage, done, total: steps.append((stage, done, total)))
    assert steps[0] == ("c5", 0, 1)
    assert ("critic", 0, 1) in steps  # un seul fait à juger : le titre est un support, jamais jugé


def test_a_pass_stopped_between_two_calls_writes_nothing_I_WEB_04():
    world, doc = source_with_ostrel()

    def stop_at_critic(stage, done, total):
        if stage == "critic":
            raise RuntimeError("arrêt")
    with pytest.raises(RuntimeError):
        layers.run_facts(world, "reference", doc.doc_id, FakeFinder([MEMBER, HAUNTS]), critic=FakeCritic({}),
                         on_step=stop_at_critic)
    assert facts_of(world, doc) == []  # les annotations ne s'écrivent qu'à la fin de la passe
    assert layers.last_run(world, "reference", doc, layers.FACTS) == 0


def test_the_service_reports_a_stopped_pass_and_its_progress(tmp_path, monkeypatch):
    from test_service import make_world
    from worldkit.periphery import llm
    from worldkit.periphery.llm.usage import UsageMeter
    from worldkit.service.session import Session

    class Silent:  # n'est jamais appelé : l'arrêt est pris avant le premier appel
        meter = UsageMeter()

        def complete(self, *a, **k):
            raise AssertionError("aucun appel après un arrêt")
    monkeypatch.setattr(llm, "make_adapter", lambda profile: Silent())
    db = tmp_path / "valmont.db"
    make_world(db)
    with Session(db) as s:
        doc_id = s.call("atelier.import", {"text": NOTES}).output["doc_id"]
        s.call("atelier.run", {"doc_id": doc_id})
        stop = threading.Event()
        stop.set()
        result = s.call("atelier.run", {"doc_id": doc_id, "layer": "facts", "confirm": True}, cancel=stop)
    assert result.status == "ok" and result.output["stopped"] == "c5" and result.output["calls"] == 0
    assert "rien n'est écrit" in result.issues[0].message


# --- Écran et flux d'événements ---

def _client(db):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    from worldkit.web import create_app
    return TestClient(create_app(db))


def test_the_event_stream_of_a_finished_run_sends_its_state_then_done(tmp_path):
    from test_service import make_world
    from worldkit.service import jobs
    db = tmp_path / "valmont.db"
    make_world(db)
    client = _client(db)
    from worldkit.service.session import Session
    with Session(db) as s:
        doc_id = s.call("atelier.import", {"text": NOTES}).output["doc_id"]
    run_id = jobs.start(db, "atelier.run", {"doc_id": doc_id})  # sans modèle : finit aussitôt
    jobs.wait(db, run_id, 30)
    with client.stream("GET", f"/events/run/{run_id}") as response:
        assert response.headers["content-type"].startswith("text/event-stream")
        body = "".join(response.iter_text())
    assert body.index("event: progress") < body.index("event: done")
    assert '"status": "ok"' in body
    with client.stream("GET", "/events/run/9999") as response:
        assert '"status": "unknown"' in "".join(response.iter_text())


def test_the_atelier_swaps_its_work_area_only_and_follows_a_live_pass(tmp_path):
    from test_service import make_world
    from worldkit.service import jobs
    from worldkit.service.session import Session
    db = tmp_path / "valmont.db"
    make_world(db)
    with Session(db) as s:
        doc_id = s.call("atelier.import", {"text": NOTES}).output["doc_id"]
        s.call("atelier.run", {"doc_id": doc_id})
    client = _client(db)
    page = client.get(f"/atelier/{doc_id}").text
    assert 'id="atelier-work"' in page and 'hx-select="#atelier-work"' in page and "show:none" in page
    assert 'http-equiv="refresh"' not in page  # plus de rechargement toutes les 3 s
    assert f'hx-push-url="/atelier/{doc_id}"' in page  # un geste ne pousse jamais l'adresse d'un POST (405)
    # Une passe en cours (simulée) : l'encart suit la progression et propose d'arrêter.
    with Session(db) as s:
        run_id = s.runs.begin("atelier.run", "write", "world", {"doc_id": doc_id, "layer": "facts"})
        s.runs.set_progress(run_id, {"stage": "critic", "label": "critique", "done": 1, "total": 3, "calls": 4})
    key = (str(db.resolve()), run_id)
    jobs.JOBS[key] = jobs.Job(run_id, db, "atelier.run", True)
    try:
        live = client.get(f"/atelier/{doc_id}?job={run_id}").text
        assert 'id="job-live"' in live and "critique, appel 2 sur 3" in live and "4 appel(s) faits" in live
        assert "Arrêter" in live
        stopped = client.post(f"/atelier/{doc_id}/cancel", data={"job": str(run_id)}, follow_redirects=False)
        assert stopped.status_code == 303 and jobs.JOBS[key].cancel.is_set()
    finally:
        jobs.JOBS.pop(key, None)


def test_a_gesture_still_answers_with_the_whole_page_for_htmx_to_select(tmp_path):
    """Le serveur ne change pas : htmx suit la redirection et ne garde que la zone de travail."""
    from test_service import make_world
    from worldkit.service.session import Session
    db = tmp_path / "valmont.db"
    make_world(db)
    with Session(db) as s:
        doc_id = s.call("atelier.import", {"text": NOTES}).output["doc_id"]
        s.call("atelier.run", {"doc_id": doc_id})
        view = s.call("atelier.view", {"doc_id": doc_id}).output
    ann = next(a for p in view["passages"] for a in p["annotations"])
    client = _client(db)
    answer = client.post(f"/atelier/{doc_id}/annotate", data={"ann_id": ann["id"], "action": "keep"},
                         headers={"HX-Request": "true"})
    assert answer.status_code == 200 and 'id="atelier-work"' in answer.text
