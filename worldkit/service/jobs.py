"""Exécutions longues en tâche de fond (décision I4) : une extraction par un modèle prend des minutes.

`start(db, opération, paramètres, cible)` crée aussitôt l'exécution « en cours » dans `runs.db` et la lance dans
un fil ; la progression s'écrit dans l'exécution (étape, passages faits sur le total, appels) ; `cancel` demande
un arrêt propre entre deux groupes de passages. Un seul pipeline avec modèle à la fois par monde, pour ne pas
doubler la consommation sans le vouloir (I-LLM-01). Chaque fil ouvre sa propre session (SQLite).
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .registry import REGISTRY
from .session import Session, parse_target

_LOCK = threading.Lock()


@dataclass
class Job:
    run_id: int
    db: Path
    operation: str
    uses_model: bool
    cancel: threading.Event = field(default_factory=threading.Event)
    thread: threading.Thread | None = None


JOBS: dict[tuple[str, int], Job] = {}


def _uses_model(operation: str, params: dict[str, Any]) -> bool:
    if operation == "atelier.run":  # I8 : la couche « mentions » avec modèle
        return bool(params.get("model")) and bool(params.get("confirm"))
    return operation == "pipeline.run" and bool(params.get("profile")) and bool(params.get("confirm"))


def running(db: str | Path) -> list[Job]:
    key = str(Path(db).resolve())
    return [j for (k, _), j in JOBS.items() if k == key]


def start(db: str | Path, operation: str, params: dict[str, Any], target: str | int | None = None) -> int:
    db = Path(db)
    op = REGISTRY.get(operation)
    if op is None:
        raise KeyError(f"opération inconnue : {operation}")
    op.params.model_validate(params)  # paramètres invalides : refus immédiat, avant tout fil
    uses_model = _uses_model(operation, params)
    with _LOCK:
        if uses_model and any(j.uses_model for j in running(db)):
            raise ValueError("un appel au modèle est déjà en cours sur ce monde : attendre ou l'arrêter (I-LLM-01)")
        with Session(db) as s:
            run_id = s.runs.begin(operation, op.kind, parse_target(target), params)
        job = Job(run_id, db, operation, uses_model)
        JOBS[(str(db.resolve()), run_id)] = job

    def work() -> None:
        try:
            with Session(db) as s:
                s.call(operation, params, target, record=True, run_id=run_id, cancel=job.cancel)
        finally:
            with _LOCK:
                JOBS.pop((str(db.resolve()), run_id), None)

    job.thread = threading.Thread(target=work, name=f"worldkit-run-{run_id}", daemon=True)
    job.thread.start()
    return run_id


def cancel(db: str | Path, run_id: int) -> bool:
    job = JOBS.get((str(Path(db).resolve()), run_id))
    if job is None:
        return False
    job.cancel.set()
    return True


def wait(db: str | Path, run_id: int, timeout: float | None = None) -> None:
    job = JOBS.get((str(Path(db).resolve()), run_id))
    if job is not None and job.thread is not None:
        job.thread.join(timeout)


def mark_interrupted(db: str | Path) -> int:
    """Au démarrage du serveur : une exécution restée « en cours » sans fil vivant a été interrompue."""
    live = {j.run_id for j in running(db)}
    with Session(db) as s:
        rows = s.runs.conn.execute("SELECT run_id FROM runs WHERE status = 'running'").fetchall()
        stale = [r for (r,) in rows if r not in live]
        with s.runs.conn:
            for r in stale:
                s.runs.conn.execute("UPDATE runs SET status = 'interrupted' WHERE run_id = ?", (r,))
    return len(stale)
