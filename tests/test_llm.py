"""J4 : adaptateurs LLM, profils, extracteur LLM, erreurs d'extraction, mesure T2 — sans vrai modèle.

T-LLM-01, T-ING-09, T-ING-17, T-ING-19. Les vrais modèles se mesurent avec `worldkit eval extraction`.
"""

from __future__ import annotations

import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
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
from worldkit.periphery.llm import adapters
from worldkit.periphery.llm.adapters import find_claude_code
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

def test_default_config_routes_extraction_to_a_light_model(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)  # sans le worldkit-llm.yaml personnel de l'auteur
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
        "import json, os, sys\n"
        "args = sys.argv[1:]\n"
        "assert args[0] == '-p' and '--json-schema' in args and args[args.index('--tools') + 1] == ''\n"
        "prompt = sys.stdin.read()\n"
        "system = open(args[args.index('--system-prompt-file') + 1], encoding='utf-8').read()\n"
        "print(json.dumps({'is_error': False, 'subtype': 'success', 'structured_output': "
        "{'echo': prompt, 'system': system, 'model': args[args.index('--model') + 1], 'args': args, "
        "'cwd_files': os.listdir('.')}}))\n", encoding="utf-8")
    adapter = ClaudeCodeAdapter("claude-haiku-4-5", command=[sys.executable, str(fake)])
    out = adapter.complete("système « long »", "bonjour", {"type": "object"})
    assert (out["echo"], out["system"], out["model"]) == ("bonjour", "système « long »", "claude-haiku-4-5")
    assert "--system-prompt" not in out["args"]  # le prompt passe par un fichier : aucune limite de ligne de commande


def test_claude_code_call_is_isolated_from_the_user_environment(tmp_path):
    """Ni MCP, ni compétences, ni réglages, ni CLAUDE.md : sans cela, ~34 000 tokens de contexte par appel."""
    fake = tmp_path / "fake_claude.py"
    fake.write_text(
        "import json, os, sys\n"
        "print(json.dumps({'is_error': False, 'structured_output': {'args': sys.argv[1:], 'cwd': os.getcwd(), "
        "'files': os.listdir('.')}}))\n", encoding="utf-8")
    out = ClaudeCodeAdapter("m", command=[sys.executable, str(fake)]).complete("s", "p", {})
    args = out["args"]
    assert "--strict-mcp-config" in args and "--disable-slash-commands" in args
    assert args[args.index("--setting-sources") + 1] == "local"
    assert out["files"] == ["system.txt"]  # dossier vide : aucun CLAUDE.md découvert
    assert not Path(out["cwd"]).exists()  # dossier temporaire supprimé après l'appel


def test_claude_code_stays_on_the_subscription_even_with_an_api_key(tmp_path, monkeypatch):
    """Claude Code utilise ANTHROPIC_API_KEY quand elle existe : l'appel ne doit pas basculer sur l'API."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    fake = tmp_path / "fake_claude.py"
    fake.write_text("import json, os\nprint(json.dumps({'is_error': False, 'structured_output': "
                    "{'key': os.environ.get('ANTHROPIC_API_KEY')}}))\n", encoding="utf-8")
    assert ClaudeCodeAdapter("m", command=[sys.executable, str(fake)]).complete("s", "p", {}) == {"key": None}


def test_api_key_prefers_the_worldkit_variable(monkeypatch):
    monkeypatch.delenv("WORLDKIT_ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(LLMError, match="WORLDKIT_ANTHROPIC_API_KEY"):
        adapters.api_key()
    monkeypatch.setenv("ANTHROPIC_API_KEY", "générale")
    assert adapters.api_key() == "générale"
    monkeypatch.setenv("WORLDKIT_ANTHROPIC_API_KEY", "propre")
    assert adapters.api_key() == "propre"


def test_npm_launcher_is_replaced_by_the_native_binary(tmp_path, monkeypatch):
    """`claude.cmd` passe par cmd.exe, limité à 8 191 caractères : on lui préfère le binaire qu'il lance."""
    monkeypatch.delenv("WORLDKIT_CLAUDE_BIN", raising=False)
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")  # aucune extension VS Code
    launcher = tmp_path / "npm" / "claude.cmd"
    launcher.parent.mkdir()
    launcher.write_text("@echo off", encoding="utf-8")
    monkeypatch.setattr(adapters.shutil, "which", lambda name: str(launcher))
    assert find_claude_code() == [str(launcher)]  # pas de binaire natif : le lanceur, faute de mieux
    native = launcher.parent / "node_modules" / "@anthropic-ai" / "claude-code" / "bin" / "claude.exe"
    native.parent.mkdir(parents=True)
    native.write_text("", encoding="utf-8")
    assert find_claude_code() == [str(native)]
    monkeypatch.setattr(adapters.shutil, "which", lambda name: str(tmp_path / "bin" / "claude"))
    assert find_claude_code() == [str(tmp_path / "bin" / "claude")]  # un vrai binaire sur le PATH est gardé
    monkeypatch.setenv("WORLDKIT_CLAUDE_BIN", "choisi")
    assert find_claude_code() == ["choisi"]


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
            body = json.dumps({"message": {"content": '{"ok": true}'}, "prompt_eval_count": 812,
                               "eval_count": 40}).encode()
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
        [call] = adapter.meter.calls
        assert (call.input_tokens, call.output_tokens, call.cost) == (812, 40, 0.0)
    finally:
        server.shutdown()


