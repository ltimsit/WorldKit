"""Adaptateurs LLM (T-LLM-01) : une seule interface, un adaptateur par fournisseur.

`complete(system, prompt, schema) → dict` : un appel, une réponse JSON conforme à `schema`.
La périphérie ne décide rien : la sortie est ensuite validée par le noyau (T-ING-17).

| Adaptateur | Accès | Usage |
|---|---|---|
| `claude-code` | abonnement Claude, via `claude -p` (Claude Code en mode non interactif) | usage personnel |
| `anthropic-api` | clé d'API dans `WORLDKIT_ANTHROPIC_API_KEY` (SDK officiel `anthropic`, sorties structurées) | facturé à l'usage |
| `ollama` | modèle local (`http://localhost:11434`) | rien ne quitte la machine |

Chaque adaptateur note l'usage de ses appels (tokens, durée, coût) dans `meter` (`usage.py`) : la mesure T2
en tire le coût et l'écart au budget d'entrée qui simule un petit modèle (chantier ingestion §8.2).
"""

from __future__ import annotations

import glob
import json
import os
import shutil
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from .usage import CallUsage, UsageMeter, cost_of


class LLMError(RuntimeError):
    """Échec d'un appel : réseau, refus, sortie absente ou non conforme."""


class LLMAdapter(Protocol):
    def complete(self, system: str, prompt: str, schema: dict[str, Any]) -> dict[str, Any]: ...


@dataclass(frozen=True)
class Profile:
    """Un modèle précis derrière un adaptateur, choisi par tâche (routage, configuration)."""

    name: str
    adapter: str
    model: str
    effort: str | None = None
    options: dict[str, Any] = field(default_factory=dict)

    @property
    def signature(self) -> str:
        temperature = self.options.get("temperature")  # l'échantillonnage change la sortie : il entre dans le cache
        return f"{self.adapter}:{self.model}" + (f":{self.effort}" if self.effort else "") \
            + (f":t{temperature}" if temperature is not None else "")


# ---------------------------------------------------------------------------
# Claude Code (abonnement)
# ---------------------------------------------------------------------------

# Lanceurs npm sous Windows : `claude.cmd` passe par cmd.exe, qui refuse une ligne de plus de 8 191 caractères.
_LAUNCHERS = (".cmd", ".bat", ".ps1")
_NPM_NATIVE = Path("node_modules") / "@anthropic-ai" / "claude-code" / "bin" / "claude.exe"

# Isolement de l'appel : ni serveurs MCP, ni compétences, ni réglages de l'utilisateur ou du projet. Sans lui,
# Claude Code ajoutait environ 34 000 tokens de contexte à chaque appel (mesure sur b1 : 39 000 contre 4 900).
# `--bare` irait plus loin mais exige une clé d'API : il ignore la connexion de l'abonnement.
ISOLATION = ("--strict-mcp-config", "--disable-slash-commands", "--setting-sources", "local")


def find_claude_code() -> list[str]:
    """Commande `claude` : variable WORLDKIT_CLAUDE_BIN, sinon le PATH, sinon le binaire de l'extension VS Code.

    Un lanceur npm (`claude.cmd`) est remplacé par le binaire natif qu'il lance, quand il existe."""
    explicit = os.environ.get("WORLDKIT_CLAUDE_BIN")
    if explicit:
        return [explicit]
    on_path = shutil.which("claude")
    if on_path and Path(on_path).suffix.lower() not in _LAUNCHERS:
        return [on_path]
    candidates = [Path(on_path).parent / _NPM_NATIVE] if on_path else []
    pattern = str(Path.home() / ".vscode" / "extensions" / "anthropic.claude-code-*" / "resources" / "native-binary"
                  / ("claude.exe" if os.name == "nt" else "claude"))
    candidates += [Path(p) for p in sorted(glob.glob(pattern), reverse=True)]
    for candidate in candidates:
        if candidate.is_file():
            return [str(candidate)]
    if on_path:
        return [on_path]
    raise LLMError("Claude Code introuvable : l'installer, ou indiquer son chemin dans WORLDKIT_CLAUDE_BIN")


