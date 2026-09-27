"""Registre des opérations du service (décision I1 : opérations nommées à paramètres typés).

Une opération est déclarée une fois : un nom (`edit.apply`), une **sorte**, un modèle pydantic de
paramètres et une fonction qui appelle le code métier, sans logique propre (I-PRI-02). Un appel est
donc une donnée — nom et paramètres JSON — qu'on enregistre (I-RUN-01), qu'on rejoue pour rendre un bac
réel (I-SBX-01, I3), et d'où se déduisent la ligne de commande (I-CLI-01) et l'API HTTP (I2).

Sortes (décision I1) :
- `read` : consultation ; non enregistrée (elle se recalcule depuis l'état), sauf si on l'épingle ;
- `compute` : mécanisme sans écriture ; enregistrée, pour comparer ;
- `write` : écrit dans un monde ou un bac ; enregistrée, rejouable ;
- `admin` : gère les bacs et les exécutions ; enregistrée, jamais rejouée.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from worldkit.core.schema import Issue

Kind = Literal["read", "compute", "write", "admin"]


class Params(BaseModel):
    """Base des paramètres d'une opération : un paramètre inconnu est refusé, pas ignoré."""

    model_config = ConfigDict(extra="forbid")


@dataclass
class Output:
    """Ce que rend la fonction d'une opération ; le service en fait un `Result`."""

    value: Any = None
    issues: list[Issue] = field(default_factory=list)
    indicators: dict[str, Any] = field(default_factory=dict)
    status: str | None = None  # déduit des signalements si absent (erreur → refused)


@dataclass(frozen=True)
class Operation:
    name: str
    kind: Kind
    params: type[Params]
    func: Callable[..., Output]
    summary: str
    rules: tuple[str, ...] = ()
    needs_world: bool = True  # False : opération de session (bacs, exécutions)


REGISTRY: dict[str, Operation] = {}


def operation(name: str, kind: Kind, params: type[Params], summary: str, rules: tuple[str, ...] = (),
              needs_world: bool = True) -> Callable[[Callable[..., Output]], Callable[..., Output]]:
    def register(func: Callable[..., Output]) -> Callable[..., Output]:
        if name in REGISTRY:
            raise ValueError(f"opération déjà déclarée : {name}")
        REGISTRY[name] = Operation(name, kind, params, func, summary, rules, needs_world)
        return func
    return register


def describe(op: Operation) -> dict[str, Any]:
    """Nom, sorte, résumé, règles et paramètres (schéma JSON) : pour `worldkit ops` et l'interface."""
    schema = op.params.model_json_schema()
    required = set(schema.get("required", []))
    params = {k: {"type": v.get("type") or v.get("anyOf") or v.get("$ref"), "required": k in required,
                  "description": v.get("description", ""), "default": v.get("default")}
              for k, v in schema.get("properties", {}).items()}
    return {"name": op.name, "kind": op.kind, "summary": op.summary, "rules": list(op.rules), "params": params}
