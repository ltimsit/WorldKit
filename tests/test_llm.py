"""J4 : adaptateurs LLM, profils, extracteur LLM, erreurs d'extraction, mesure T2 — sans vrai modèle.

T-LLM-01, T-ING-09, T-ING-17, T-ING-19. Les vrais modèles se mesurent avec `worldkit eval extraction`.
"""

from __future__ import annotations

import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from types import SimpleNamespace

import pytest
import yaml

from support import VALMONT, base_world
from worldkit.ingest.batch import batch_documents, extraction_context, ingest
from worldkit.ingest.queue import load
from worldkit.periphery.evaluation import evaluate
from worldkit.periphery.extraction import OracleExtractor
from worldkit.periphery.llm import (
    AnthropicApiAdapter, ClaudeCodeAdapter, LLMError, OllamaAdapter, Profile, load_config, parse_config,
)
from worldkit.periphery.llm_extractor import OUTPUT_SCHEMA, LLMExtractor

B1 = batch_documents(VALMONT / "docs" / "batches.yaml", "b1")
PROFILE = Profile("fake", "claude-code", "fake-model")


def change(op, **fields):
    base = {f: None for f in ("entity", "type", "attribute", "value", "from", "relation", "to", "target", "visibility")}
    return {**base, "op": op, **{k.rstrip("_"): v for k, v in fields.items()}}


class FakeAdapter:
    """Répond selon le début du passage ; compte les appels."""

    def __init__(self, answers, fail_first=0):
        self.answers, self.calls, self.fail_first = answers, [], fail_first

    def complete(self, system, prompt, schema):
        self.calls.append((system, prompt))
        if len(self.calls) <= self.fail_first:
            raise LLMError("panne simulée")
        passage = prompt.split("Passage :\n", 1)[1]
        for start, answer in self.answers.items():
            if passage.startswith(start):
                return answer
        return {"changes": [], "claims": [], "attribution": False}


NOTES = {
    "Odon de Brume est le baron": {"changes": [change("set_attribute", entity="odon", attribute="title", value="baron")],
                                   "claims": [], "attribution": False},
    "Dans les faits": {"changes": [
        change("create_entity", entity="new:conseil", type="Faction"),
        change("set_attribute", entity="new:conseil", attribute="name", value="le conseil des marchands"),
        change("add_relation", from_="new:conseil", relation="rules", to="brume")], "claims": [], "attribution": False},
    "« Le baron est un traître »": {"changes": [], "claims": [], "attribution": True},
}


# --- Configuration et profils ---

def test_default_config_routes_extraction_to_a_light_model():
    config = load_config()
    assert config.profile().model == "claude-haiku-4-5" and config.profile().adapter == "claude-code"
    assert config.profile("local").adapter == "ollama"


def test_config_file_routes_tasks_to_profiles(tmp_path):
    path = tmp_path / "llm.yaml"
    path.write_text(yaml.safe_dump({"profiles": {"s": {"adapter": "anthropic-api", "model": "claude-sonnet-5",
                                                       "effort": "low"}}, "tasks": {"extraction": "s"}}), "utf-8")
    profile = load_config(path).profile()
    assert (profile.model, profile.effort, profile.signature) == ("claude-sonnet-5", "low", "anthropic-api:claude-sonnet-5:low")
    with pytest.raises(LLMError):
        parse_config({"profiles": {"x": {"adapter": "gpt", "model": "m"}}})
    with pytest.raises(LLMError):
        parse_config({"profiles": {}, "tasks": {"extraction": "absent"}})


# --- Adaptateurs, sans réseau ---

def test_claude_code_adapter_builds_the_command_and_reads_structured_output(tmp_path):
    fake = tmp_path / "fake_claude.py"
    fake.write_text(
        "import json, sys\n"
        "args = sys.argv[1:]\n"
        "assert args[0] == '-p' and '--json-schema' in args and args[args.index('--tools') + 1] == ''\n"
        "prompt = sys.stdin.read()\n"
        "print(json.dumps({'is_error': False, 'subtype': 'success', 'structured_output': "
        "{'echo': prompt, 'model': args[args.index('--model') + 1]}}))\n", encoding="utf-8")
    adapter = ClaudeCodeAdapter("claude-haiku-4-5", command=[sys.executable, str(fake)])
    assert adapter.complete("système", "bonjour", {"type": "object"}) == {"echo": "bonjour", "model": "claude-haiku-4-5"}


