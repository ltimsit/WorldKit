"""Revue complète et acceptation (cadre d'interface I-VUE-05, I-ACC-01 ; décisions I5).

- **Revue** : la file de la cible affichée (propositions, questions de nature, passages signalés, rejeux ouverts).
  Sur un bac, les décisions s'appliquent directement. Sur le monde de travail, l'écran est en lecture jusqu'à
  l'ouverture d'une **session de revue**, confirmée une fois, limitée dans le temps (30 minutes, prolongée à
  chaque décision) et affichée en permanence (décision I5, I-PRI-04).
- **Acceptation** : les parcours du corpus, exécutés en tâche de fond par `walkthrough.run`, chaque étape et
  chaque attendu montrés (réussi, échoué, non structuré).
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import yaml
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from worldkit.service import Session, jobs

SESSION_LENGTH = timedelta(minutes=30)


def register(app: FastAPI, db: Path, render: Callable[..., HTMLResponse], page_factory: Callable[[], Any],
             templates: Any) -> None:
    state: dict[str, Any] = {"until": None}  # session de revue du monde de travail (un seul utilisateur, local)

    def session_open() -> bool:
        return state["until"] is not None and datetime.now() < state["until"]

    def review_page(request: Request, page: Any, target: str | None, last: Any = None, error: str | None = None) -> HTMLResponse:
        q = request.query_params
        params = {k: q[k] for k in ("batch",) if q.get(k)}
        listing = page.call("review.list", {**params, "awaiting": True}, target)
        replays = page.call("replay.list", {}, target)
        proposals = (listing.output or {}).get("proposals", [])
        tag, doc = q.get("tag"), q.get("doc")
        if tag:
            proposals = [p for p in proposals if tag in p["tags"]]
        if doc:
            proposals = [p for p in proposals if p["doc"] == doc]
        details = {p["id"]: page.call("review.show", {"proposal": p["id"]}, target).output for p in proposals}
        tags = sorted({t for p in (listing.output or {}).get("proposals", []) for t in p["tags"]})
        return render(request, "review.html", page, listing=listing, proposals=proposals, details=details,
                      replays=replays.output or [], tags=tags, target=target, last=last, error=error,
                      writable=bool(target) or session_open(), session_until=state["until"] if session_open() else None)

    @app.get("/review", response_class=HTMLResponse)
    def review(request: Request) -> HTMLResponse:
        page = page_factory()
        return review_page(request, page, request.query_params.get("target") or None)

    @app.post("/review/session", response_class=HTMLResponse)
    async def review_session(request: Request) -> Any:
        form = await request.form()
        if form.get("stop"):
            state["until"] = None
        elif form.get("confirm_world"):
            state["until"] = datetime.now() + SESSION_LENGTH
        return RedirectResponse("/review", status_code=303)

    @app.post("/review/decide", response_class=HTMLResponse)
    async def review_decide(request: Request) -> HTMLResponse:
        form = await request.form()
        page = page_factory()
        target = str(form.get("target") or "") or None
        if target is None and not session_open():
            return review_page(request, page, None, error="monde de travail en lecture : ouvrir une session de revue "
                                                          "(confirmée une fois) pour décider (I-PRI-04)")
        action = str(form.get("action", ""))
        pid = str(form.get("proposal", ""))
        try:
            op, params = decision(action, pid, form)
        except (ValueError, yaml.YAMLError) as e:
            return review_page(request, page, target, error=str(e))
        result = page.call(op, params, target)
        if target is None:
            state["until"] = datetime.now() + SESSION_LENGTH  # prolongée à chaque décision
        return review_page(request, page, target, last=result)

    def decision(action: str, pid: str, form: Any) -> tuple[str, dict[str, Any]]:
        reason = str(form.get("reason") or "") or None
        extra = {"reason": reason} if reason else {}
        if action == "accept":
            keep = [int(k) for k in form.getlist("keep")]
            total = int(form.get("total", 0) or 0)
            params: dict[str, Any] = {"proposals": [pid], **extra}
            if total and len(keep) < total:
                params["keep"] = keep
            return "review.accept", params
        if action == "refuse":
            return "review.refuse", {"proposals": [pid], **extra}
        if action == "choose":
            return "review.choose", {"proposal": pid, **extra}
        if action == "abandon":
            return "review.abandon", {"proposals": [pid], **extra}
        if action == "qualify":
            return "review.qualify", {"target": pid, "value": str(form.get("value")), **extra}
        if action == "promote":
            return "review.promote", {"proposal": pid, **({"visibility": form.get("visibility")} if form.get("visibility") else {})}
        if action == "adapt":
            changes = yaml.safe_load(str(form.get("changes") or "")) or []
            if not isinstance(changes, list):
                raise ValueError("adapter : une liste de changements (YAML)")
            return "review.adapt", {"proposal": pid, "changes": changes, "replace": bool(form.get("replace")), **extra}
        if action == "nature":
            return "review.nature", {"document": str(form.get("document")), "passage": int(str(form.get("passage"))),
                                     "decision": str(form.get("decision")), **extra}
        if action == "dismiss":
            return "review.dismiss", {"document": str(form.get("document")), "passage": int(str(form.get("passage")))}
        if action in ("keep", "discard"):
            return "replay.decide", {"id": str(form.get("replay")), "action": action, **extra}
        raise ValueError(f"décision inconnue : {action}")

    # --- Acceptation (I-ACC-01) ---

    @app.get("/acceptance", response_class=HTMLResponse)
    def acceptance(request: Request) -> HTMLResponse:
        page = page_factory()
        listing = page.call("walkthrough.list", {}, None)
        runs = page.call("runs.list", {"limit": 30, "operation": "walkthrough.run"}, None)
        return render(request, "acceptance.html", page, listing=listing, runs=runs.output or [], error=None)

    @app.post("/acceptance", response_class=HTMLResponse)
    async def acceptance_start(request: Request) -> Any:
        form = await request.form()
        try:
            run_id = jobs.start(db, "walkthrough.run", {"id": str(form.get("id"))})
        except (KeyError, ValueError) as e:
            page = page_factory()
            listing = page.call("walkthrough.list", {}, None)
            return render(request, "acceptance.html", page, listing=listing, runs=[], error=str(e))
        return RedirectResponse(f"/acceptance/{run_id}", status_code=303)

    def acceptance_view(run_id: int) -> dict[str, Any]:
        with Session(db) as s:
            status, progress = s.runs.progress(run_id)
            result = None if status in ("running", "interrupted") else s.runs.result(run_id)
        return {"id": run_id, "status": status, "progress": progress, "result": result}

    @app.get("/acceptance/{run_id}", response_class=HTMLResponse)
    def acceptance_run(run_id: int, request: Request) -> HTMLResponse:
        page = page_factory()
        return render(request, "acceptance_run.html", page, run=acceptance_view(run_id))

    @app.get("/fragments/acceptance/{run_id}", response_class=HTMLResponse)
    def acceptance_fragment(run_id: int, request: Request) -> HTMLResponse:
        return templates.TemplateResponse(request, "_acceptance_status.html", {"run": acceptance_view(run_id)})
