"""Stockage d'un monde : SQLite, un fichier par monde (T-STO-02 ; tables : cadre technique §2.1).

L'historique ne fait que s'allonger (R-HIS-01, R-CYC-01) : des déclencheurs SQL interdisent
de modifier ou de retirer une ligne du journal, un changement, ou une édition sortie de l'état
`pending`. Seuls le statut et l'état de base d'une édition en attente évoluent (T-ING-06).
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from worldkit.core.projection.state import WorldDeclaration
from worldkit.core.schema import FactKey, Schema
from worldkit.core.schema.changes import parse_change

from .models import BaseState, Edit, EditStatus

_DDL = """
CREATE TABLE world (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE branches (
    branch_id TEXT PRIMARY KEY, parent TEXT, fork_seq INTEGER, status TEXT NOT NULL DEFAULT 'active');
CREATE TABLE edits (
    edit_id TEXT PRIMARY KEY, branch_id TEXT NOT NULL REFERENCES branches(branch_id),
    status TEXT NOT NULL, header TEXT NOT NULL, submitted INTEGER NOT NULL,
    base_seq INTEGER, base_schema_rev INTEGER, reads TEXT, writes TEXT,
    needs_recheck INTEGER NOT NULL DEFAULT 0);
CREATE TABLE changes (
    edit_id TEXT NOT NULL REFERENCES edits(edit_id), idx INTEGER NOT NULL, payload TEXT NOT NULL,
    PRIMARY KEY (edit_id, idx));
CREATE TABLE journal (
    branch_id TEXT NOT NULL REFERENCES branches(branch_id), seq INTEGER NOT NULL,
    edit_id TEXT NOT NULL UNIQUE REFERENCES edits(edit_id), PRIMARY KEY (branch_id, seq));
CREATE TABLE named_points (
    branch_id TEXT NOT NULL, name TEXT NOT NULL, seq INTEGER NOT NULL, PRIMARY KEY (branch_id, name));
CREATE TABLE heads (branch_id TEXT PRIMARY KEY, seq INTEGER NOT NULL, state TEXT NOT NULL);

CREATE TRIGGER journal_append_only_u BEFORE UPDATE ON journal
  BEGIN SELECT RAISE(ABORT, 'R-HIS-01 : le journal ne fait que s''allonger'); END;
CREATE TRIGGER journal_append_only_d BEFORE DELETE ON journal
  BEGIN SELECT RAISE(ABORT, 'R-HIS-01 : le journal ne fait que s''allonger'); END;
CREATE TRIGGER changes_append_only_u BEFORE UPDATE ON changes
  BEGIN SELECT RAISE(ABORT, 'R-CYC-01 : un changement enregistré ne se modifie pas'); END;
CREATE TRIGGER changes_append_only_d BEFORE DELETE ON changes
  BEGIN SELECT RAISE(ABORT, 'R-CYC-01 : un changement enregistré ne se retire pas'); END;
CREATE TRIGGER edits_frozen_u BEFORE UPDATE ON edits WHEN OLD.status <> 'pending'
  BEGIN SELECT RAISE(ABORT, 'R-CYC-01 : une édition appliquée ou abandonnée ne se modifie pas'); END;
CREATE TRIGGER edits_no_delete BEFORE DELETE ON edits
  BEGIN SELECT RAISE(ABORT, 'R-CYC-02 : une édition reste tracée'); END;
"""


def encode_keys(keys: Iterable[FactKey]) -> str:
    return json.dumps(sorted((list(k) for k in keys), key=repr), ensure_ascii=False)


def _tuplify(x: Any) -> Any:
    return tuple(_tuplify(i) for i in x) if isinstance(x, list) else x


def decode_keys(text: str | None) -> frozenset[FactKey]:
    return frozenset(_tuplify(k) for k in json.loads(text)) if text else frozenset()


@dataclass(frozen=True)
class EditRecord:
    edit: Edit
    status: EditStatus
    base: BaseState | None
    reads: frozenset[FactKey]
    writes: frozenset[FactKey]
    needs_recheck: bool


class WorldExists(FileExistsError):
    pass


class Store:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    # --- Ouverture ---

    @classmethod
    def create(cls, path: str | Path, decl: WorldDeclaration) -> Store:
        path = Path(path)
        if str(path) != ":memory:" and path.exists():
            raise WorldExists(f"le monde existe déjà : {path}")
        conn = sqlite3.connect(str(path))
        conn.executescript(_DDL)
        store = cls(conn)
        with conn:
            conn.execute("INSERT INTO world VALUES ('declaration', ?)", (_encode_decl(decl),))
            conn.execute("INSERT INTO branches (branch_id, parent, fork_seq) VALUES (?, NULL, NULL)",
                         (decl.reference_branch,))
        return store

    @classmethod
    def open(cls, path: str | Path) -> Store:
        if not Path(path).exists():
            raise FileNotFoundError(f"monde introuvable : {path}")
        return cls(sqlite3.connect(str(path)))

    def close(self) -> None:
        self.conn.close()

    def declaration(self) -> WorldDeclaration:
        row = self.conn.execute("SELECT value FROM world WHERE key = 'declaration'").fetchone()
        return _decode_decl(row[0])

    # --- Éditions ---

    def has_edit(self, edit_id: str) -> bool:
        return self.conn.execute("SELECT 1 FROM edits WHERE edit_id = ?", (edit_id,)).fetchone() is not None

    def record_edit(self, edit: Edit, status: EditStatus, base: BaseState | None,
                    reads: frozenset[FactKey], writes: frozenset[FactKey]) -> None:
        header = edit.model_dump(mode="json", by_alias=True, exclude={"changes"}, exclude_none=True)
        submitted = self.conn.execute("SELECT COUNT(*) FROM edits").fetchone()[0]
        self.conn.execute(
            "INSERT INTO edits (edit_id, branch_id, status, header, submitted, base_seq, base_schema_rev,"
            " reads, writes) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (edit.id, edit.branch, status.value, json.dumps(header, ensure_ascii=False), submitted,
             base.seq if base else None, base.schema_rev if base else None,
             encode_keys(reads), encode_keys(writes)))
        self.conn.executemany(
            "INSERT INTO changes (edit_id, idx, payload) VALUES (?, ?, ?)",
            [(edit.id, i, json.dumps(c.model_dump(mode="json", by_alias=True, exclude_none=True), ensure_ascii=False))
             for i, c in enumerate(edit.changes)])

    def append_journal(self, branch: str, edit_id: str) -> int:
        seq = self.head_seq(branch) + 1
        self.conn.execute("INSERT INTO journal VALUES (?, ?, ?)", (branch, seq, edit_id))
        return seq

    def update_pending(self, edit_id: str, *, status: EditStatus | None = None, base: BaseState | None = None,
                       reads: frozenset[FactKey] | None = None, writes: frozenset[FactKey] | None = None,
                       needs_recheck: bool | None = None) -> None:
        sets, args = [], []
        if status is not None:
            sets.append("status = ?"); args.append(status.value)
        if base is not None:
            sets += ["base_seq = ?", "base_schema_rev = ?"]; args += [base.seq, base.schema_rev]
        if reads is not None:
            sets.append("reads = ?"); args.append(encode_keys(reads))
        if writes is not None:
            sets.append("writes = ?"); args.append(encode_keys(writes))
        if needs_recheck is not None:
            sets.append("needs_recheck = ?"); args.append(int(needs_recheck))
        self.conn.execute(f"UPDATE edits SET {', '.join(sets)} WHERE edit_id = ?", (*args, edit_id))

    def edit(self, edit_id: str) -> EditRecord:
        row = self.conn.execute(
            "SELECT edit_id, branch_id, status, header, base_seq, base_schema_rev, reads, writes, needs_recheck"
            " FROM edits WHERE edit_id = ?", (edit_id,)).fetchone()
        if row is None:
            raise KeyError(f"édition inconnue : {edit_id}")
        return self._record(row)

    def edits(self, branch: str, status: EditStatus | None = None) -> list[EditRecord]:
        sql = ("SELECT edit_id, branch_id, status, header, base_seq, base_schema_rev, reads, writes, needs_recheck"
               " FROM edits WHERE branch_id = ?")
        args: list[Any] = [branch]
        if status is not None:
            sql += " AND status = ?"; args.append(status.value)
        return [self._record(r) for r in self.conn.execute(sql + " ORDER BY submitted", args)]

    def _record(self, row: Any) -> EditRecord:
        edit_id, branch, status, header, base_seq, base_rev, reads, writes, recheck = row
        payloads = [json.loads(p) for (p,) in self.conn.execute(
            "SELECT payload FROM changes WHERE edit_id = ? ORDER BY idx", (edit_id,))]
        edit = Edit.model_validate({**json.loads(header), "changes": [parse_change(p) for p in payloads]})
        base = BaseState(branch=branch, seq=base_seq, schema_rev=base_rev) if base_seq is not None else None
        return EditRecord(edit, EditStatus(status), base, decode_keys(reads), decode_keys(writes), bool(recheck))

    # --- Journal ---

    def head_seq(self, branch: str) -> int:
        return self.conn.execute("SELECT COALESCE(MAX(seq), 0) FROM journal WHERE branch_id = ?",
                                 (branch,)).fetchone()[0]

    def journal(self, branch: str, upto: int | None = None) -> list[tuple[int, Edit]]:
        rows = self.conn.execute(
            "SELECT seq, edit_id FROM journal WHERE branch_id = ? AND seq <= ? ORDER BY seq",
            (branch, upto if upto is not None else self.head_seq(branch))).fetchall()
        return [(seq, self.edit(edit_id).edit) for seq, edit_id in rows]

    def writes_since(self, branch: str, seq: int) -> set[FactKey]:
        out: set[FactKey] = set()
        for (writes,) in self.conn.execute(
                "SELECT e.writes FROM journal j JOIN edits e ON e.edit_id = j.edit_id"
                " WHERE j.branch_id = ? AND j.seq > ?", (branch, seq)):
            out |= decode_keys(writes)
        return out

    def branches(self) -> list[str]:
        return [b for (b,) in self.conn.execute("SELECT branch_id FROM branches ORDER BY branch_id")]

    # --- Points nommés ---

    def set_named_point(self, branch: str, name: str, seq: int) -> None:
        self.conn.execute("INSERT OR REPLACE INTO named_points VALUES (?, ?, ?)", (branch, name, seq))

    def named_point(self, branch: str, name: str) -> int | None:
        row = self.conn.execute("SELECT seq FROM named_points WHERE branch_id = ? AND name = ?",
                                (branch, name)).fetchone()
        return row[0] if row else None

    def named_points(self, branch: str) -> dict[str, int]:
        return dict(self.conn.execute("SELECT name, seq FROM named_points WHERE branch_id = ? ORDER BY seq, name",
                                      (branch,)).fetchall())

    # --- Tête matérialisée (T-STO-01) ---

    def cached_head(self, branch: str) -> tuple[int, str] | None:
        row = self.conn.execute("SELECT seq, state FROM heads WHERE branch_id = ?", (branch,)).fetchone()
        return (row[0], row[1]) if row else None

    def save_head(self, branch: str, seq: int, state_json: str) -> None:
        self.conn.execute("INSERT OR REPLACE INTO heads VALUES (?, ?, ?)", (branch, seq, state_json))


def _encode_decl(decl: WorldDeclaration) -> str:
    return json.dumps({
        "world": decl.world,
        "reference_branch": decl.reference_branch,
        "world_schema": decl.world_schema.model_dump(mode="json", by_alias=True),
        "systems": {k: v.model_dump(mode="json", by_alias=True) for k, v in decl.systems.items()},
        "sheet_requirements": {k: dict(v) for k, v in decl.sheet_requirements.items()},
    }, ensure_ascii=False)


def _decode_decl(text: str) -> WorldDeclaration:
    d = json.loads(text)
    return WorldDeclaration(d["world"], d["reference_branch"], Schema.model_validate(d["world_schema"]),
                            {k: Schema.model_validate(v) for k, v in d["systems"].items()},
                            d["sheet_requirements"])
