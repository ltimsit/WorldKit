"""Jalon I5, interface : écran de revue (session du monde de travail) et écran d'acceptation.

I-VUE-05, I-ACC-01, I-PRI-04 ; décision I5 : la revue décide sur la cible affichée, le monde de travail demande une
session de revue confirmée une fois, limitée dans le temps.
"""

from __future__ import annotations

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from support import VALMONT  # noqa: E402
from test_service import make_world, snapshot  # noqa: E402
from worldkit.service import Session, jobs  # noqa: E402
from worldkit.web import create_app  # noqa: E402

BATCHES = str(VALMONT / "docs" / "batches.yaml")
GOLD = str(VALMONT / "gold")


@pytest.fixture
def world(tmp_path):
    db = make_world(tmp_path / "valmont.db")
    with Session(db) as s:
        for b in ("b1", "b4"):
            assert s.call("ingest.batch", {"batch_id": b, "batches": BATCHES, "oracle": GOLD}).ok
    return db, TestClient(create_app(db))


def test_review_lists_questions_flags_and_proposals(world):
    _, c = world
    page = c.get("/review").text
    assert "Questions de nature (1)" in page and "bestiaire-loup-de-cendre p6" in page
    assert "attribution" in page and "b1.notes-baron.p3.1" in page and "lecture" in page


def test_the_working_world_needs_a_confirmed_review_session_I_PRI_04(world):
    db, c = world
    before = snapshot(db)
    refused = c.post("/review/decide", data={"action": "refuse", "proposal": "b1.notes-baron.p7.1"}).text
    assert "ouvrir une session de revue" in refused and snapshot(db) == before
    c.post("/review/session", data={})  # sans la case : rien
    assert "Revoir dans le monde de travail" in c.get("/review").text
    c.post("/review/session", data={"confirm_world": "1"})
    assert "Session de revue du monde de travail ouverte" in c.get("/review").text
    c.post("/review/decide", data={"action": "accept", "proposal": "b1.notes-baron.p3.1", "total": "3",
                                   "keep": ["0", "1"]})
    with Session(db) as s:
        assert "conseil-marchands" in s.open().state().entities
    c.post("/review/session", data={"stop": "1"})
    assert "ouvrir une session" in c.post("/review/decide", data={"action": "refuse",
                                                                    "proposal": "b1.notes-baron.p7.1"}).text


def test_decisions_in_a_sandbox_apply_directly_and_leave_the_world_alone(world):
    db, c = world
    with Session(db) as s:
        n = str(s.call("sandbox.create").output["id"])
    before = snapshot(db)
    c.post("/review/decide", data={"target": n, "action": "nature", "document": "bestiaire-loup-de-cendre",
                                   "passage": "6", "decision": "accept"})
    r = c.post("/review/decide", data={"target": n, "action": "accept", "proposal": "b4.bestiaire-loup-de-cendre.p6.1",
                                       "total": "3", "keep": ["0", "1", "2"]})
    assert "Dernière décision" in r.text
    assert snapshot(db) == before
    assert "system-b (Monster)" in c.get(f"/wiki/loup-de-cendre?target={n}").text


def test_acceptance_screen_runs_a_walkthrough_and_shows_each_expectation(world):
    db, c = world
    listing = c.get("/acceptance").text
    assert "W15" in listing and "exécuter" in listing
    r = c.post("/acceptance", data={"id": "W08"}, follow_redirects=False)
    run_id = int(r.headers["location"].rsplit("/", 1)[1])
    jobs.wait(db, run_id, 120)
    page = c.get(f"/acceptance/{run_id}").text
    assert "4 réussi(s)" in page and "0 échoué(s)" in page and "W01" in page and "réussi" in page
