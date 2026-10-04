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
TASKS = ("extraction",)

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
        name = name or self.tasks.get(task)
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


def load_config(path: str | Path | None = None) -> LLMConfig:
    """Le fichier donné, sinon `worldkit-llm.yaml` s'il existe, sinon la configuration par défaut."""
    candidate = Path(path) if path else Path(DEFAULT_PATH)
    if candidate.exists():
        return parse_config(yaml.safe_load(candidate.read_text(encoding="utf-8")) or {})
    if path:
        raise LLMError(f"configuration LLM introuvable : {path}")
    return parse_config(DEFAULT)
