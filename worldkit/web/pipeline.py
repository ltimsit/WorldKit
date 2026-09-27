"""Banc de pipeline (cadre d'interface I-VUE-03 ; décisions I4) : étapes de x à y en tâche de fond, suivi en
direct, arrêt, artefacts par étape, réinjection, enregistrement, comparaison de deux exécutions.

Tout passe par le service (`pipeline.*`, `runs.*`) ; la page ne fait que lancer, suivre et montrer (I-PRI-02).
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import yaml
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from worldkit.service import Session, jobs

STAGES = ["E1", "E2", "E3", "E4", "E5", "E6", "E7", "E8", "E9", "E9+", "E10", "E11", "E12"]
DEFAULTS = {"batch_id": "b4", "batches": "corpus/valmont-v1/valmont/docs/batches.yaml",
            "oracle": "corpus/valmont-v1/valmont/gold"}


def _profiles() -> list[str]:
    try:
        from worldkit.periphery.llm import load_config
        return sorted(load_config().profiles)
    except Exception:  # configuration illisible : l'oracle reste disponible
        return []


def register(app: FastAPI, db: Path, render: Callable[..., HTMLResponse], page_factory: Callable[[], Any],
             templates: Any) -> None:
    jobs.mark_interrupted(db)

    def form_params(form: Any) -> tuple[dict[str, Any], str | None]:
        """Formulaire → paramètres de pipeline.run (cible à part)."""
        get = lambda k: str(form.get(k, "") or "").strip()  # noqa: E731
        params: dict[str, Any] = {"batch_id": get("batch_id") or "lot", "from": get("from") or "E1",
                                  "to": get("to") or "E9"}
        docs = [line.strip() for line in get("documents").splitlines() if line.strip()]
        if docs:
            params["documents"] = docs
        elif get("batches"):
            params["batches"] = get("batches")
            if get("batch"):
                params["batch"] = get("batch")
        if get("extractor") == "profile" and get("profile"):
            params["profile"] = get("profile")
        elif get("oracle"):
            params["oracle"] = get("oracle")
        if get("input"):
            params["input"] = int(get("input"))
            if get("input_stage"):
                params["input_stage"] = get("input_stage")
        if get("artifact"):
            params["artifact"] = yaml.safe_load(get("artifact"))
        if get("max_calls"):
            params["max_calls"] = int(get("max_calls"))
        if form.get("confirm"):
            params["confirm"] = True
        return params, (get("target") or None)

    @app.get("/pipeline", response_class=HTMLResponse)
    def pipeline_form(request: Request) -> HTMLResponse:
        page = page_factory()
        q = request.query_params
        values = {**DEFAULTS, **{k: v for k, v in q.items()}}
        runs = page.call("runs.list", {"limit": 15, "operation": "pipeline.run"}, None)
        return render(request, "pipeline.html", page, values=values, stages=STAGES, profiles=_profiles(),
                      runs=runs.output or [], error=None, estimate=None)

    @app.post("/pipeline", response_class=HTMLResponse)
    async def pipeline_start(request: Request) -> Any:
        form = await request.form()
        page = page_factory()
        try:
            params, target = form_params(form)
        except (ValueError, yaml.YAMLError) as e:
            params, target = {}, None
            error = f"paramètres illisibles : {e}"
        else:
            error = None
        if error is None and params.get("profile") and not params.get("confirm") \
                and STAGES.index(params["from"]) <= STAGES.index("E4") <= STAGES.index(params["to"]):
            estimate = page.call("pipeline.estimate", {k: v for k, v in params.items()
                                                        if k in ("batch_id", "documents", "batches", "batch", "profile")},
                                 target)
            if estimate.ok and estimate.output["calls"] > 0:  # I-LLM-01 : estimation exacte, puis confirmation
                runs = page.call("runs.list", {"limit": 15, "operation": "pipeline.run"}, None)
                return render(request, "pipeline.html", page, values={**DEFAULTS, **{k: str(v) for k, v in form.items()}},
                              stages=STAGES, profiles=_profiles(), runs=runs.output or [], error=None,
                              estimate=estimate)
        if error is None:
            try:
                run_id = jobs.start(db, "pipeline.run", params, target)
            except (KeyError, ValueError) as e:
                error = str(e)
            else:
                return RedirectResponse(f"/pipeline/{run_id}", status_code=303)
        runs = page.call("runs.list", {"limit": 15, "operation": "pipeline.run"}, None)
        return render(request, "pipeline.html", page, values={**DEFAULTS, **{k: str(v) for k, v in form.items()}},
                      stages=STAGES, profiles=_profiles(), runs=runs.output or [], error=error, estimate=None)

    def run_view(run_id: int) -> dict[str, Any]:
        with Session(db) as s:
            status, progress = s.runs.progress(run_id)
            stages = s.runs.artifact_stages(run_id)
            result = None if status in ("running", "interrupted") else s.runs.result(run_id)
            record = next((r for r in s.runs.runs(limit=None) if r.id == run_id), None)
        return {"id": run_id, "status": status, "progress": progress, "stages": stages, "result": result,
                "record": record, "live": run_id in {j.run_id for j in jobs.running(db)}}

    @app.get("/pipeline/{run_id}", response_class=HTMLResponse)
    def pipeline_run(run_id: int, request: Request) -> HTMLResponse:
        page = page_factory()
        return render(request, "pipeline_run.html", page, run=run_view(run_id), stages=STAGES)

    @app.get("/fragments/run/{run_id}", response_class=HTMLResponse)
    def run_fragment(run_id: int, request: Request) -> HTMLResponse:
        return templates.TemplateResponse(request, "_run_status.html", {"run": run_view(run_id), "stages": STAGES})

    @app.post("/pipeline/{run_id}/cancel")
    def pipeline_cancel(run_id: int) -> RedirectResponse:
        jobs.cancel(db, run_id)
        return RedirectResponse(f"/pipeline/{run_id}", status_code=303)

    @app.post("/pipeline/{run_id}/save", response_class=HTMLResponse)
    async def pipeline_save(run_id: int, request: Request) -> HTMLResponse:
        from .actions import WORLD_CONFIRM
        form = await request.form()
        page = page_factory()
        choice = str(form.get("destination", "new"))
        decisions_text = str(form.get("decisions", "") or "")
        params: dict[str, Any] = {"input": run_id, "to": str(form.get("to") or "E9+")}
        error = None
        try:
            decisions = yaml.safe_load(decisions_text) if decisions_text.strip() else []
            if decisions:
                params["decisions"] = decisions
        except yaml.YAMLError as e:
            error = f"décisions illisibles : {e}"
        result, target = None, None
        if error is None:
            if choice == "world":
                if form.get(WORLD_CONFIRM):
                    target = "world"
                else:
                    error = "écrire dans le monde de travail demande de cocher la confirmation (I-PRI-04)"
            elif choice in ("", "new"):
                created = page.call("sandbox.create", {"note": f"lot de l'exécution {run_id}"}, None)
                target = str(created.output["id"]) if created.ok else None
            else:
                target = choice
        if error is None and target:
            result = page.call("pipeline.save", params, None if target == "world" else target)
        return render(request, "pipeline_run.html", page, run=run_view(run_id), stages=STAGES,
                      saved=result, save_error=error, save_target=target)

    @app.get("/runs/{run_id}/artifact/{stage}", response_class=HTMLResponse)
    def artifact(run_id: int, stage: str, request: Request) -> HTMLResponse:
        page = page_factory()
        result = page.call("runs.artifact", {"id": run_id, "stage": stage}, None)
        art = result.output["artifact"] if result.ok else None
        following = STAGES[STAGES.index(stage) + 1] if stage in STAGES[:8] else "E9"
        return render(request, "artifact.html", page, result=result, art=art, run_id=run_id, stage=stage,
                      stage_next=following,
                      pretty=json.dumps(art, ensure_ascii=False, indent=1, sort_keys=True) if art else "",
                      yaml_text=yaml.safe_dump(art, allow_unicode=True, sort_keys=False, width=110) if art else "")

    @app.get("/runs-diff", response_class=HTMLResponse)
    def diff(request: Request) -> HTMLResponse:
        page = page_factory()
        a, b = request.query_params.get("a"), request.query_params.get("b")
        result = page.call("runs.diff", {"a": int(a), "b": int(b)}, None) if a and b else None
        return render(request, "diff.html", page, result=result, a=a or "", b=b or "")
