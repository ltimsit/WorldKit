"""Exécutions et bacs à sable d'un monde (I-RUN-01, I-SBX-01 ; décisions I1).

Un seul fichier par monde de travail, `monde.runs.db`, à côté de `monde.db` : il ne fait jamais partie de
l'histoire de l'univers (T-STO-02) ; on le purge à la main sans effet sur le monde.

- `runs` : une ligne par exécution enregistrée (calcul, écriture, administration ; une consultation
  seulement si on l'épingle) ; le résultat complet y est gardé en JSON.
- `sandboxes` : le registre des bacs (fichier, origine — le monde ou un autre bac —, rangs de tête des
  branches au moment de la copie, statut). Jeter un bac garde ses exécutions.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .result import Result

_DDL = """
CREATE TABLE IF NOT EXISTS runs (
    run_id INTEGER PRIMARY KEY AUTOINCREMENT, operation TEXT NOT NULL, kind TEXT NOT NULL, target TEXT NOT NULL,
    status TEXT NOT NULL, params TEXT NOT NULL, result TEXT NOT NULL, created TEXT NOT NULL DEFAULT (datetime('now')));
CREATE TABLE IF NOT EXISTS sandboxes (
    sandbox_id INTEGER PRIMARY KEY AUTOINCREMENT, file TEXT NOT NULL, origin TEXT NOT NULL, heads TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active', created TEXT NOT NULL DEFAULT (datetime('now')), note TEXT);
"""


@dataclass(frozen=True)
class RunRecord:
    id: int
    operation: str
    kind: str
    target: str
    status: str
    params: dict[str, Any]
    created: str

    def result(self, store: RunStore) -> Result:
        return store.result(self.id)


@dataclass(frozen=True)
class Sandbox:
    id: int
    file: str
    origin: str            # "world" ou "sandbox:<n>"
    heads: dict[str, int]  # rang de tête de chaque branche au moment de la copie
    status: str            # active | dropped
    created: str
    note: str | None = None

    @property
    def target(self) -> str:
        return f"sandbox:{self.id}"


class RunStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.conn = sqlite3.connect(str(self.path))
        self.conn.executescript(_DDL)

    def close(self) -> None:
        self.conn.close()

    # --- Exécutions ---

    def record(self, result: Result) -> int:
        with self.conn:
            cur = self.conn.execute(
                "INSERT INTO runs (operation, kind, target, status, params, result) VALUES (?, ?, ?, ?, ?, ?)",
                (result.operation, result.kind, result.target, result.status,
                 json.dumps(result.params, ensure_ascii=False, sort_keys=True), result.to_json(None)))
        run_id = int(cur.lastrowid or 0)
        result.trace.run_id = run_id
        with self.conn:
            self.conn.execute("UPDATE runs SET result = ? WHERE run_id = ?", (result.to_json(None), run_id))
        return run_id

    def runs(self, limit: int | None = None, target: str | None = None,
             operation: str | None = None) -> list[RunRecord]:
        rows = self.conn.execute(
            "SELECT run_id, operation, kind, target, status, params, created FROM runs"
            " WHERE (? IS NULL OR target = ?) AND (? IS NULL OR operation = ?) ORDER BY run_id DESC"
            + (" LIMIT ?" if limit else ""),
            (target, target, operation, operation, *([limit] if limit else []))).fetchall()
        return [RunRecord(r[0], r[1], r[2], r[3], r[4], json.loads(r[5]), r[6]) for r in rows]

    def result(self, run_id: int) -> Result:
        row = self.conn.execute("SELECT result FROM runs WHERE run_id = ?", (run_id,)).fetchone()
        if row is None:
            raise KeyError(f"exécution inconnue : {run_id}")
        return Result.model_validate_json(row[0])

    def purge(self, ids: list[int] | None = None, before: int | None = None, everything: bool = False) -> int:
        """Purge manuelle (I-RUN-01) : sans effet sur l'histoire du monde."""
        with self.conn:
            if everything:
                cur = self.conn.execute("DELETE FROM runs")
            elif before is not None:
                cur = self.conn.execute("DELETE FROM runs WHERE run_id < ?", (before,))
            else:
                cur = self.conn.executemany("DELETE FROM runs WHERE run_id = ?", [(i,) for i in ids or []])
        return cur.rowcount

    # --- Bacs à sable ---

    def add_sandbox(self, file: str, origin: str, heads: dict[str, int], note: str | None) -> int:
        with self.conn:
            cur = self.conn.execute("INSERT INTO sandboxes (file, origin, heads, note) VALUES (?, ?, ?, ?)",
                                    (file, origin, json.dumps(heads, sort_keys=True), note))
        return int(cur.lastrowid or 0)

    def next_sandbox_id(self) -> int:
        row = self.conn.execute("SELECT seq FROM sqlite_sequence WHERE name = 'sandboxes'").fetchone()
        return (row[0] if row else 0) + 1

    def sandboxes(self, include_dropped: bool = False) -> list[Sandbox]:
        rows = self.conn.execute("SELECT sandbox_id, file, origin, heads, status, created, note FROM sandboxes"
                                 " ORDER BY sandbox_id").fetchall()
        out = [Sandbox(r[0], r[1], r[2], json.loads(r[3]), r[4], r[5], r[6]) for r in rows]
        return out if include_dropped else [s for s in out if s.status == "active"]

    def sandbox(self, sandbox_id: int) -> Sandbox:
        for s in self.sandboxes(include_dropped=True):
            if s.id == sandbox_id:
                return s
        raise KeyError(f"bac à sable inconnu : {sandbox_id}")

    def drop_sandbox(self, sandbox_id: int) -> None:
        with self.conn:
            self.conn.execute("UPDATE sandboxes SET status = 'dropped' WHERE sandbox_id = ?", (sandbox_id,))
