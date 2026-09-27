"""File de revue vivante (M9) : propositions stockées, requalification contre la tête (T-ING-06).

Une proposition est écrite contre l'état de base de son lot. Quand la branche avance :
- celles que les nouvelles écritures touchent (`needs_recheck`) sont **requalifiées** contre la tête :
  un changement devenu identique à l'état devient un support (T-ING-11), une clé désormais occupée
  autrement devient une anomalie ; une proposition dont il ne reste rien à décider est close ;
- les autres sont rebasées en silence (base = tête).

`refresh` est appelée à chaque lecture de la revue et avant chaque décision : le résultat ne dépend
pas du processus qui a fait avancer la branche (édition structurée, autre lot, décision).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from worldkit.core.journal.models import BaseState, EditStatus
from worldkit.core.projection.state import State, relation_fact_id
from worldkit.core.schema import Change, FactKey, fact_keys
from worldkit.core.schema.changes import AddRelation, AddValue, SetAttribute
from worldkit.core.schema.keys import UnknownRelation
from worldkit.core.world import World

from .declaration import Mode, name_key
from .proposals import Item, NewEntity, qualify_item, _context
from .store import dumps, ensure_tables, loads_key

# Étiquettes qui ne dépendent pas de l'état : elles survivent à la requalification.
STICKY = {"internal_contradiction", "batch_conflict", "competing", "duplicate", "hint_visibility", "optional",
          "claim"}


@dataclass
class StoredChange:
    index: int
    change: Change
    tags: set[str]
    detail: dict[str, Any]
    fingerprint: str
    state: str                       # open | accepted | refused | support
    keys: list[FactKey] = field(default_factory=list)
    value: Any = None                # forme JSON de la valeur écrite, pour comparer


@dataclass
class StoredProposal:
    id: str
    batch: str
    batch_order: int
    doc: str
    version_fp: str
    passage: int
    subject: str
    kind: str
    mode: Mode
    status: EditStatus
    base: BaseState | None
    needs_recheck: bool
    changes: list[StoredChange]
    depends_on: list[str]
    issues: list[str]
    closed_reason: str | None
    reads: frozenset[FactKey] = frozenset()
    writes: frozenset[FactKey] = frozenset()

    def open_changes(self) -> list[StoredChange]:
        return [c for c in self.changes if c.state == "open"]


def load(world: World, branch: str | None = None, only: str | None = None,
         status: EditStatus | None = EditStatus.PENDING) -> list[StoredProposal]:
    conn = world.store.conn
    ensure_tables(conn)
    branch = None if only else (branch or world.reference_branch)
    rows = conn.execute(
        "SELECT p.edit_id, p.batch_id, b.opened, p.doc_id, p.version_fp, p.passage_idx, p.subject, p.kind,"
        " p.issues, p.closed_reason, v.axes FROM proposals p"
        " JOIN batches b ON b.batch_id = p.batch_id"
        " JOIN batch_documents d ON d.batch_id = p.batch_id AND d.doc_id = p.doc_id"
        " JOIN document_versions v ON v.doc_id = p.doc_id AND v.version_fp = p.version_fp"
        " JOIN edits e ON e.edit_id = p.edit_id"
        " WHERE (? IS NULL OR e.branch_id = ?) AND (? IS NULL OR p.edit_id = ?)"
        " ORDER BY b.opened, d.position, p.passage_idx, p.edit_id", (branch, branch, only, only)).fetchall()
    out = []
    for pid, batch, opened, doc, vfp, passage, subject, kind, issues, closed, axes in rows:
        rec = world.store.edit(pid)
        if status is not None and rec.status is not status:
            continue
        crows = conn.execute("SELECT idx, fingerprint, tags, detail, state FROM proposal_changes WHERE edit_id = ?"
                             " ORDER BY idx", (pid,)).fetchall()
        keys: dict[int, list[FactKey]] = {}
        values: dict[int, Any] = {}
        for idx, k, v in conn.execute("SELECT idx, fact_key, value FROM proposal_keys WHERE edit_id = ?", (pid,)):
            keys.setdefault(idx, []).append(loads_key(k))
            values[idx] = v
        changes = [StoredChange(i, c, set(json.loads(t)), json.loads(d), fp, st, sorted(keys.get(i, []), key=repr),
                                values.get(i)) for (i, fp, t, d, st), c in zip(crows, rec.edit.changes, strict=True)]
        deps = [d for (d,) in conn.execute("SELECT depends_on FROM proposal_deps WHERE edit_id = ? ORDER BY 1", (pid,))]
        out.append(StoredProposal(pid, batch, opened, doc, vfp, passage, subject, kind, Mode(json.loads(axes)["mode"]),
                                  rec.status, rec.base, rec.needs_recheck, changes, deps, json.loads(issues), closed,
                                  rec.reads, rec.writes))
    return out


def blocked(state: State, doc_id: str) -> bool:
    """Proposition bloquée : son document est obsolète dans l'état (R-DOC-05, décision J3.4).
    Bloquée n'est pas close : la levée du statut la réactive telle quelle."""
    return bool(state.obsolete_documents.get(doc_id, False))


