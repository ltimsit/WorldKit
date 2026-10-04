"""Écran Atelier (I8, T4) : importer une source, lancer la couche « mentions », voir les mentions sur le texte,
garder, retirer, corriger, ajouter (par sélection), ignorer, avec une portée ; proposer le lot.

L'atelier écrit dans le **monde** (son magasin, hors journal) : c'est le travail de l'auteur. Les appels au modèle
sont estimés et confirmés (I-LLM-01).
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any
from urllib.parse import quote

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse


def spans_of(text: str, annotations: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Le texte découpé en morceaux (texte seul, ou portion annotée) ; les annotations imbriquées à part."""
    placed, nested = [], []
    for a in sorted((a for a in annotations if a["start"] is not None), key=lambda a: (a["start"], -a["end"])):
        if placed and a["start"] < placed[-1]["end"]:
            nested.append(a)
        else:
            placed.append(a)
    pieces, pos = [], 0
    for a in placed:
        if a["start"] > pos:
            pieces.append({"text": text[pos:a["start"]]})
        pieces.append({"text": text[a["start"]:a["end"]], "ann": a})
        pos = a["end"]
    if pos < len(text):
        pieces.append({"text": text[pos:]})
    return pieces, nested


def css_class(a: dict[str, Any]) -> str:
    v = a["value"]
    if a["status"] in ("removed", "ignored"):
        state = "off"
    elif a["confidence"] == "doubt" or (v.get("entity") is None and not v.get("new")):
        state = "doubt"
    elif v.get("new") or (v.get("entity") or "").startswith("new:"):
        state = "new"
    else:
        state = "known"
    return f"ann ann-{state}" + (" ann-author" if a["by_author"] else "")


def register(app: FastAPI, db: Path, render: Callable[..., HTMLResponse], page_factory: Callable[[], Any],
             templates: Any) -> None:
    templates.env.globals["atelier_spans"] = spans_of
    templates.env.globals["atelier_class"] = css_class

    @app.get("/atelier", response_class=HTMLResponse)
    def atelier_list(request: Request) -> HTMLResponse:
        page = page_factory()
        return render(request, "atelier_list.html", page, sources=page.call("atelier.sources").output or [],
                      error=None)

    @app.post("/atelier", response_class=HTMLResponse)
    async def atelier_import(request: Request) -> Any:
        form = await request.form()
        page = page_factory()
        result = page.call("atelier.import", {"text": str(form.get("text") or ""),
                                              "doc_id": str(form.get("doc_id") or "") or None,
                                              "nature": str(form.get("nature") or "diegetic"),
                                              "voice": str(form.get("voice") or "author")})
        if not result.ok:
            return render(request, "atelier_list.html", page, sources=page.call("atelier.sources").output or [],
                          error="; ".join(i.message for i in result.issues) or "import impossible")
        return RedirectResponse(f"/atelier/{quote(result.output['doc_id'])}", status_code=303)

    def source_page(request: Request, page: Any, doc_id: str, **extra: Any) -> HTMLResponse:
        view = page.call("atelier.view", {"doc_id": doc_id})
        if not view.ok:
            return render(request, "atelier_list.html", page, sources=page.call("atelier.sources").output or [],
                          error=f"source inconnue : {doc_id}")
        selected = request.query_params.get("ann")
        annotations = {a["id"]: a for p in view.output["passages"] for a in p["annotations"]}
        chosen = annotations.get(int(selected)) if selected and selected.isdigit() else None
        names = {e["id"]: e for e in view.output["entities"]}
        return render(request, "atelier.html", page, view=view.output, indicators=view.indicators, chosen=chosen,
                      names=names, **{"estimate": None, "message": None, "error": None, **extra})

    @app.get("/atelier/{doc_id}", response_class=HTMLResponse)
    def atelier_source(doc_id: str, request: Request) -> HTMLResponse:
        return source_page(request, page_factory(), doc_id)

    @app.post("/atelier/{doc_id}/run", response_class=HTMLResponse)
    async def atelier_run(doc_id: str, request: Request) -> Any:
        form = await request.form()
        page = page_factory()
        params = {"doc_id": doc_id, "model": bool(form.get("model")), "signals": bool(form.get("signals")),
                  "confirm": bool(form.get("confirm"))}
        result = page.call("atelier.run", params)
        if result.status == "pending":
            return source_page(request, page, doc_id, estimate=result)
        if not result.ok:
            return source_page(request, page, doc_id, error="; ".join(i.message for i in result.issues))
        return RedirectResponse(f"/atelier/{quote(doc_id)}", status_code=303)

    @app.post("/atelier/{doc_id}/annotate", response_class=HTMLResponse)
    async def atelier_annotate(doc_id: str, request: Request) -> Any:
        form = await request.form()
        page = page_factory()
        params: dict[str, Any] = {"doc_id": doc_id, "action": str(form.get("action")),
                                  "scope": str(form.get("scope") or "source")}
        for key in ("ann_id", "passage", "start", "end"):
            if form.get(key) not in (None, ""):
                params[key] = int(str(form.get(key)))
        entity = str(form.get("entity") or form.get("entity_free") or "").strip()
        if entity:
            params["entity"] = entity
        if form.get("type"):
            params["type"] = str(form.get("type"))
        result = page.call("atelier.annotate", params)
        if not result.ok:
            return source_page(request, page, doc_id, error="; ".join(i.message for i in result.issues))
        return RedirectResponse(f"/atelier/{quote(doc_id)}", status_code=303)

    @app.post("/atelier/{doc_id}/propose", response_class=HTMLResponse)
    async def atelier_propose(doc_id: str, request: Request) -> Any:
        page = page_factory()
        result = page.call("atelier.propose", {"doc_id": doc_id})
        if not result.ok:
            return source_page(request, page, doc_id, error="; ".join(i.message for i in result.issues))
        n = len(result.output["proposals"])
        return source_page(request, page, doc_id,
                           message=f"lot {result.output['batch']} : {n} proposition(s) dans la file de revue")
