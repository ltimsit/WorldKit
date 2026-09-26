"""File de revue (M9, lecture) : propositions qualifiées, dépendances, supports (T-ING-02 à T-ING-05, T-ING-11)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from worldkit.core.journal.models import BaseState, EditStatus
from worldkit.core.schema import Change
from worldkit.core.schema.changes import (
    AddRelation, AddValue, CloseEntity, CreateEntity, DeleteEntity, RemoveRelation, RemoveValue, SetAttribute,
    SetVisibility, UnsetAttribute,
)
from worldkit.core.world import World

from .store import ensure_tables, loads_key

# Ordre d'affichage des étiquettes : ce qui demande l'attention d'abord.
TAG_ORDER = ["out_of_schema", "invalid_value", "unresolved", "anomaly", "intention", "internal_contradiction",
             "batch_conflict", "competing", "hint_visibility", "enrichment", "optional", "support"]


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

    @property
    def tags(self) -> list[str]:
        return sort_tags(sorted({t for c in self.changes for t in c.tags}))


def proposals(world: World, batch: str | None = None, status: EditStatus | None = EditStatus.PENDING) -> list[ProposalView]:
    conn = world.store.conn
    ensure_tables(conn)
    sql = ("SELECT p.edit_id, p.batch_id, p.doc_id, p.passage_idx, p.subject, p.kind, p.issues FROM proposals p"
           " JOIN batches b ON b.batch_id = p.batch_id"
           " JOIN batch_documents d ON d.batch_id = p.batch_id AND d.doc_id = p.doc_id"
           " WHERE (? IS NULL OR p.batch_id = ?) ORDER BY b.opened, d.position, p.passage_idx, p.edit_id")
    out = []
    for edit_id, batch_id, doc, passage, subject, kind, issues in conn.execute(sql, (batch, batch)).fetchall():
        rec = world.store.edit(edit_id)
        if status is not None and rec.status is not status:
            continue
        rows = conn.execute("SELECT fingerprint, tags, detail FROM proposal_changes WHERE edit_id = ? ORDER BY idx",
                            (edit_id,)).fetchall()
        changes = [ChangeView(c, sort_tags(json.loads(t)), json.loads(d), fp)
                   for c, (fp, t, d) in zip(rec.edit.changes, rows, strict=True)]
        deps = [d for (d,) in conn.execute("SELECT depends_on FROM proposal_deps WHERE edit_id = ? ORDER BY depends_on",
                                           (edit_id,))]
        out.append(ProposalView(edit_id, rec.status, rec.needs_recheck, batch_id, doc, passage, subject, kind,
                                rec.base, changes, deps, json.loads(issues)))
    return out


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
