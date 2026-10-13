"""Profils de modèles et routage par tâche (T-LLM-01 : le choix se fait par étape, sur mesures).

Fichier YAML (par défaut `worldkit-llm.yaml` dans le dossier courant), par exemple :

    profiles:
      haiku:     { adapter: claude-code, model: claude-haiku-4-5 }
      sonnet:    { adapter: claude-code, model: claude-sonnet-5 }
      api-haiku: { adapter: anthropic-api, model: claude-haiku-4-5, temperature: 0, price: { input: 1.0, output: 5.0 } }
      local:     { adapter: ollama, model: qwen2.5:7b }
    tasks:
      extraction: haiku

Changer de modèle pour une tâche ne demande aucune ligne de code.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .adapters import ADAPTERS, LLMError, Profile

DEFAULT_PATH = "worldkit-llm.yaml"
TASKS = ("extraction", "mentions", "facts", "notes")

DEFAULT: dict[str, Any] = {
    "profiles": {
        "haiku": {"adapter": "claude-code", "model": "claude-haiku-4-5"},
        "sonnet": {"adapter": "claude-code", "model": "claude-sonnet-5"},
        "api-haiku": {"adapter": "anthropic-api", "model": "claude-haiku-4-5", "temperature": 0,
                      "price": {"input": 1.0, "output": 5.0}},
        "api-sonnet": {"adapter": "anthropic-api", "model": "claude-sonnet-5", "price": {"input": 2.0, "output": 10.0}},
        "local": {"adapter": "ollama", "model": "qwen2.5:7b"},
    },
    "tasks": {"extraction": "haiku"},
}


@dataclass(frozen=True)
class LLMConfig:
    profiles: dict[str, Profile]
    tasks: dict[str, str] = field(default_factory=dict)
    max_calls_per_run: int = 30  # plafond d'appels au modèle par exécution (I-LLM-01)

    def profile(self, name: str | None = None, task: str = "extraction") -> Profile:
        # Une tâche sans profil : celui de l'extraction ; la couche « descriptions », qui suit les faits, prend
        # d'abord celui des faits (J9).
        name = name or self.tasks.get(task) or (self.tasks.get("facts") if task == "notes" else None) \
            or self.tasks.get("extraction")
        if name is None:
            raise LLMError(f"aucun profil pour la tâche « {task} » : préciser --profile ou tasks.{task}")
        if name not in self.profiles:
            raise LLMError(f"profil inconnu : {name} (connus : {', '.join(sorted(self.profiles))})")
        return self.profiles[name]


def parse_config(raw: dict[str, Any]) -> LLMConfig:
    profiles = {}
    for name, p in (raw.get("profiles") or {}).items():
        if p.get("adapter") not in ADAPTERS:
            raise LLMError(f"profil {name} : adaptateur inconnu « {p.get('adapter')} »")
        profiles[name] = Profile(name, p["adapter"], str(p["model"]), p.get("effort"),
                                 {k: v for k, v in p.items() if k not in ("adapter", "model", "effort")})
    tasks = {k: str(v) for k, v in (raw.get("tasks") or {}).items()}
    for task, name in tasks.items():
        if name not in profiles:
            raise LLMError(f"tâche {task} : profil inconnu « {name} »")
    return LLMConfig(profiles, tasks, int(raw.get("max_calls_per_run", 30)))


def routing(config: LLMConfig) -> dict[str, str | None]:
    """Profil effectif de chaque tâche (avec les replis de `LLMConfig.profile`), None s'il n'y en a pas."""
    out: dict[str, str | None] = {}
    for task in TASKS:
        try:
            out[task] = config.profile(None, task).name
        except LLMError:
            out[task] = None
    return out


def write_routing(tasks: dict[str, str], path: str | Path | None = None) -> LLMConfig:
    """Fixe le profil de tâches dans le fichier (I-LLM-02) et rend la configuration relue.

    Seul le bloc `tasks:` est réécrit : profils, réglages et commentaires du reste du fichier restent. Sans
    fichier, il est créé depuis la configuration par défaut. Un profil inconnu est refusé avant toute écriture."""
    candidate = Path(path) if path else Path(DEFAULT_PATH)
    text = candidate.read_text(encoding="utf-8") if candidate.exists() else yaml.safe_dump(
        {k: v for k, v in DEFAULT.items() if k != "tasks"}, allow_unicode=True, sort_keys=False)
    raw = yaml.safe_load(text) or {}
    merged = {**(raw.get("tasks") or {}), **tasks}
    parse_config({**raw, "tasks": merged})  # refuse un profil ou une tâche inconnus, sans rien écrire
    for task in tasks:
        if task not in TASKS:
            raise LLMError(f"tâche inconnue : {task} (connues : {', '.join(TASKS)})")
    block = ["tasks:"] + [f"  {task}: {name}" for task, name in merged.items()]
    lines, kept, inside = text.splitlines(), [], False
    for line in lines:
        if line.startswith("tasks:"):
            inside = True
            kept.extend(block)
            continue
        if inside and (line.startswith((" ", "\t")) or not line.strip()):
            continue  # ligne du bloc remplacé
        inside = False
        kept.append(line)
    if "tasks:" not in kept:
        kept.extend(block)
    candidate.write_text("\n".join(kept) + "\n", encoding="utf-8")
    return load_config(candidate)


def load_config(path: str | Path | None = None) -> LLMConfig:
    """Le fichier donné, sinon `worldkit-llm.yaml` s'il existe, sinon la configuration par défaut."""
    candidate = Path(path) if path else Path(DEFAULT_PATH)
    if candidate.exists():
        return parse_config(yaml.safe_load(candidate.read_text(encoding="utf-8")) or {})
    if path:
        raise LLMError(f"configuration LLM introuvable : {path}")
    return parse_config(DEFAULT)
