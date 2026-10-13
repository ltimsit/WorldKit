"""Choisir le profil de modèle depuis l'interface (I-LLM-02) : par défaut pour toutes les tâches (en-tête, écrit
dans worldkit-llm.yaml), ou pour un seul lancement (atelier, pipeline, mesures)."""

from __future__ import annotations

import pytest
import yaml

from worldkit.periphery.llm import LLMError, load_config, routing, write_routing
from worldkit.service.session import Session

CONFIG = """# Profils de modèles (commentaire de l'auteur)
profiles:
  api-haiku:  { adapter: anthropic-api, model: claude-haiku-4-5, temperature: 0 }
  qwen3-4b:   { adapter: ollama, model: qwen3:4b, num_ctx: 16384, concurrency: 1 }
tasks:
  extraction: api-haiku   # toutes les tâches retombent sur celui-ci
max_calls_per_run: 12
"""


@pytest.fixture
def config(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)  # worldkit-llm.yaml du dossier courant, comme le serveur
    path = tmp_path / "worldkit-llm.yaml"
    path.write_text(CONFIG, encoding="utf-8")
    return path


def test_routing_rewrites_only_the_tasks_block_I_LLM_02(config):
    assert routing(load_config())["facts"] == "api-haiku"  # repli sur l'extraction
    write_routing({"extraction": "qwen3-4b", "mentions": "qwen3-4b"})
    text = config.read_text(encoding="utf-8")
    assert "# Profils de modèles (commentaire de l'auteur)" in text and "num_ctx: 16384" in text
    raw = yaml.safe_load(text)
    assert raw["tasks"] == {"extraction": "qwen3-4b", "mentions": "qwen3-4b"} and raw["max_calls_per_run"] == 12
    assert routing(load_config()) == {t: "qwen3-4b" for t in ("extraction", "mentions", "facts", "notes")}


def test_an_unknown_profile_or_task_writes_nothing(config):
    with pytest.raises(LLMError, match="profil inconnu"):
        write_routing({"extraction": "gpt"})
    with pytest.raises(LLMError, match="tâche inconnue"):
        write_routing({"résumé": "qwen3-4b"})
    assert config.read_text(encoding="utf-8") == CONFIG


def test_without_a_file_the_default_configuration_is_written(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    write_routing({"extraction": "local"})
    assert load_config().profile().model == "qwen2.5:7b"


def test_llm_operations_list_and_route(config, tmp_path):
    from test_service import make_world
    db = make_world(tmp_path / "valmont.db")
    with Session(db) as s:
        listed = s.call("llm.profiles")
        assert [p["name"] for p in listed.output["profiles"]] == ["api-haiku", "qwen3-4b"]
        routed = s.call("llm.route", {"profile": "qwen3-4b"})
        assert routed.ok and set(routed.output["tasks"].values()) == {"qwen3-4b"}
        assert s.call("llm.route", {"profile": "absent"}).status == "refused"
        assert s.call("llm.route", {"profile": "api-haiku", "tasks": ["facts"]}).output["tasks"]["facts"] == "api-haiku"


def test_header_selector_routes_every_task_and_comes_back_I_LLM_02(config, tmp_path):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    from test_service import make_world
    from worldkit.web import create_app

    c = TestClient(create_app(make_world(tmp_path / "valmont.db")))
    page = c.get("/wiki").text
    assert 'action="/llm/route"' in page and "qwen3-4b — qwen3:4b" in page
    assert '<option value="api-haiku" selected>' in page  # toutes les tâches retombent sur api-haiku
    r = c.post("/llm/route", data={"profile": "qwen3-4b", "next": "/wiki?branch=reference"}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/wiki?branch=reference"
    assert set(routing(load_config()).values()) == {"qwen3-4b"}
    assert '<option value="qwen3-4b" selected>' in c.get("/wiki").text
    assert c.post("/llm/route", data={"profile": "absent"}).status_code == 400  # jamais muet (I-PRI-01)
    r = c.post("/llm/route", data={"profile": "qwen3-4b", "next": "//ailleurs.example"}, follow_redirects=False)
    assert r.headers["location"] == "/"  # retour dans l'application seulement
    write_routing({"facts": "api-haiku"})
    assert "(mixte)" in c.get("/wiki").text


def test_an_atelier_launch_takes_its_own_profile_I_LLM_02(config, tmp_path):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    from test_atelier import ROI
    from test_service import make_world
    from worldkit.web import create_app

    c = TestClient(create_app(make_world(tmp_path / "valmont.db")))
    doc_url = str(c.post("/atelier", data={"text": ROI}).url).split("testserver")[1]
    page = c.get(doc_url).text
    assert page.count('<select name="profile" title="profil du modèle pour ce lancement') == 3  # mentions, faits, descriptions
    estimate = c.post(doc_url + "/run", data={"model": "1", "profile": "qwen3-4b"}).text
    assert "qwen3:4b (profil qwen3-4b, ollama)" in estimate  # l'estimation dit quel modèle sera appelé
    assert '<input type="hidden" name="profile" value="qwen3-4b">' in estimate  # et la confirmation le garde
    assert set(routing(load_config()).values()) == {"api-haiku"}  # le défaut n'a pas bougé
