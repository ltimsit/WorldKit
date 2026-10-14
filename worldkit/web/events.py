"""Suivi poussé d'une exécution (I-WEB-04) : Server-Sent Events, du serveur vers le navigateur.

`GET /events/run/{id}` envoie la progression de l'exécution (étape, appel en cours sur le total, appels faits) dès
qu'elle change, puis un événement `done` quand elle n'est plus en cours (finie, refusée, interrompue), et se ferme.
La progression est celle qu'écrit la tâche de fond dans `monde.runs.db` (décision I4) : le flux la relit toutes les
demi-secondes côté serveur, le navigateur n'interroge plus rien. Aucune dépendance : `EventSource` côté navigateur.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse

from worldkit.service import jobs
from worldkit.service.session import Session

POLL_SECONDS = 0.5


def snapshot(db: Path, run_id: int) -> dict[str, Any] | None:
    """État d'une exécution pour le flux : statut, progression, tâche vivante ; None si elle n'existe pas."""
    with Session(db) as s:
        try:
            status, progress = s.runs.progress(run_id)
        except KeyError:
            return None
    return {"run": run_id, "status": status, "progress": progress,
            "live": run_id in {j.run_id for j in jobs.running(db)}}


def _event(name: str, data: dict[str, Any]) -> str:
    return f"event: {name}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


async def run_stream(db: Path, run_id: int, request: Request | None = None) -> AsyncIterator[str]:
    last = None
    while True:
        if request is not None and await request.is_disconnected():
            return
        state = snapshot(db, run_id)
        if state is None:
            yield _event("done", {"run": run_id, "status": "unknown"})
            return
        if state != last:
            yield _event("progress", state)
            last = state
        if state["status"] != "running" or not state["live"]:  # finie, ou serveur arrêté pendant l'exécution
            yield _event("done", state)
            return
        await asyncio.sleep(POLL_SECONDS)


def register(app: FastAPI, db: Path) -> None:
    @app.get("/events/run/{run_id}")
    def run_events(run_id: int, request: Request) -> StreamingResponse:
        return StreamingResponse(run_stream(db, run_id, request), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
