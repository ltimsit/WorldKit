"""Forme commune d'un retour (cadre d'interface §7, I-PRI-03, I-OBJ-06).

Toute opération du service rend un `Result` : statut, entrée, sortie, signalements avec la règle citée,
indicateurs, trace. Il se sérialise en **JSON canonique** (clés triées) ; la sortie et les signalements ne
dépendent que de l'entrée et de l'état (T-ARC-01), la trace (durées, horodatage) varie.
"""

from __future__ import annotations

import dataclasses
import enum
import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from worldkit.core.schema import Issue, Severity

Status = Literal["ok", "refused", "pending", "error"]
RESULT_FORMAT = 1


class IssueView(BaseModel):
    code: str
    severity: str
    rule: str
    message: str
    path: str = ""

    @classmethod
    def of(cls, issue: Issue) -> IssueView:
        return cls(code=str(issue.code), severity=str(issue.severity), rule=issue.rule, message=issue.message,
                   path=issue.path)


class Trace(BaseModel):
    duration_ms: float = 0.0
    code_version: str = ""
    llm_calls: int = 0
    run_id: int | None = None  # exécution enregistrée (I-RUN-01), si elle l'est


class Result(BaseModel):
    format: int = RESULT_FORMAT
    operation: str
    kind: str                       # read | compute | write | admin
    target: str                     # "world" ou "sandbox:<n>"
    status: Status
    params: dict[str, Any] = Field(default_factory=dict)
    output: Any = None
    issues: list[IssueView] = Field(default_factory=list)
    indicators: dict[str, Any] = Field(default_factory=dict)
    trace: Trace = Field(default_factory=Trace)

    @property
    def ok(self) -> bool:
        return self.status in ("ok", "pending")

    def to_json(self, indent: int | None = 2) -> str:
        return json.dumps(self.model_dump(mode="json"), ensure_ascii=False, sort_keys=True, indent=indent)

    def stable(self) -> dict[str, Any]:
        """Ce qui ne dépend que de l'entrée et de l'état : pour vérifier le déterminisme (I-PRI-05)."""
        d = self.model_dump(mode="json")
        d.pop("trace")
        return d


def jsonable(x: Any) -> Any:
    """Objets du domaine (dataclasses, modèles pydantic, énumérations, ensembles, tuples) → JSON."""
    if isinstance(x, BaseModel):
        return jsonable(x.model_dump(mode="json", by_alias=True, exclude_none=True))
    if dataclasses.is_dataclass(x) and not isinstance(x, type):
        return {f.name: jsonable(getattr(x, f.name)) for f in dataclasses.fields(x)}
    if isinstance(x, enum.Enum):
        return x.value
    if isinstance(x, dict):
        return {str(k) if not isinstance(k, (tuple, list)) else json.dumps(jsonable(k)): jsonable(v)
                for k, v in x.items()}
    if isinstance(x, (set, frozenset)):
        return sorted((jsonable(i) for i in x), key=lambda v: json.dumps(v, sort_keys=True, default=str))
    if isinstance(x, (list, tuple)):
        return [jsonable(i) for i in x]
    if isinstance(x, Path):
        return str(x)
    return x


def issues_of(issues: list[Issue]) -> list[IssueView]:
    return [IssueView.of(i) for i in issues]


def has_error(issues: list[Issue]) -> bool:
    return any(i.severity is Severity.ERROR for i in issues)