def test_ollama_unreachable_is_an_llm_error():
    with pytest.raises(LLMError):
        OllamaAdapter("m", base_url="http://127.0.0.1:9", timeout=2).complete("s", "p", {})


# --- Usage des appels et budget d'entrée (T-LLM-01 ; chantier ingestion §8.2) ---


def _api_response(input_tokens=1000, read=3000, write=0, output=200):
    usage = SimpleNamespace(input_tokens=input_tokens, cache_read_input_tokens=read,
                            cache_creation_input_tokens=write, output_tokens=output)
    return SimpleNamespace(stop_reason="end_turn", usage=usage,
                           content=[SimpleNamespace(type="text", text='{"ok": true}')])


def test_anthropic_api_adapter_records_usage_and_cost():
    adapter = AnthropicApiAdapter("claude-haiku-4-5", price={"input": 1.0, "output": 5.0},
                                  client=SimpleNamespace(messages=SimpleNamespace(create=lambda **_: _api_response())))
    adapter.complete("s", "p", {})
    [call] = adapter.meter.calls
    assert (call.input_tokens, call.cache_read_tokens, call.output_tokens) == (4000, 3000, 200)  # tout le prompt
    assert call.cost == pytest.approx((1000 * 1.0 + 3000 * 0.1 + 200 * 5.0) / 1e6)  # lecture du cache à 0,1


def test_temperature_is_sent_only_when_the_profile_gives_it():
    seen = []
    client = SimpleNamespace(messages=SimpleNamespace(create=lambda **kw: seen.append(kw) or _api_response()))
    AnthropicApiAdapter("claude-sonnet-5", client=client).complete("s", "p", {})  # Sonnet 5 refuse temperature
    AnthropicApiAdapter("claude-haiku-4-5", client=client, temperature=0.0).complete("s", "p", {})
    assert "extra_body" not in seen[0] and seen[1]["extra_body"] == {"temperature": 0.0}  # le SDK 1.x n'a plus ce paramètre
    profile = load_config(None).profile("api-haiku")
    adapter = adapters.make_adapter(profile)
    assert adapter.temperature == 0.0 and adapter.price == {"input": 1.0, "output": 5.0}
    assert profile.signature.endswith(":t0")  # l'échantillonnage entre dans la version de l'extracteur (cache)


def test_api_schema_stays_under_the_union_limit_and_restores_nulls():
    """L'API refuse plus de 16 champs de type union ; le schéma de l'extracteur en a 27 (chaîne ou null)."""
    from worldkit.periphery.llm.adapters import api_schema, api_value
    sent = json.dumps(api_schema(OUTPUT_SCHEMA))
    assert sent.count('"anyOf"') <= 16 and sent.count('"anyOf"') < json.dumps(OUTPUT_SCHEMA).count('"anyOf"')
    raw = {"changes": [{"op": "set_attribute", "entity": "odon", "type": "", "value": "baron", "values": None}],
           "claims": [{"text": "t", "claimed": {"op": "add_relation", "from": "odon", "entity": ""}}], "attribution": False}
    out = api_value(raw, OUTPUT_SCHEMA)
    assert out["changes"][0]["type"] is None and out["changes"][0]["value"] == "baron"
    assert out["claims"][0]["claimed"]["entity"] is None and out["claims"][0]["text"] == "t"


def test_haiku_refuses_effort_before_any_call():
    def create(**_):
        raise AssertionError("aucun appel ne doit partir")
    adapter = AnthropicApiAdapter("claude-haiku-4-5", "low", client=SimpleNamespace(messages=SimpleNamespace(create=create)))
    with pytest.raises(LLMError, match="effort"):
        adapter.complete("s", "p", {})


def test_claude_code_adapter_records_usage(tmp_path):
    fake = tmp_path / "fake_claude.py"
    fake.write_text("import json\nprint(json.dumps({'is_error': False, 'structured_output': {'ok': True}, "
                    "'total_cost_usd': 0.0042, 'usage': {'input_tokens': 9, 'cache_read_input_tokens': 4880, "
                    "'cache_creation_input_tokens': 0, 'output_tokens': 372}}))\n", encoding="utf-8")
    adapter = ClaudeCodeAdapter("m", command=[sys.executable, str(fake)])
    adapter.complete("s", "p", {})
    [call] = adapter.meter.calls
    assert (call.input_tokens, call.output_tokens, call.cost) == (4889, 372, 0.0042)


