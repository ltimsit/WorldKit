"""File de revue (M9, lecture) : propositions qualifiées, dépendances, supports (T-ING-02 à T-ING-05, T-ING-11)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from worldkit.core.journal.models import BaseState, EditStatus
from worldkit.core.schema import Change
from worldkit.core.schema.changes import (
    AddClaim, AddRelation, AddValue, CloseEntity, CreateEntity, DeleteEntity, RemoveRelation, RemoveValue, SetAttribute,
    SetVisibility, UnsetAttribute,
)
from worldkit.core.world import World

from .queue import load, refresh
from .store import ensure_tables, loads_key

# Ordre d'affichage des étiquettes : ce qui demande l'attention d'abord.
TAG_ORDER = ["out_of_schema", "invalid_value", "unresolved", "anomaly", "intention", "internal_contradiction",
             "batch_conflict", "competing", "duplicate", "hint_visibility", "enrichment", "optional", "support"]


def describe(c: Change) -> str:
    """Forme lisible d'un changement, pour la revue."""
    match c:
        case CreateEntity():
            return f"+ entité {c.entity} ({c.type})"
        case CloseEntity():
            return f"clôture de {c.entity}"
        case DeleteEntity():
            return f"suppression de {c.entity}"
        case SetAttribute():
            return f"{c.entity}.{c.attribute} = {c.value!r}"
        case UnsetAttribute():
            return f"{c.entity}.{c.attribute} = (vide)"
        case AddValue():
            return f"{c.entity}.{c.attribute} += {c.value!r}"
        case RemoveValue():
            return f"{c.entity}.{c.attribute} -= {c.value!r}"
        case AddRelation():
            return f"+ {c.relation}({c.from_}, {c.to})"
        case RemoveRelation():
            return f"- {c.relation}({c.from_}, {c.to})"
        case AddClaim():
            return f"affirmation de {c.speaker} : « {c.text} »"
        case SetVisibility():
            t = c.target
            target = f"{t.relation}({t.from_}, {t.to})" if t.relation else \
                f"{t.entity}.{t.attribute}" if t.attribute else f"{t.entity}"
            return f"notoriété de {target} → {c.value}"
    return c.op


def sort_tags(tags: list[str]) -> list[str]:
    return sorted(tags, key=lambda t: TAG_ORDER.index(t) if t in TAG_ORDER else len(TAG_ORDER))


@dataclass(frozen=True)
class ChangeView:
    change: Change
    tags: list[str]
    detail: dict[str, Any]
    fingerprint: str
    state: str = "open"

    @property
    def text(self) -> str:
        return describe(self.change)


@dataclass(frozen=True)
class ProposalView:
    id: str
    status: EditStatus
    needs_recheck: bool
    batch: str
    doc: str
    passage: int
    subject: str
    kind: str
    base: BaseState | None
    changes: list[ChangeView]
    depends_on: list[str] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)
    closed_reason: str | None = None

    @property
    def tags(self) -> list[str]:
        return sort_tags(sorted({t for c in self.changes if c.state == "open" for t in c.tags}))


def proposals(world: World, batch: str | None = None,
              status: EditStatus | None = EditStatus.PENDING) -> list[ProposalView]:
    """Propositions, requalifiées contre la tête au préalable (T-ING-06)."""
    refresh(world)
    return [ProposalView(p.id, p.status, p.needs_recheck, p.batch, p.doc, p.passage, p.subject, p.kind, p.base,
                         [ChangeView(c.change, sort_tags(sorted(c.tags)), c.detail, c.fingerprint, c.state)
                          for c in p.changes], p.depends_on, p.issues, p.closed_reason)
            for p in load(world, None, None, status) if batch is None or p.batch == batch]


@dataclass(frozen=True)
class SupportView:
    batch: str
    doc: str
    passage: int
    key: tuple[Any, ...]
    value: Any


def supports(world: World, batch: str | None = None) -> list[SupportView]:
    conn = world.store.conn
    ensure_tables(conn)
    rows = conn.execute("SELECT batch_id, doc_id, passage_idx, fact_key, value FROM supports"
                        " WHERE (? IS NULL OR batch_id = ?) ORDER BY batch_id, doc_id, passage_idx, fact_key",
                        (batch, batch)).fetchall()
    return [SupportView(b, d, p, loads_key(k), json.loads(v)) for b, d, p, k, v in rows]


def flagged_passages(world: World, batch: str | None = None) -> list[tuple[str, int, list[str]]]:
    conn = world.store.conn
    ensure_tables(conn)
    rows = conn.execute("SELECT p.doc_id, p.idx, p.flags FROM passages p JOIN batch_documents d"
                        " ON d.doc_id = p.doc_id AND d.version_fp = p.version_fp"
                        " WHERE (? IS NULL OR d.batch_id = ?) ORDER BY d.batch_id, d.position, p.idx",
                        (batch, batch)).fetchall()
    return [(d, i, json.loads(f)) for d, i, f in rows if json.loads(f)]
