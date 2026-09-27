"""Écran Mesures (cadre d'interface I-VUE-09 ; décisions I6) : historique en tableaux denses avec barres dessinées
côté serveur, lancement à coût contrôlé en tâche de fond, détail, comparaison de deux mesures jusqu'au passage."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import yaml
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from worldkit.service import Session, jobs

DEFAULT_BATCHES = "corpus/valmont-v1/valmont/docs/batches.yaml"
DEFAULT_GOLD = "corpus/valmont-v1/valmont/gold"


def _declared(path: str) -> list[str]:
    try:
        return [b["id"] for b in yaml.safe_load(Path(path).read_text(encoding="utf-8"))["batches"]]
    except (OSError, KeyError, TypeError, yaml.YAMLError):
        return []


def register(app: FastAPI, db: Path, render: Callable[..., HTMLResponse], page_factory: Callable[[], Any],
             templates: Any) -> None:
    from .pipeline import _profiles

    def listing(request: Request, page: Any, **extra: Any) -> HTMLResponse:
        history = page.call("eval.history", {}, None)
        return render(request, "measures.html", page, history=history.output or [], profiles=_profiles(),
                      batches=_declared(DEFAULT_BATCHES), defaults={"batches": DEFAULT_BATCHES, "oracle": DEFAULT_GOLD},
                      **{"estimate": None, "error": None, **extra})

    @app.get("/measures", response_class=HTMLResponse)
    def measures(request: Request) -> HTMLResponse:
        return listing(request, page_factory())

    @app.post("/measures", response_class=HTMLResponse)
    async def measures_start(request: Request) -> Any:
        form = await request.form()
        page = page_factory()
        params: dict[str, Any] = {"batches": str(form.get("batches") or DEFAULT_BATCHES),
                                  "oracle": str(form.get("oracle") or DEFAULT_GOLD),
                                  "batch": [str(b) for b in form.getlist("batch")],
                                  "repeat": int(str(form.get("repeat") or 1))}
        if form.get("extractor") == "profile" and form.get("profile"):
            params["profile"] = str(form.get("profile"))
        if form.get("max_calls"):
            params["max_calls"] = int(str(form.get("max_calls")))
        if form.get("confirm"):
            params["confirm"] = True
        if params.get("profile") and not params.get("confirm"):
            estimate = page.call("eval.run", params, None, record=False)  # s'arrête à l'estimation : aucun appel
            if estimate.status in ("pending", "refused"):
                return listing(request, page, estimate=estimate)
        try:
            run_id = jobs.start(db, "eval.run", params)
        except (KeyError, ValueError) as e:
            return listing(request, page, error=str(e))
        return RedirectResponse(f"/measures/{run_id}", status_code=303)

    def view(run_id: int) -> dict[str, Any]:
        with Session(db) as s:
            status, progress = s.runs.progress(run_id)
            result = None if status in ("running", "interrupted") else s.runs.result(run_id)
        return {"id": run_id, "status": status, "progress": progress, "result": result}

    @app.get("/measures/{run_id}", response_class=HTMLResponse)
    def measure(run_id: int, request: Request) -> HTMLResponse:
        return render(request, "measure.html", page_factory(), run=view(run_id))

    @app.get("/fragments/measure/{run_id}", response_class=HTMLResponse)
    def measure_fragment(run_id: int, request: Request) -> HTMLResponse:
        return templates.TemplateResponse(request, "_measure_status.html", {"run": view(run_id)})

    @app.get("/measures-compare", response_class=HTMLResponse)
    def compare(request: Request) -> HTMLResponse:
        page = page_factory()
        a, b = request.query_params.get("a"), request.query_params.get("b")
        result = page.call("eval.compare", {"a": int(a), "b": int(b)}, None) if a and b else None
        return render(request, "measures_compare.html", page, result=result, a=a or "", b=b or "")