def load_one(world: World, pid: str) -> StoredProposal | None:
    found = load(world, None, pid, None)
    return found[0] if found else None


def pending_new_entities(world: World, head: State) -> dict[str, NewEntity]:
    """Entités dont la création est proposée par un lot encore en attente (T-ING-07) : étiquette → entité."""
    conn = world.store.conn
    ensure_tables(conn)
    out: dict[str, NewEntity] = {}
    for label, eid, type_, name, creator in conn.execute(
            "SELECT label, entity_id, type, name, creator FROM new_entities ORDER BY rowid").fetchall():
        if eid in head.entities or not creator:
            continue
        p = load_one(world, creator)
        if p is not None and p.status is EditStatus.PENDING and any(
                c.state == "open" and c.change.op == "create_entity" for c in p.changes):
            out[label] = NewEntity(label, eid, type_, name)
    return out


def name_index(entities: dict[str, NewEntity]) -> dict[tuple[str, str], NewEntity]:
    """Empreinte (type, nom normalisé) d'une création : sert à reconnaître une création en attente (T-ING-08)."""
    return {(e.type, name_key(e.name)): e for e in entities.values() if e.name}


def passage_fp(world: World, doc: str, version_fp: str, passage: int) -> str:
    row = world.store.conn.execute("SELECT passage_fp FROM passages WHERE doc_id = ? AND version_fp = ? AND idx = ?",
                                   (doc, version_fp, passage)).fetchone()
    return row[0] if row else ""


def save_change(world: World, pid: str, c: StoredChange) -> None:
    world.store.conn.execute("UPDATE proposal_changes SET tags = ?, detail = ?, state = ? WHERE edit_id = ? AND idx = ?",
                             (dumps(sorted(c.tags)), dumps(c.detail), c.state, pid, c.index))


def close(world: World, p: StoredProposal, status: EditStatus, reason: str) -> None:
    world.store.update_pending(p.id, status=status, needs_recheck=False)
    world.store.conn.execute("UPDATE proposals SET closed_reason = ? WHERE edit_id = ?", (reason, p.id))


def record_support(world: World, p: StoredProposal, change: Change, state: State | None = None) -> None:
    """Le passage de la proposition soutient ce changement (T-ING-11). Clés et valeur sont calculées
    contre l'état courant : un changement hors schéma à l'ingestion n'avait pas de clé, il en a une
    une fois le schéma étendu (W09)."""
    state = state or world.state(p.base.branch if p.base else None)
    ctx = state.context()
    try:
        keys = fact_keys(change, ctx)
    except UnknownRelation:
        return
    if isinstance(change, SetAttribute):
        value: Any = change.value
    elif isinstance(change, AddValue):
        value = True
    elif isinstance(change, AddRelation):
        value = list(relation_fact_id(change.from_, change.relation, change.to, change.scope, ctx))
    else:
        return
    for k in keys:
        world.store.conn.execute("INSERT OR IGNORE INTO supports VALUES (?, ?, ?, ?, ?, ?)",
                                 (p.doc, p.version_fp, p.passage, dumps(k), dumps(value), p.batch))


def branch_of(world: World, p: StoredProposal) -> str:
    return p.base.branch if p.base else world.reference_branch


def refresh(world: World, branch: str | None = None) -> list[str]:
    """Requalifie contre la tête les propositions touchées ; rebase les autres. Rend les requalifiées."""
    branch = branch or world.reference_branch
    head = world.state(branch)
    pending = load(world, branch)
    if not pending:
        return []
    ctx = _context(head, pending_new_entities(world, head))
    requalified = []
    with world.store.conn:
        for p in pending:
            if p.base is not None and p.base.seq == head.seq and not p.needs_recheck:
                continue
            touched = p.needs_recheck or _touched(world, p, branch)
            if touched:
                requalified.append(p.id)
                for c in p.open_changes():
                    q = qualify_item(Item(p.doc, p.version_fp, p.passage, 0, c.change, p.mode, "optional" in c.tags),
                                     head, ctx)
                    if q.tags == {"support"} or (q.tags - {"optional"}) == {"support"}:
                        c.tags, c.state = {"support"}, "support"
                        record_support(world, p, c.change, head)
                    else:
                        c.tags = q.tags | (c.tags & STICKY)
                        if "internal_contradiction" in c.tags:
                            c.tags.add("anomaly")  # R-ING-02
                        c.detail = {**{k: v for k, v in c.detail.items() if k != "occupied_by"}, **q.detail}
                        c.detail["requalified_at"] = head.seq
                    save_change(world, p.id, c)
                if not p.open_changes():
                    close(world, p, EditStatus.ABANDONED, "support")
                    continue
            world.store.update_pending(p.id, base=BaseState(branch=branch, seq=head.seq, schema_rev=head.schema_rev),
                                       needs_recheck=False)
    return requalified


def _touched(world: World, p: StoredProposal, branch: str) -> bool:
    if p.base is None:
        return True
    written = world.store.writes_since(branch, p.base.seq)
    return bool(written & (set(p.reads) | set(p.writes)))
