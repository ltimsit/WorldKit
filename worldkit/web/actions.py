"""Actions de l'application (jalon I3) : écritures, éditeur vérifié en direct, banc de mécanismes, rendre réel.

- Destination par défaut d'une écriture : un bac à sable (celui du contexte, ou un bac créé à la volée) ;
  le monde de travail exige d'être choisi **et** confirmé (décision I3, I-PRI-04).
- L'éditeur envoie le brouillon au service à chaque pause de frappe (`edit.check`) : rien n'est écrit ; les
  signalements sont rattachés aux lignes du YAML (présentation).
- Le banc de mécanismes est une console sur tout le registre (décision I3) : paramètres en YAML pré-remplis
  (exemple Valmont ou gabarit), résultat de forme commune, « rejouer » pour vérifier le déterminisme.
- Rendre réel : répétition à blanc, rapport, puis application en tout ou rien (décision I3).
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import yaml
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from worldkit.service import REGISTRY, Result, Session, describe

WORLD_CONFIRM = "confirm_world"


def lines_of_changes(text: str) -> dict[str, int]:
    """`changes[i]` → numéro de ligne (1…) dans le YAML saisi, pour rattacher un signalement à sa ligne."""
    try:
        node = yaml.compose(text)
    except yaml.YAMLError:
        return {}
    out: dict[str, int] = {}
    if isinstance(node, yaml.MappingNode):
        for key, value in node.value:
            if getattr(key, "value", None) == "changes" and isinstance(value, yaml.SequenceNode):
                for i, item in enumerate(value.value):
                    out[f"changes[{i}]"] = item.start_mark.line + 1
    return out


def parse_yaml(text: str) -> tuple[Any, str | None]:
    try:
        return yaml.safe_load(text) if text.strip() else {}, None
    except yaml.YAMLError as e:
        return None, f"YAML illisible : {e}"


def register(app: FastAPI, db: Path, render: Callable[..., HTMLResponse], page_factory: Callable[[], Any],
             templates: Any) -> None:

    def run(page: Any, op: str, params: dict[str, Any], target: str | None) -> Result:
        return page.call(op, params, target)

    def destination(page: Any, choice: str, confirmed: bool) -> tuple[str | None, str | None]:
        """Rend (cible, erreur). « new » crée un bac à la volée ; « world » exige la confirmation."""
        if choice == "world":
            if not confirmed:
                return None, "écrire dans le monde de travail demande de cocher la confirmation (I-PRI-04)"
            return "world", None
        if choice in ("", "new"):
            created = run(page, "sandbox.create", {"note": "créé par l'interface"}, None)
            return (str(created.output["id"]) if created.ok else None), (None if created.ok else "bac non créé")
        return choice, None

    # --- API en écriture (I-SVC-01) ---

    @app.post("/api/call/{operation}")
    async def api_post(operation: str, request: Request) -> JSONResponse:
        op = REGISTRY.get(operation)
        if op is None:
            return JSONResponse({"error": f"opération inconnue : {operation}"}, status_code=404)
        body = await request.json() if await request.body() else {}
        target = body.get("target") or None
        if op.kind == "write" and target in (None, "world") and not body.get(WORLD_CONFIRM):
            return JSONResponse({"error": f"{operation} écrirait dans le monde de travail : viser un bac, ou passer "
                                          f"« {WORLD_CONFIRM}: true » (I-PRI-04)"}, status_code=409)
        with Session(db) as s:
            result = s.call(operation, body.get("params") or {}, None if target == "world" else target)
        return JSONResponse(json.loads(result.to_json()), status_code=200 if result.status != "error" else 400)

    # --- Éditeur d'édition (I-SAI-01) ---

    TEMPLATES = {
        "set_attribute": "  - { op: set_attribute, entity: ENTITÉ, attribute: ATTRIBUT, value: VALEUR }",
        "add_value": "  - { op: add_value, entity: ENTITÉ, attribute: ATTRIBUT, value: VALEUR }",
        "add_relation": "  - { op: add_relation, from: SOURCE, relation: RELATION, to: CIBLE }",
        "remove_relation": "  - { op: remove_relation, from: SOURCE, relation: RELATION, to: CIBLE }",
        "create_entity": "  - { op: create_entity, entity: IDENTIFIANT, type: TYPE }\n"
                         "  - { op: set_attribute, entity: IDENTIFIANT, attribute: name, value: NOM }",
        "close_entity": "  - { op: close_entity, entity: ENTITÉ }",
        "set_visibility": "  - { op: set_visibility, target: { entity: ENTITÉ, attribute: ATTRIBUT }, value: secret }",
        "sheet": "  - { op: create_entity, entity: ENTITÉ@SYSTÈME, type: Sheet, sheet: { of: ENTITÉ, system: SYSTÈME, "
                 "category: CATÉGORIE } }",
    }
    STARTER = "id: essai-1\norigin: enrichment\nchanges:\n" + TEMPLATES["set_attribute"] + "\n"

    def check(page: Any, text: str, target: str | None, point: str | None) -> dict[str, Any]:
        raw, error = parse_yaml(text)
        if error or not isinstance(raw, dict):
            return {"error": error or "une édition est un dictionnaire (id, origin, changes)", "result": None}
        params: dict[str, Any] = {"edit": raw}
        if point:
            params["point"] = point
        result = run(page, "edit.check", params, target)
        lines = lines_of_changes(text)
        return {"error": None, "result": result, "lines": {i.path: lines.get(i.path) for i in result.issues}}

    def check_target(choice: str) -> str | None:
        return None if choice in ("", "new", "world") else choice

    @app.get("/editor", response_class=HTMLResponse)
    def editor(request: Request) -> HTMLResponse:
        page = page_factory()
        target = request.query_params.get("target") or None
        index = run(page, "wiki.index", {}, target)
        text = request.query_params.get("yaml") or STARTER
        return render(request, "editor.html", page, text=text, templates=TEMPLATES, index=index,
                      checked=check(page, text, target, None), outcome=None, dest=target or "new")

    @app.post("/fragments/check", response_class=HTMLResponse)
    async def fragment_check(request: Request) -> HTMLResponse:
        form = await request.form()
        page = page_factory()
        checked = check(page, str(form.get("yaml", "")), check_target(str(form.get("destination", ""))),
                        str(form.get("point", "")) or None)
        return templates.TemplateResponse(request, "_check.html", {"checked": checked})

    @app.post("/editor", response_class=HTMLResponse)
    async def editor_run(request: Request) -> HTMLResponse:
        form = await request.form()
        page = page_factory()
        text, choice = str(form.get("yaml", "")), str(form.get("destination", "new"))
        action = "edit.submit" if form.get("action") == "submit" else "edit.apply"
        raw, error = parse_yaml(text)
        outcome: dict[str, Any] = {"error": error, "result": None, "target": None}
        if not error:
            target, error = destination(page, choice, bool(form.get(WORLD_CONFIRM)))
            outcome.update(error=error, target=target)
            if target:
                params: dict[str, Any] = {"edit": raw}
                if form.get("point"):
                    params["point"] = str(form.get("point"))
                outcome["result"] = run(page, action, params, None if target == "world" else target)
        target_ctx = outcome["target"] if outcome["target"] not in (None, "world") else None
        index = run(page, "wiki.index", {}, target_ctx)
        return render(request, "editor.html", page, text=text, templates=TEMPLATES, index=index,
                      checked=check(page, text, target_ctx, None), outcome=outcome, dest=target_ctx or choice)

    # --- Banc de mécanismes (décision I3) ---

    def initial_params(name: str) -> str:
        op = REGISTRY[name]
        d = describe(op)
        body = op.example if op.example is not None else d["template"]
        return yaml.safe_dump(body, allow_unicode=True, sort_keys=False, width=100) if body else "{}\n"

    @app.get("/bench", response_class=HTMLResponse)
    def bench(request: Request) -> HTMLResponse:
        page = page_factory()
        name = request.query_params.get("op") or "change.keys"
        if name not in REGISTRY:
            name = "change.keys"
        ops = run(page, "ops.list", {}, None)
        return render(request, "bench.html", page, ops=ops.output, op=describe(REGISTRY[name]),
                      params_text=initial_params(name), result=None, previous=None, error=None)

    @app.post("/bench", response_class=HTMLResponse)
    async def bench_run(request: Request) -> HTMLResponse:
        form = await request.form()
        page = page_factory()
        name, text = str(form.get("op", "")), str(form.get("params", ""))
        choice = str(form.get("destination", ""))
        ops = run(page, "ops.list", {}, None)
        if name not in REGISTRY:
            return RedirectResponse("/bench", status_code=303)
        op = REGISTRY[name]
        params, error = parse_yaml(text)
        result: Result | None = None
        if not error and not isinstance(params, dict):
            error = "les paramètres sont un dictionnaire YAML"
        if not error:
            target: str | None = choice or None
            if op.kind == "write":
                target, error = destination(page, choice or "new", bool(form.get(WORLD_CONFIRM)))
            if not error:
                result = run(page, name, params, None if target in (None, "world") else target)
        previous = None
        if result is not None and form.get("compare_to"):
            with Session(db) as s:
                before = s.runs.result(int(str(form.get("compare_to"))))
            previous = {"run": before.trace.run_id, "same": before.stable() == result.stable()}
        return render(request, "bench.html", page, ops=ops.output, op=describe(op), params_text=text,
                      result=result, previous=previous, error=error, dest=choice)

    # --- Rendre réel (I-SBX-01, décision I3) ---

    @app.get("/sandbox/{sandbox_id}/promote", response_class=HTMLResponse)
    def promote(sandbox_id: int, request: Request) -> HTMLResponse:
        page = page_factory()
        result = run(page, "sandbox.promote", {"id": sandbox_id}, None)
        return render(request, "promote.html", page, sandbox_id=sandbox_id, result=result, applied=False)

    @app.post("/sandbox/{sandbox_id}/promote", response_class=HTMLResponse)
    async def promote_apply(sandbox_id: int, request: Request) -> HTMLResponse:
        form = await request.form()
        page = page_factory()
        if not form.get(WORLD_CONFIRM):
            result = run(page, "sandbox.promote", {"id": sandbox_id}, None)
            return render(request, "promote.html", page, sandbox_id=sandbox_id, result=result, applied=False,
                          error="cocher la confirmation pour écrire dans le monde de travail")
        result = run(page, "sandbox.promote", {"id": sandbox_id, "confirm": True}, None)
        return render(request, "promote.html", page, sandbox_id=sandbox_id, result=result, applied=True)
