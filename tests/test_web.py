"""Jalon I2 : application web locale, lecture seule (cadre d'interface I-TEC-01, I-INC-01 ; décisions I2).

I-PRI-01 à I-PRI-03, I-OBJ-06, I-OBJ-07 ; contexte dans l'adresse ; comparaison par le service (`wiki.compare`).
"""

from __future__ import annotations

import re

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from test_service import make_world, snapshot  # noqa: E402
from test_w15_replay import file_world, w15_changes  # noqa: E402
from worldkit.core.world import World  # noqa: E402
from worldkit.core.workflows import replay as R  # noqa: E402
from worldkit.service import Session  # noqa: E402
from worldkit.web import create_app  # noqa: E402
from worldkit.web.app import nest  # noqa: E402

PAGES = ["/", "/wiki", "/wiki/aldren-ii", "/wiki/aldren-ii?filter=player", "/branches", "/journal", "/edit/e003",
         "/runs", "/ops", "/compare/aldren-ii?left.filter=author&right.filter=player"]


@pytest.fixture
def world_db(tmp_path):
    return make_world(tmp_path / "valmont.db")


@pytest.fixture
def client(world_db):
    return TestClient(create_app(world_db))


def test_every_page_answers_and_lists_its_service_calls_I_PRI_03(client):
    for url in PAGES:
        r = client.get(url)
        assert r.status_code == 200, url
        assert "Appels au service pour cet écran" in r.text and "/api/call/" in r.text, url


def test_pages_work_on_a_sandbox_target(world_db):
    with Session(world_db) as s:
        s.call("sandbox.create", {"note": "essai"})
        s.call("edit.apply", {"edit": {"id": "x1", "origin": "enrichment", "changes": [
            {"op": "set_attribute", "entity": "odon", "attribute": "condition", "value": "Harassé-du-bac"}]}}, target=1)
    client = TestClient(create_app(world_db))
    assert "Harassé-du-bac" in client.get("/wiki/odon?target=1").text
    assert "Harassé-du-bac" not in client.get("/wiki/odon").text
    assert "bac 1 — essai" in client.get("/").text


def test_api_reads_refuses_writes_and_matches_the_service(client, world_db):
    r = client.get("/api/call/wiki.page", params={"entity": "aldren-ii", "filter": "player"})
    assert r.status_code == 200
    with Session(world_db) as s:
        direct = s.call("wiki.page", {"entity": "aldren-ii", "filter": "player"})
    body = r.json()
    body.pop("trace")
    assert body == direct.stable()
    assert client.get("/api/call/edit.apply", params={"edit.id": "x"}).status_code == 405
    assert client.get("/api/call/nope").status_code == 404
    assert client.get("/api/call/wiki.page").status_code == 400  # paramètre requis absent : erreur explicite
    assert client.post("/wiki/aldren-ii").status_code == 405


def test_player_view_shows_no_secret_R_NOT_03(client):
    player, author = client.get("/wiki/aldren-ii?filter=player").text, client.get("/wiki/aldren-ii").text
    assert "poison" in author and "poison" not in player
    assert "mervin" in author and "killed" not in player


def test_browsing_writes_nothing_and_records_no_run(client, world_db):
    before = snapshot(world_db)
    for url in PAGES:
        client.get(url)
    assert snapshot(world_db) == before
    with Session(world_db) as s:
        assert s.runs.runs() == []


def test_context_lives_in_the_address_and_names_stay_strings():
    assert nest({"branch": "7", "point": "12", "left.point": "@base", "passage": "6", "all": "true", "x": ""}) == \
        {"branch": "7", "point": "12", "left": {"point": "@base"}, "passage": 6, "all": True}


def test_compare_author_and_player_marks_what_players_do_not_see(client):
    r = client.get("/compare/aldren-ii?left.filter=author&right.filter=player")
    removed = re.findall(r'<tr class="removed">', r.text)
    assert len(removed) >= 3 and "poison" in r.text  # la colonne auteur garde les faits secrets


def test_compare_the_aldren_retcon_between_the_two_branches_W15(tmp_path):
    """Test humain d'I2, automatisé : relire le retcon d'Aldren entre `reference` (archivée) et `reference-r1`."""
    db = tmp_path / "valmont.db"
    w = file_world(db)
    report = R.start(w, w15_changes(), "e003")
    R.decide(w, report.replay.id, "keep")
    w.close()
    with Session(db) as s:
        result = s.call("wiki.compare", {"entity": "aldren-ii", "left": {"branch": "reference"},
                                         "right": {"branch": "reference-r1"}})
    diff = {(d["section"], d["status"]) for d in result.output["diff"]}
    assert ("attributes", "changed") in diff and ("relations", "removed") in diff
    changed = next(d for d in result.output["diff"] if d["status"] == "changed")
    assert (changed["left"]["value"], changed["right"]["value"]) == ("poison", "fièvre")
    page = TestClient(create_app(db)).get("/compare/aldren-ii?left.branch=reference&right.branch=reference-r1")
    assert page.status_code == 200 and '<tr class="changed">' in page.text and "fièvre" in page.text
    branches = TestClient(create_app(db)).get("/branches").text
    assert "reference-r1" in branches and "archived" in branches and "r1" in branches


def test_serve_command_refuses_a_missing_world(tmp_path, capsys):
    from worldkit.cli import main
    assert main(["--db", str(tmp_path / "absent.db"), "serve", "--no-browser"]) == 2
    assert "introuvable" in capsys.readouterr().out


def test_navigation_errors_are_never_silent_and_the_server_says_its_version(client):
    page = client.get("/").text
    assert 'id="htmx-error"' in page and "htmx:responseError" in page and "htmx:sendError" in page
    assert "serveur démarré à" in page and "worldkit " in page
