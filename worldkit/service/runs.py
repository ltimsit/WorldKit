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
CREATE TABLE IF NOT EXISTS artifacts (
    run_id INTEGER NOT NULL, stage TEXT NOT NULL, artifact TEXT NOT NULL, PRIMARY KEY (run_id, stage));
CREATE TABLE IF NOT EXISTS sandboxes (
    sandbox_id INTEGER PRIMARY KEY AUTOINCREMENT, file TEXT NOT NULL, origin TEXT NOT NULL, heads TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active', created TEXT NOT NULL DEFAULT (datetime('now')), note TEXT,
    after_run INTEGER NOT NULL DEFAULT 0);
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
    status: str            # active | dropped | promoted (rendu réel, I3)
    created: str
    note: str | None = None
    after_run: int = 0     # dernière exécution enregistrée au moment de la copie (chaîne de rejeu, I3)

    @property
    def target(self) -> str:
        return f"sandbox:{self.id}"


class RunStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.conn = sqlite3.connect(str(self.path))
        self.conn.executescript(_DDL)
        cols = {r[1] for r in self.conn.execute("PRAGMA table_info(sandboxes)")}
        if "after_run" not in cols:  # journaux créés avant I3
            self.conn.execute("ALTER TABLE sandboxes ADD COLUMN after_run INTEGER NOT NULL DEFAULT 0")
        if "progress" not in {r[1] for r in self.conn.execute("PRAGMA table_info(runs)")}:  # avant I4
            self.conn.execute("ALTER TABLE runs ADD COLUMN progress TEXT")

    def close(self) -> None:
        self.conn.close()

    # --- Exécutions ---

    def record(self, result: Result, run_id: int | None = None) -> int:
        if run_id is None:
            with self.conn:
                cur = self.conn.execute(
                    "INSERT INTO runs (operation, kind, target, status, params, result) VALUES (?, ?, ?, ?, ?, ?)",
                    (result.operation, result.kind, result.target, result.status,
                     json.dumps(result.params, ensure_ascii=False, sort_keys=True), result.to_json(None)))
            run_id = int(cur.lastrowid or 0)
        else:
            with self.conn:
                self.conn.execute("UPDATE runs SET status = ?, params = ? WHERE run_id = ?",
                                  (result.status, json.dumps(result.params, ensure_ascii=False, sort_keys=True), run_id))
        result.trace.run_id = run_id
        with self.conn:
            self.conn.execute("UPDATE runs SET result = ? WHERE run_id = ?", (result.to_json(None), run_id))
        return run_id

    # --- Exécutions longues (tâches de fond, décision I4) ---

    def begin(self, operation: str, kind: str, target: str, params: dict[str, Any]) -> int:
        """Crée l'exécution « en cours » avant qu'elle ne commence ; `record(result, run_id)` la terminera."""
        with self.conn:
            cur = self.conn.execute(
                "INSERT INTO runs (operation, kind, target, status, params, result) VALUES (?, ?, ?, 'running', ?, '{}')",
                (operation, kind, target, json.dumps(params, ensure_ascii=False, sort_keys=True)))
        return int(cur.lastrowid or 0)

    def set_progress(self, run_id: int, progress: dict[str, Any]) -> None:
        with self.conn:
            self.conn.execute("UPDATE runs SET progress = ? WHERE run_id = ?",
                              (json.dumps(progress, ensure_ascii=False), run_id))

    def progress(self, run_id: int) -> tuple[str, dict[str, Any]]:
        row = self.conn.execute("SELECT status, progress FROM runs WHERE run_id = ?", (run_id,)).fetchone()
        if row is None:
            raise KeyError(f"exécution inconnue : {run_id}")
        return row[0], json.loads(row[1]) if row[1] else {}

    # --- Artefacts des étapes (I-PIP-01) ---

    def save_artifact(self, run_id: int, stage: str, artifact: str) -> None:
        with self.conn:
            self.conn.execute("INSERT OR REPLACE INTO artifacts VALUES (?, ?, ?)", (run_id, stage, artifact))

    def artifact(self, run_id: int, stage: str | None = None) -> tuple[str, str]:
        """(étape, JSON) : l'artefact d'une étape, ou le dernier de l'exécution."""
        rows = self.conn.execute("SELECT stage, artifact FROM artifacts WHERE run_id = ?", (run_id,)).fetchall()
        if not rows:
            raise KeyError(f"aucun artefact pour l'exécution {run_id}")
        from worldkit.ingest.stages import STAGES
        by = dict(rows)
        if stage is None:
            stage = max(by, key=STAGES.index)
        if stage not in by:
            raise KeyError(f"exécution {run_id} : pas d'artefact pour {stage} (connus : {', '.join(sorted(by, key=STAGES.index))})")
        return stage, by[stage]

    def artifact_stages(self, run_id: int) -> list[str]:
        from worldkit.ingest.stages import STAGES
        return sorted((s for (s,) in self.conn.execute("SELECT stage FROM artifacts WHERE run_id = ?", (run_id,))),
                      key=STAGES.index)

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

    def purge(self, ids: list[int] | None = None, before: int | None = None, everything: bool = False,
              keep: int | None = None) -> int:
        """Purge manuelle (I-RUN-01) : sans effet sur l'histoire du monde ; `keep` : l'exécution de la purge."""
        spare = keep if keep is not None else -1
        with self.conn:
            if everything:
                cur = self.conn.execute("DELETE FROM runs WHERE run_id != ?", (spare,))
            elif before is not None:
                cur = self.conn.execute("DELETE FROM runs WHERE run_id < ? AND run_id != ?", (before, spare))
            else:
                cur = self.conn.executemany("DELETE FROM runs WHERE run_id = ? AND run_id != ?",
                                            [(i, spare) for i in ids or []])
            self.conn.execute("DELETE FROM artifacts WHERE run_id NOT IN (SELECT run_id FROM runs)")
        return cur.rowcount

    # --- Bacs à sable ---

    def last_run(self) -> int:
        row = self.conn.execute("SELECT MAX(run_id) FROM runs").fetchone()
        return row[0] or 0

    def add_sandbox(self, file: str, origin: str, heads: dict[str, int], note: str | None) -> int:
        with self.conn:
            cur = self.conn.execute("INSERT INTO sandboxes (file, origin, heads, note, after_run) VALUES (?, ?, ?, ?, ?)",
                                    (file, origin, json.dumps(heads, sort_keys=True), note, self.last_run()))
        return int(cur.lastrowid or 0)

    def next_sandbox_id(self) -> int:
        row = self.conn.execute("SELECT seq FROM sqlite_sequence WHERE name = 'sandboxes'").fetchone()
        return (row[0] if row else 0) + 1

    def sandboxes(self, include_dropped: bool = False) -> list[Sandbox]:
        rows = self.conn.execute("SELECT sandbox_id, file, origin, heads, status, created, note, after_run"
                                 " FROM sandboxes ORDER BY sandbox_id").fetchall()
        out = [Sandbox(r[0], r[1], r[2], json.loads(r[3]), r[4], r[5], r[6], r[7]) for r in rows]
        return out if include_dropped else [s for s in out if s.status == "active"]

    def sandbox(self, sandbox_id: int) -> Sandbox:
        for s in self.sandboxes(include_dropped=True):
            if s.id == sandbox_id:
                return s
        raise KeyError(f"bac à sable inconnu : {sandbox_id}")

    def drop_sandbox(self, sandbox_id: int) -> None:
        self.set_status(sandbox_id, "dropped")

    def set_status(self, sandbox_id: int, status: str) -> None:
        with self.conn:
            self.conn.execute("UPDATE sandboxes SET status = ? WHERE sandbox_id = ?", (status, sandbox_id))

    def writes(self, target: str, upto: int | None = None) -> list[RunRecord]:
        """Écritures réussies d'une cible, dans l'ordre (matière de « rendre réel », I-SBX-01)."""
        rows = self.conn.execute(
            "SELECT run_id, operation, kind, target, status, params, created FROM runs WHERE target = ? AND kind = 'write'"
            " AND (? IS NULL OR run_id <= ?) ORDER BY run_id", (target, upto, upto)).fetchall()
        return [RunRecord(r[0], r[1], r[2], r[3], r[4], json.loads(r[5]), r[6]) for r in rows]
