"""File de revue (M9, lecture) : propositions qualifiées, dépendances, supports (T-ING-02 à T-ING-05, T-ING-11)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from worldkit.core.journal.models import BaseState, EditStatus
from worldkit.core.schema import Change, Issue, IssueCode, Severity, Visibility
from worldkit.core.schema.changes import (
    AddClaim, AddRelation, AddValue, CloseEntity, CreateEntity, DeleteEntity, RemoveRelation, RemoveValue, SetAttribute,
    SetVisibility, UnsetAttribute,
)
from worldkit.core.world import World

from .queue import blocked, load, refresh
from .store import dumps, ensure_tables, loads_key

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
    blocked: bool = False  # document obsolète (R-DOC-05)

    @property
    def tags(self) -> list[str]:
        return sort_tags(sorted({t for c in self.changes if c.state == "open" for t in c.tags}))


def proposals(world: World, batch: str | None = None,
              status: EditStatus | None = EditStatus.PENDING, branch: str | None = None) -> list[ProposalView]:
    """Propositions d'une branche, requalifiées contre sa tête au préalable (T-ING-06)."""
    refresh(world, branch)
    head = world.state(branch)
    return [ProposalView(p.id, p.status, p.needs_recheck, p.batch, p.doc, p.passage, p.subject, p.kind, p.base,
                         [ChangeView(c.change, sort_tags(sorted(c.tags)), c.detail, c.fingerprint, c.state)
                          for c in p.changes], p.depends_on, p.issues, p.closed_reason, blocked(head, p.doc))
            for p in load(world, branch, None, status) if batch is None or p.batch == batch]


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


def orphan_facts(world: World, branch: str | None = None) -> list[Issue]:
    """R-FAI-06 : faits établis par l'ingestion qui n'ont plus aucun support documentaire.
    Signalés, jamais retirés (R-PRI-01). Un fait d'édition structurée n'est jamais orphelin (T-ING-11)."""
    conn = world.store.conn
    ensure_tables(conn)
    branch = branch or world.reference_branch
    head = world.state(branch)
    documentary = {e.id for _, e in world.store.journal(branch) if "ingestion" in e.tags}
    keys_of: dict[Any, list[Any]] = {}
    for k, fid in head.occupancy.items():
        keys_of.setdefault(fid, []).append(k)
    out = []
    for f in sorted(head.facts.values(), key=lambda f: repr(f.id)):
        if f.established_by not in documentary:
            continue
        value = dumps(list(f.id) if f.kind == "rel" else True if f.kind == "value" else f.value)
        supported = any(conn.execute("SELECT 1 FROM supports WHERE fact_key = ? AND value = ?", (dumps(k), value))
                        .fetchone() for k in keys_of.get(f.id, []))
        if not supported:
            label = f"{f.name}({f.subject}, {f.target})" if f.kind == "rel" else f"{f.subject}.{f.name}"
            out.append(Issue(IssueCode.ORPHAN_FACT,
                             f"{label} n'a plus aucun support documentaire (établi par {f.established_by}) ; "
                             "conservé dans l'état", "R-FAI-06", Severity.WARNING, label))
    return out


def sources(world: World, branch: str | None = None) -> dict[str, list[tuple[str, Visibility]]]:
    """Documents qui soutiennent au moins un fait de chaque entité (R-VUE-02, R-DOC-04), avec la
    notoriété déclarée du document (absente = non qualifiée, R-NOT-01)."""
    conn = world.store.conn
    ensure_tables(conn)
    head = world.state(branch)
    visibility: dict[str, Visibility] = {}
    for doc, axes in conn.execute("SELECT doc_id, axes FROM document_versions"):
        declared = json.loads(axes).get("visibility")
        visibility[doc] = Visibility(declared) if declared else Visibility.UNQUALIFIED
    out: dict[str, set[str]] = {}
    for doc, key in conn.execute("SELECT DISTINCT doc_id, fact_key FROM supports"):
        for part in loads_key(key):
            if isinstance(part, str) and part in head.entities:
                out.setdefault(part, set()).add(doc)
    return {e: [(d, visibility.get(d, Visibility.UNQUALIFIED)) for d in sorted(docs)] for e, docs in out.items()}