def test_claude_code_adapter_reports_failures(tmp_path):
    fake = tmp_path / "fake_claude.py"
    fake.write_text("import json\nprint(json.dumps({'is_error': True, 'subtype': 'error', 'result': 'quota'}))\n",
                    encoding="utf-8")
    with pytest.raises(LLMError):
        ClaudeCodeAdapter("m", command=[sys.executable, str(fake)]).complete("s", "p", {})


def test_anthropic_api_adapter_uses_structured_outputs_and_cached_system():
    seen = {}

    def create(**kwargs):
        seen.update(kwargs)
        return SimpleNamespace(stop_reason="end_turn", content=[SimpleNamespace(type="text", text='{"ok": true}')])

    adapter = AnthropicApiAdapter("claude-haiku-4-5", client=SimpleNamespace(messages=SimpleNamespace(create=create)))
    assert adapter.complete("système", "question", {"type": "object"}) == {"ok": True}
    assert seen["output_config"]["format"] == {"type": "json_schema", "schema": {"type": "object"}}
    assert seen["system"][0]["cache_control"] == {"type": "ephemeral"}


def test_anthropic_api_adapter_refusal_is_an_error():
    create = lambda **_: SimpleNamespace(stop_reason="refusal", content=[])  # noqa: E731
    adapter = AnthropicApiAdapter("m", client=SimpleNamespace(messages=SimpleNamespace(create=create)))
    with pytest.raises(LLMError):
        adapter.complete("s", "p", {})