def test_input_budget_defaults_to_4000_and_is_set_by_environment(monkeypatch):
    from worldkit.periphery.llm import input_budget
    monkeypatch.delenv("WORLDKIT_LLM_INPUT_BUDGET", raising=False)
    assert input_budget() == 4000
    monkeypatch.setenv("WORLDKIT_LLM_INPUT_BUDGET", "8000")
    assert input_budget() == 8000
    monkeypatch.setenv("WORLDKIT_LLM_INPUT_BUDGET", "off")
    assert input_budget() is None


class MeteredAdapter(FakeAdapter):
    """Comme FakeAdapter, et note un appel dont l'entrée vaut `tokens`."""

    def __init__(self, answers, tokens):
        super().__init__(answers)
        from worldkit.periphery.llm import UsageMeter
        self.meter, self.tokens = UsageMeter(), tokens

    def complete(self, system, prompt, schema):
        from worldkit.periphery.llm import CallUsage
        self.meter.record(CallUsage("fake", self.tokens, 50, cost=0.001))
        return super().complete(system, prompt, schema)


def test_measure_reports_usage_and_budget_excess_per_passage(monkeypatch, caplog):
    """Le dépassement du budget d'entrée n'est pas refusé : signalé une fois, et mesuré (chantier §8.2)."""
    monkeypatch.setenv("WORLDKIT_LLM_INPUT_BUDGET", "4000")
    world = base_world()
    with caplog.at_level("WARNING", logger="worldkit.llm"):
        report = evaluate(LLMExtractor(MeteredAdapter(NOTES, 4889), PROFILE), OracleExtractor(VALMONT / "gold"),
                          VALMONT / "gold", B1, extraction_context(world, world.state()))
    usage, n = report.summary()["usage"], len(report.passages)
    assert (usage["calls"], usage["over_budget"], usage["max_excess"]) == (n, n, 889)
    assert usage["excess_tokens"] == 889 * n and usage["cost"] == pytest.approx(0.001 * n)
    assert all(r.usage["calls"] == 1 for r in report.passages)  # chaque appel rattaché à son passage
    assert sum("budget d'entrée" in m for m in caplog.messages) == 1
    oracle = OracleExtractor(VALMONT / "gold")
    assert "usage" not in evaluate(oracle, oracle, VALMONT / "gold", B1,
                                   extraction_context(world, world.state())).summary()


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


def test_measure_where_every_extraction_failed_says_so_T_ING_17():
    """Une précision de 0 sans aucune extraction réussie passerait pour un résultat : la mesure le signale."""
    world = base_world()
    broken = LLMExtractor(FakeAdapter({}, fail_first=10**6), PROFILE)
    report = evaluate(broken, OracleExtractor(VALMONT / "gold"), VALMONT / "gold", B1,
                      extraction_context(world, world.state()))
    assert report.all_failed and report.summary()["errors"] == len(report.passages)
    oracle = OracleExtractor(VALMONT / "gold")
    assert not evaluate(oracle, oracle, VALMONT / "gold", B1, extraction_context(world, world.state())).all_failed


def test_measure_duration_is_the_elapsed_time_not_the_sum_of_passages():
    """Les passages sont extraits en parallèle : additionner leurs durées compterait plusieurs fois le même temps."""
    world = base_world()
    oracle = OracleExtractor(VALMONT / "gold")
    report = evaluate(oracle, oracle, VALMONT / "gold", B1, extraction_context(world, world.state()))
    for p in report.passages:
        p.seconds = 10.0
    assert report.elapsed is not None and report.summary()["seconds"] == round(report.elapsed, 1) < 10


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


def test_optional_gold_changes_are_neutral_T_ING_19():
    """Facultatifs du gold : ni manqués quand ils manquent, ni en trop quand ils sont trouvés (chantier §9)."""
    world = base_world()
    taverne = [change("create_entity", entity="new:heron", type="Place"),
               change("set_attribute", entity="new:heron", attribute="name", value="la taverne du Héron"),
               change("add_relation", from_="new:heron", relation="located_in", to="brume")]
    category = [change("set_attribute", entity="new:heron", attribute="category", value="taverne")]
    passages = {}
    for answer in (taverne, taverne + category):
        report = evaluate(LLMExtractor(FakeAdapter({"La taverne du Héron": {
            "changes": answer, "claims": [], "attribution": False}}), PROFILE),
            OracleExtractor(VALMONT / "gold"), VALMONT / "gold", B1, extraction_context(world, world.state()))
        passages[len(answer)] = next(r for r in report.passages if r.doc == "lieux-de-valmont" and r.index == 3)
    without, with_category = passages[3], passages[4]
    assert len(without.optional) == 4 and without.expected <= without.found and not without.extra
    assert not with_category.extra and len(with_category.found & with_category.optional) == 1
    assert report.summary()["optional"] == "1/4"


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