@dataclass
class ClaudeCodeAdapter:
    """`claude -p` en mode non interactif, avec la connexion de l'utilisateur (abonnement).

    Aucun outil, aucune session conservée, notre prompt système à la place de celui de Claude Code ;
    la réponse structurée est lue dans le champ `structured_output`. Le prompt système passe par un
    fichier (aucune limite de longueur de ligne de commande) et l'appel tourne dans un dossier vide,
    isolé (`ISOLATION`) : aucun CLAUDE.md, aucune mémoire, aucun réglage n'entre dans le contexte.
    """

    model: str
    command: list[str] | None = None
    effort: str | None = None
    timeout: float = 300.0
    meter: UsageMeter = field(default_factory=UsageMeter)

    def complete(self, system: str, prompt: str, schema: dict[str, Any]) -> dict[str, Any]:
        executable = self.command or find_claude_code()
        start = time.perf_counter()
        with tempfile.TemporaryDirectory(prefix="worldkit-claude-") as neutral:
            prompt_file = Path(neutral) / "system.txt"
            prompt_file.write_text(system, encoding="utf-8")
            command = executable + [
                "-p", "--output-format", "json", "--json-schema", json.dumps(schema, ensure_ascii=False),
                "--model", self.model, "--system-prompt-file", str(prompt_file), "--tools", "",
                "--no-session-persistence", *ISOLATION]
            if self.effort:
                command += ["--effort", self.effort]
            env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}  # reste sur l'abonnement
            try:
                run = subprocess.run(command, input=prompt, capture_output=True, text=True, encoding="utf-8",
                                     timeout=self.timeout, cwd=neutral, env=env)
            except (OSError, subprocess.TimeoutExpired) as e:
                raise LLMError(f"claude -p : {e}") from e
        if run.returncode != 0:
            raise LLMError(f"claude -p a échoué ({run.returncode}) : {(run.stderr or run.stdout)[:300]}")
        try:
            result = json.loads(run.stdout)
        except json.JSONDecodeError as e:
            raise LLMError(f"claude -p : sortie illisible ({e})") from e
        if result.get("is_error") or not isinstance(result.get("structured_output"), dict):
            raise LLMError(f"claude -p : pas de sortie structurée ({result.get('subtype')}, "
                           f"{str(result.get('result'))[:200]})")
        u = result.get("usage") or {}
        read, write = int(u.get("cache_read_input_tokens") or 0), int(u.get("cache_creation_input_tokens") or 0)
        cost = result.get("total_cost_usd")  # coût équivalent à l'API, estimé par Claude Code (l'abonnement ne facture pas)
        self.meter.record(CallUsage(self.model, int(u.get("input_tokens") or 0) + read + write,
                                    int(u.get("output_tokens") or 0), read, write, time.perf_counter() - start,
                                    float(cost) if cost is not None else None))
        return result["structured_output"]


# ---------------------------------------------------------------------------
# API Anthropic (clé)
# ---------------------------------------------------------------------------

API_KEY_VARIABLES = ("WORLDKIT_ANTHROPIC_API_KEY", "ANTHROPIC_API_KEY")


def api_key() -> str:
    """La clé propre à worldkit d'abord : définir ANTHROPIC_API_KEY pour tout le compte ferait aussi passer
    Claude Code (et donc l'adaptateur claude-code) sur la facturation de l'API."""
    for name in API_KEY_VARIABLES:
        if os.environ.get(name):
            return os.environ[name]
    raise LLMError("clé d'API absente : la définir dans la variable d'environnement WORLDKIT_ANTHROPIC_API_KEY")


