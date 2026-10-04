"""Usage des appels au modèle : tokens, durée, coût, budget d'entrée (T-LLM-01 ; chantier ingestion §8.2).

Chaque adaptateur note ses appels dans un `UsageMeter`. La mesure T2 en tire le coût et l'écart au budget,
par passage et au total. Le budget d'entrée simule un petit modèle (contexte court) : 4 000 tokens par appel
par défaut, réglable par la variable d'environnement `WORLDKIT_LLM_INPUT_BUDGET` (`0` ou `off` : aucun).
Un dépassement n'est pas refusé : il est signalé une fois par compteur, et mesuré.

Trace des appels : si `WORLDKIT_LLM_LOG_DIR` désigne un dossier, chaque appel y est écrit en Markdown, exactement
comme il part (prompt système, message, schéma de sortie, réglages) avec la réponse brute. Pour l'auteur, hors dépôt.
"""

from __future__ import annotations

import json
import logging
import os
import re
import threading
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
from typing import Any

INPUT_BUDGET_VARIABLE = "WORLDKIT_LLM_INPUT_BUDGET"
CALL_LOG_VARIABLE = "WORLDKIT_LLM_LOG_DIR"
DEFAULT_INPUT_BUDGET = 4000
CACHE_WRITE_FACTOR, CACHE_READ_FACTOR = 1.25, 0.1  # tarifs du cache de prompt, relatifs à l'entrée

log = logging.getLogger("worldkit.llm")


def input_budget() -> int | None:
    """Budget d'entrée par appel, en tokens ; None : aucun budget."""
    raw = os.environ.get(INPUT_BUDGET_VARIABLE, "").strip().lower()
    if not raw:
        return DEFAULT_INPUT_BUDGET
    if raw in ("off", "none", "aucun"):
        return None
    try:
        value = int(raw)
    except ValueError:
        raise ValueError(f"{INPUT_BUDGET_VARIABLE} : nombre de tokens attendu, ou « off » (reçu : {raw})") from None
    return value if value > 0 else None


@dataclass(frozen=True)
class CallUsage:
    """Un appel au modèle. `input_tokens` compte tout le prompt vu par le modèle, cache compris."""

    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    seconds: float = 0.0
    cost: float | None = None  # en dollars ; None : prix inconnu
    label: str | None = None   # ce que l'appel traitait (« notes-baron p1 »)


def cost_of(price: dict[str, Any] | None, input_tokens: int, output_tokens: int,
            cache_read: int = 0, cache_write: int = 0) -> float | None:
    """Coût d'un appel d'après le prix du profil (`price: {input, output}`, dollars par million de tokens)."""
    if not price:
        return None
    unit_in, unit_out = float(price["input"]), float(price["output"])
    fresh = max(0, input_tokens - cache_read - cache_write)
    return (fresh * unit_in + cache_write * unit_in * CACHE_WRITE_FACTOR + cache_read * unit_in * CACHE_READ_FACTOR
            + output_tokens * unit_out) / 1_000_000


class UsageMeter:
    """Journal des appels d'un adaptateur, sûr entre fils ; `label` étiquette les appels du fil courant."""

    def __init__(self) -> None:
        self.calls: list[CallUsage] = []
        self._lock = threading.Lock()
        self._local = threading.local()
        self._warned = False

    @contextmanager
    def label(self, name: str) -> Iterator[None]:
        previous = getattr(self._local, "label", None)
        self._local.label = name
        try:
            yield
        finally:
            self._local.label = previous

    def trace(self, adapter: str, model: str, system: str, prompt: str, schema: Any, settings: dict[str, Any],
              response: Any) -> Path | None:
        """Écrit l'appel tel qu'il part, et sa réponse brute, si `WORLDKIT_LLM_LOG_DIR` est défini."""
        folder = os.environ.get(CALL_LOG_VARIABLE, "").strip()
        if not folder:
            return None
        label = getattr(self._local, "label", None) or "appel"
        path = Path(folder) / (f"{datetime.now():%Y%m%d-%H%M%S}-{re.sub(r'[^\w-]+', '-', label)}"
                               f"-{uuid.uuid4().hex[:6]}.md")
        path.parent.mkdir(parents=True, exist_ok=True)
        shown = response if isinstance(response, str) else json.dumps(response, ensure_ascii=False, indent=2)
        fence = "````"
        sections = [f"# {label}", "",
                    f"- adaptateur : `{adapter}`", f"- modèle : `{model}`", f"- réglages : `{json.dumps(settings)}`",
                    f"- date : {datetime.now():%Y-%m-%d %H:%M:%S}", "",
                    "## Prompt système", "", fence + "text", system, fence, "",
                    "## Message", "", fence + "text", prompt, fence, "",
                    "## Schéma de sortie envoyé", "", fence + "json", json.dumps(schema, ensure_ascii=False, indent=2),
                    fence, "", "## Réponse brute", "", fence + "json", shown, fence, ""]
        path.write_text("\n".join(sections), encoding="utf-8")
        return path

    def record(self, usage: CallUsage) -> None:
        usage = replace(usage, label=getattr(self._local, "label", None))
        budget = input_budget()
        with self._lock:
            self.calls.append(usage)
            warn = budget is not None and usage.input_tokens > budget and not self._warned
            self._warned = self._warned or warn
        if warn:
            log.warning("appel au-delà du budget d'entrée : %d tokens pour %d (%s) ; dépassements mesurés",
                        usage.input_tokens, budget, INPUT_BUDGET_VARIABLE)


def summarize(calls: list[CallUsage], budget: int | None = None) -> dict[str, Any]:
    """Totaux d'une série d'appels et écart au budget d'entrée."""
    over = [c.input_tokens - budget for c in calls if budget is not None and c.input_tokens > budget]
    costs = [c.cost for c in calls]
    return {
        "calls": len(calls),
        "input_tokens": sum(c.input_tokens for c in calls),
        "output_tokens": sum(c.output_tokens for c in calls),
        "cache_read_tokens": sum(c.cache_read_tokens for c in calls),
        "max_input_tokens": max((c.input_tokens for c in calls), default=0),
        "cost": round(sum(costs), 4) if calls and None not in costs else None,  # type: ignore[arg-type]
        "budget": budget,
        "over_budget": len(over),
        "excess_tokens": sum(over),
        "max_excess": max(over, default=0),
    }