# --- Méta (J8) : systèmes dans le prompt, formes réduites, mesure T2 ---

B4 = batch_documents(VALMONT / "docs" / "batches.yaml", "b4")


def meta_change(op, **fields):
    return {**change(op, **{k: v for k, v in fields.items() if k not in ("system", "min", "max", "values")}),
            "system": fields.get("system"), "min": fields.get("min"), "max": fields.get("max"),
            "values": fields.get("values")}


BESTIAIRE = {
    "[meta]Loup de cendre (système A)": {"changes": [meta_change(
        "sheet_values", entity="loup-de-cendre", system="system-a",
        values=[{"attribute": "hp", "value": "5"}, {"attribute": "strength", "value": "12"},
                {"attribute": "abilities", "value": "system-a:bite"}])], "claims": [], "attribution": False},
    "[meta]Dans le système A": {"changes": [meta_change(
        "schema_constraint", system="system-a", type="Creature", attribute="hp", min="1", max="10")],
        "claims": [], "attribution": False},
    "Système B : niveau 7": {"changes": [meta_change(
        "sheet_values", entity="loup-de-cendre", system="system-b",
        values=[{"attribute": "level", "value": "7"}, {"attribute": "threat", "value": "8"}])],
        "claims": [], "attribution": False},
}


def test_prompt_describes_the_systems_and_names_the_document_J8():
    world = base_world()
    adapter = FakeAdapter(BESTIAIRE)
    ingest(world, "b4", B4, LLMExtractor(adapter, PROFILE))
    system, user = next(c for c in adapter.calls if "Système B : niveau 7" in c[1])
    assert "Système de règles « system-b »" in system and "Monster" in system and "level" in system
    assert "Document : Le Loup de cendre" in user
    assert "system-a:bite" in user  # les éléments de système sont des entités connues


def test_reduced_meta_forms_become_the_same_proposals_as_the_oracle_J8():
    from worldkit.ingest.meta import open_questions
    from worldkit.ingest.review import supports
    world = base_world()
    ingest(world, "b4", B4, LLMExtractor(FakeAdapter(BESTIAIRE), PROFILE))
    keys = {s.key for s in supports(world)}
    assert ("attr", "loup-de-cendre@system-a", "hp") in keys and ("schema", "system-a", "type", "Creature", "hp") in keys
    assert ("value", "loup-de-cendre@system-a", "abilities", "system-a:bite") in keys
    assert [q[:2] for q in open_questions(world)] == [("bestiaire-loup-de-cendre", 6)]
    p6 = next(p for p in load(world) if p.passage == 6)
    created = p6.changes[0].change
    assert (created.op, created.entity, created.sheet.category) == ("create_entity", "loup-de-cendre@system-b", "Monster")
    assert [(c.change.attribute, c.change.value) for c in p6.changes[1:]] == [("level", 7), ("threat", 8)]


def test_meta_passages_are_measured_after_translation_J8():
    world = base_world()
    oracle = OracleExtractor(VALMONT / "gold")
    ctx = extraction_context(world, world.state())
    perfect = evaluate(oracle, oracle, VALMONT / "gold", B4, ctx, state=world.state())
    assert {3, 4, 6} <= {r.index for r in perfect.passages}
    assert (perfect.summary()["precision"], perfect.summary()["recall"]) == (1.0, 1.0)
    llm = evaluate(LLMExtractor(FakeAdapter(BESTIAIRE), PROFILE), oracle, VALMONT / "gold", B4, ctx, state=world.state())
    p6 = next(r for r in llm.passages if r.index == 6)
    assert p6.found == p6.expected  # sheet_values traduit = création de la fiche B, niveau, menace
    p4 = next(r for r in llm.passages if r.index == 4)
    assert p4.found == p4.expected and p4.found <= p4.supports


def test_numeric_value_of_an_attribute_unknown_to_the_system_stays_an_integer_J8():
    """Mesure réelle (Haiku, b4 p3) : « Constitution 13 » arrivait en chaîne, faute d'attribut déclaré."""
    from worldkit.periphery.llm_extractor import meta_draft
    world = base_world()
    draft = meta_draft(meta_change("sheet_values", entity="loup-de-cendre", system="system-a",
                                   values=[{"attribute": "constitution", "value": "13"},
                                           {"attribute": "note", "value": "rapide"}]), world.state().systems)
    assert draft["values"] == {"constitution": 13, "note": "rapide"}