@dataclass
class AnthropicApiAdapter:
    """SDK officiel, sorties structurées (`output_config.format`) ; prompt système mis en cache.

    `temperature` n'est envoyée que si le profil la donne : Haiku 4.5 l'accepte, Sonnet 5 la refuse (400).
    `effort` est refusé par Haiku 4.5 : l'erreur est levée avant l'appel. `price` (dollars par million de tokens,
    `{input, output}`) donne le coût de chaque appel."""

    model: str
    effort: str | None = None
    client: Any = None
    max_tokens: int = 16000
    temperature: float | None = None
    price: dict[str, Any] | None = None
    meter: UsageMeter = field(default_factory=UsageMeter)

    def complete(self, system: str, prompt: str, schema: dict[str, Any]) -> dict[str, Any]:
        if self.effort and self.model.startswith("claude-haiku-4-5"):
            raise LLMError(f"{self.model} n'accepte pas « effort » : le retirer du profil")
        client = self.client
        if client is None:
            try:
                import anthropic
            except ImportError as e:
                raise LLMError("le paquet « anthropic » n'est pas installé (pip install anthropic)") from e
            client = self.client = anthropic.Anthropic(api_key=api_key())
        output_config: dict[str, Any] = {"format": {"type": "json_schema", "schema": schema}}
        if self.effort:
            output_config["effort"] = self.effort
        sampling = {"temperature": self.temperature} if self.temperature is not None else {}
        start = time.perf_counter()
        try:
            response = client.messages.create(
                model=self.model, max_tokens=self.max_tokens,
                system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
                messages=[{"role": "user", "content": prompt}], output_config=output_config, **sampling)
        except Exception as e:  # erreurs typées du SDK : réseau, 4xx, 5xx (déjà relancées par le SDK)
            raise LLMError(f"API Anthropic : {e}") from e
        u = getattr(response, "usage", None)
        if u is not None:
            read, write = getattr(u, "cache_read_input_tokens", 0) or 0, getattr(u, "cache_creation_input_tokens", 0) or 0
            total, out = (u.input_tokens or 0) + read + write, u.output_tokens or 0
            self.meter.record(CallUsage(self.model, total, out, read, write, time.perf_counter() - start,
                                        cost_of(self.price, total, out, read, write)))
        if response.stop_reason in ("refusal", "max_tokens"):
            raise LLMError(f"API Anthropic : réponse interrompue ({response.stop_reason})")
        text = next((b.text for b in response.content if b.type == "text"), None)
        if text is None:
            raise LLMError("API Anthropic : aucune réponse texte")
        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            raise LLMError(f"API Anthropic : JSON illisible ({e})") from e


# ---------------------------------------------------------------------------
# Ollama (local)
# ---------------------------------------------------------------------------

@dataclass
class OllamaAdapter:
    """Modèle local via l'API HTTP d'Ollama ; sortie contrainte par le schéma (`format`)."""

    model: str
    base_url: str = "http://localhost:11434"
    timeout: float = 600.0
    meter: UsageMeter = field(default_factory=UsageMeter)

    def complete(self, system: str, prompt: str, schema: dict[str, Any]) -> dict[str, Any]:
        body = json.dumps({"model": self.model, "stream": False, "format": schema, "options": {"temperature": 0},
                           "messages": [{"role": "system", "content": system},
                                        {"role": "user", "content": prompt}]}).encode("utf-8")
        request = urllib.request.Request(f"{self.base_url.rstrip('/')}/api/chat", data=body,
                                         headers={"Content-Type": "application/json"})
        start = time.perf_counter()
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, OSError, json.JSONDecodeError) as e:
            raise LLMError(f"Ollama ({self.base_url}) : {e}") from e
        self.meter.record(CallUsage(self.model, int(payload.get("prompt_eval_count") or 0),
                                    int(payload.get("eval_count") or 0), seconds=time.perf_counter() - start,
                                    cost=0.0))  # local : rien n'est facturé
        try:
            return json.loads(payload["message"]["content"])
        except (KeyError, TypeError, json.JSONDecodeError) as e:
            raise LLMError(f"Ollama : réponse inattendue ({e})") from e


ADAPTERS = {"claude-code", "anthropic-api", "ollama"}


def make_adapter(profile: Profile) -> LLMAdapter:
    if profile.adapter == "claude-code":
        return ClaudeCodeAdapter(profile.model, command=profile.options.get("command"), effort=profile.effort)
    if profile.adapter == "anthropic-api":
        temperature = profile.options.get("temperature")
        return AnthropicApiAdapter(profile.model, profile.effort,
                                   temperature=float(temperature) if temperature is not None else None,
                                   price=profile.options.get("price"))
    if profile.adapter == "ollama":
        return OllamaAdapter(profile.model, profile.options.get("base_url", "http://localhost:11434"))
    raise LLMError(f"adaptateur inconnu : {profile.adapter} (attendu : {', '.join(sorted(ADAPTERS))})")