def test_ollama_adapter_against_a_fake_server():
    received = {}

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            received.update(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
            body = json.dumps({"message": {"content": '{"ok": true}'}}).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        adapter = OllamaAdapter("qwen2.5:7b", base_url=f"http://127.0.0.1:{server.server_port}")
        assert adapter.complete("s", "p", {"type": "object"}) == {"ok": True}
        assert received["format"] == {"type": "object"} and received["messages"][0]["role"] == "system"
    finally:
        server.shutdown()


def test_ollama_unreachable_is_an_llm_error():
    with pytest.raises(LLMError):
        OllamaAdapter("m", base_url="http://127.0.0.1:9", timeout=2).complete("s", "p", {})


# --- Extracteur LLM ---

def test_llm_extractor_prompt_carries_schema_known_entities_and_voice():
    world = base_world()
    adapter = FakeAdapter({})
    extractor = LLMExtractor(adapter, PROFILE)
    ingest(world, "b2", batch_documents(VALMONT / "docs" / "batches.yaml", "b2"), extractor)
    system, prompt = adapter.calls[0]
    assert "rules : Character|Faction → Place (one_to_many)" in system
    assert "- odon (Character) : Odon de Brume" in prompt
    assert "in_world (énonciateur : chronique-de-la-chute)" in prompt


def test_llm_extractor_output_goes_through_the_core():
    world = base_world()
    report = ingest(world, "b1", B1, LLMExtractor(FakeAdapter(NOTES), PROFILE))
    views = {p.passage: p for p in load(world) if p.doc == "notes-baron"}
    assert "anomaly" in views[3].changes[2].tags  # le noyau qualifie, pas le modèle (T-ARC-03)
    assert [c.change.entity for c in views[3].changes[:1]] == ["conseil"]
    assert report.flagged["notes-baron p6"] == ["attribution"]
    assert len(report.supports) == 1  # « baron » : identique à l'état


def test_value_coercion_follows_the_declared_attribute_type():
    world = base_world()
    answers = {"Odon": {"changes": [change("set_attribute", entity="loup-de-cendre", attribute="flame_bearer",
                                           value="vrai")], "claims": [], "attribution": False}}
    extractor = LLMExtractor(FakeAdapter(answers), PROFILE)
    ex = extractor.extract("x", "Odon …", extraction_context(world, world.state()))
    assert ex.drafts[0]["value"] is True


def test_llm_failure_is_retried_then_marks_an_extraction_error_T_ING_17():
    world = base_world()
    adapter = FakeAdapter(NOTES, fail_first=1)
    ex = LLMExtractor(adapter, PROFILE).extract("x", "Odon de Brume est le baron", extraction_context(world, world.state()))
    assert len(adapter.calls) == 2 and ex.drafts
    broken = FakeAdapter({}, fail_first=10**6)
    report = ingest(world, "b1", B1[:1], LLMExtractor(broken, PROFILE))
    assert report.proposals == [] and len(report.errors) == 7
    assert all(f == ["extraction_error"] for f in report.flagged.values())
    assert world.store.conn.execute("SELECT COUNT(*) FROM extraction_cache").fetchone()[0] == 0  # rien en cache


def test_extractor_version_changes_with_the_model_T_ING_09():
    a = LLMExtractor(FakeAdapter({}), Profile("a", "claude-code", "claude-haiku-4-5"))
    b = LLMExtractor(FakeAdapter({}), Profile("b", "claude-code", "claude-sonnet-5"))
    assert a.version != b.version and a.version.startswith("llm-")


def test_output_schema_is_strict():
    assert OUTPUT_SCHEMA["additionalProperties"] is False
    item = OUTPUT_SCHEMA["properties"]["changes"]["items"]
    assert item["additionalProperties"] is False and set(item["required"]) == set(item["properties"])


# --- Mesure T2 ---

def test_oracle_measured_against_itself_is_perfect():
    world = base_world()
    oracle = OracleExtractor(VALMONT / "gold")
    report = evaluate(oracle, oracle, VALMONT / "gold", B1, extraction_context(world, world.state()), repeat=2)
    summary = report.summary()
    assert (summary["precision"], summary["recall"], summary["traps_fallen"], summary["stability"]) == (1.0, 1.0, 0, 1.0)


def test_measure_counts_misses_extras_and_traps():
    world = base_world()
    answers = {**NOTES, "Le Roi Gris régnait": {"changes": [
        change("create_entity", entity="new:roi-gris", type="Character"),
        change("set_attribute", entity="new:roi-gris", attribute="name", value="le Roi Gris")],
        "claims": [], "attribution": False}}
    report = evaluate(LLMExtractor(FakeAdapter(answers), PROFILE), OracleExtractor(VALMONT / "gold"),
                      VALMONT / "gold", B1, extraction_context(world, world.state()))
    summary = report.summary()
    assert summary["traps_fallen"] == 1 and 0 < summary["recall"] < 1
    lieux_p4 = next(r for r in report.passages if r.doc == "lieux-de-valmont" and r.index == 4)
    assert lieux_p4.traps and not (lieux_p4.found & lieux_p4.expected)


def test_batch_merges_new_entities_by_type_and_name_T_ING_07():
    """Deux passages extraits isolément créent chacun « le conseil » sous deux étiquettes : une seule entité."""
    world = base_world()
    answers = {**NOTES, "Odon siège lui-même": {"changes": [
        change("create_entity", entity="new:conseil-des-marchands", type="Faction"),
        change("set_attribute", entity="new:conseil-des-marchands", attribute="name", value="Le conseil des marchands"),
        change("add_relation", from_="odon", relation="member_of", to="new:conseil-des-marchands")],
        "claims": [], "attribution": False}}
    report = ingest(world, "b1", B1[:1], LLMExtractor(FakeAdapter(answers), PROFILE))
    assert [e.id for e in report.new_entities] == ["conseil"]
    p4 = next(p for p in load(world) if p.passage == 4)
    assert [c.change.op for c in p4.changes] == ["add_relation"] and p4.changes[0].change.to == "conseil"
    assert p4.depends_on == ["b1.notes-baron.p3.1"]


def test_irrelevant_fields_filled_by_the_model_are_dropped():
    world = base_world()
    noisy = {"Odon": {"changes": [change("set_attribute", entity="odon", type="Character", attribute="title",
                                         value="régent", relation="rules")], "claims": [], "attribution": False}}
    ex = LLMExtractor(FakeAdapter(noisy), PROFILE).extract("x", "Odon …", extraction_context(world, world.state()))
    assert ex.drafts == ({"op": "set_attribute", "entity": "odon", "attribute": "title", "value": "régent"},)
