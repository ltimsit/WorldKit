"""Application web locale (cadre d'interface I-TEC-01 ; jalon I2, lecture seule).

Chaque écran est le rendu d'un ou plusieurs `Result` de la couche de service (I-PRI-02) : l'application ne
calcule rien du domaine, elle appelle `Session.call` et met en page. Le contexte de lecture (cible, branche,
point, filtre) vit dans l'adresse (décision I2) ; chaque écran liste les appels qui l'ont produit, avec un
lien vers leur JSON brut (I-PRI-03, I-OBJ-06).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import yaml
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from worldkit.service import REGISTRY, Result, Session

HERE = Path(__file__).parent
CONTEXT_KEYS = ("target", "branch", "point", "filter")
READ_ONLY = {"read"}  # GET : consultations ; calculs et écritures passent par POST (I3)
NAME_KEYS = {"branch", "point", "entity", "document", "target", "batch", "batch_id", "origin", "note", "reason",
             "operation", "filter"}


def flatten(params: dict[str, Any], prefix: str = "") -> dict[str, Any]:
    """Paramètres imbriqués → clés pointées (`left.branch`), pour une adresse."""
    out: dict[str, Any] = {}
    for k, v in params.items():
        key = f"{prefix}{k}"
        if isinstance(v, dict):
            out.update(flatten(v, f"{key}."))
        elif v is not None:
            out[key] = v if isinstance(v, str) else json.dumps(v, ensure_ascii=False)
    return out


def nest(query: dict[str, str]) -> dict[str, Any]:
    """Clés pointées → dictionnaire imbriqué ; valeurs lues en YAML (`passage=6`, `all=true`) comme en ligne de
    commande (I-SVC-03). Une valeur vide est ignorée."""
    out: dict[str, Any] = {}
    for key, value in query.items():
        if value == "":
            continue
        node = out
        parts = key.split(".")
        for part in parts[:-1]:
            node = node.setdefault(part, {})
        if parts[-1] in NAME_KEYS:
            node[parts[-1]] = value  # un nom reste une chaîne, même s'il ressemble à un nombre
            continue
        try:
            node[parts[-1]] = yaml.safe_load(value)
        except yaml.YAMLError:
            node[parts[-1]] = value
    return out


def passage_html(line: dict[str, Any]) -> Any:
    """Un passage de « Ce que disent les documents » (R-VUE-05), échappé, ses portions surlignées : `mark.check`
    pour une portion à vérifier (casse différente du nom connu)."""
    from markupsafe import Markup, escape
    text, pos, out = line["text"], 0, []
    for start, end, check in sorted(line["spans"]):
        if start < pos:
            continue
        cls = ' class="check" title="à vérifier : casse différente du nom connu"' if check else ""
        out += [str(escape(text[pos:start])), f"<mark{cls}>{escape(text[start:end])}</mark>"]
        pos = end
    out.append(str(escape(text[pos:])))
    return Markup("".join(out))


class Page:
    """Les appels faits pour un écran, dans l'ordre : ils sont montrés sous l'écran."""

    def __init__(self, db: Path) -> None:
        self.db = db
        self.calls: list[Result] = []

    def call(self, op: str, params: dict[str, Any] | None = None, target: str | None = None,
             record: bool | None = None) -> Result:
        with Session(self.db) as s:
            result = s.call(op, params or {}, target, record)
        self.calls.append(result)
        return result


def create_app(db: str | Path) -> FastAPI:
    db = Path(db)
    app = FastAPI(title="worldkit — banc d'essai", docs_url="/api/docs", redoc_url=None)
    app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")
    templates = Jinja2Templates(directory=HERE / "templates")
    env = templates.env
    env.filters["factkey"] = lambda fact: json.dumps(fact)
    env.filters["yaml"] = lambda x: yaml.safe_dump(x, allow_unicode=True, sort_keys=False, width=100).rstrip()
    env.filters["tojson_pretty"] = lambda x: json.dumps(x, ensure_ascii=False, indent=2, sort_keys=True)
    env.filters["passage_html"] = passage_html

    def raw_link(r: Result) -> str:
        params = flatten(r.params)
        if r.target != "world":
            params["target"] = r.target.split(":", 1)[1]
        return f"/api/call/{r.operation}?{urlencode(params)}"

    env.globals["raw_link"] = raw_link
    from datetime import datetime
    from worldkit.service.session import code_version
    env.globals["server"] = {"version": code_version(), "started": datetime.now().strftime("%H:%M:%S")}

    def context(request: Request) -> dict[str, str]:
        return {k: request.query_params.get(k, "") for k in CONTEXT_KEYS}

    def qs(ctx: dict[str, str], **extra: str) -> str:
        return urlencode({k: v for k, v in {**ctx, **extra}.items() if v})

    env.globals["qs"] = qs

    def compare_qs(ctx: dict[str, str], left_filter: str | None = None, right_filter: str | None = None) -> str:
        """Adresse de comparaison : les deux côtés reprennent le contexte courant, filtres éventuellement forcés."""
        out: dict[str, str] = {}
        for side, forced in (("left", left_filter), ("right", right_filter)):
            for k in CONTEXT_KEYS:
                if ctx.get(k):
                    out[f"{side}.{k}"] = ctx[k]
            if forced:
                out[f"{side}.filter"] = forced
        return urlencode(out)

    def line_text(line: Any) -> str:
        """Texte court d'une ligne de différence (présentation)."""
        if line is None:
            return ""
        if isinstance(line, list):
            return " / ".join(map(str, line))
        name = line.get("name") or line.get("relation") or line.get("text") or line.get("other") or ""
        value = line.get("value", line.get("other", line.get("qualification", "")))
        return f"{name} = {value} [{line.get('visibility') or line.get('qualification_visibility') or ''}]"

    env.globals["compare_qs"] = compare_qs
    env.globals["line_text"] = line_text

    def render(request: Request, name: str, page: Page, **data: Any) -> HTMLResponse:
        ctx = context(request)
        boxes = page.call("sandbox.list").output or []
        branches = page.call("branch.list", {}, ctx["target"] or None)
        return templates.TemplateResponse(request, name, {
            "ctx": ctx, "sandboxes": boxes, "branches": branches.output["branches"] if branches.ok else [],
            "calls": page.calls, "path": request.url.path, **data})

    def params_of(ctx: dict[str, str], *keys: str) -> dict[str, Any]:
        return {k: ctx[k] for k in keys if ctx.get(k)}

    # --- API JSON (I-SVC-01) ---

    @app.get("/api/ops")
    def api_ops() -> JSONResponse:
        with Session(db) as s:
            return JSONResponse(json.loads(s.call("ops.list").to_json()))

    @app.get("/api/call/{operation}")
    def api_call(operation: str, request: Request) -> JSONResponse:
        op = REGISTRY.get(operation)
        if op is None:
            return JSONResponse({"error": f"opération inconnue : {operation}"}, status_code=404)
        if op.kind not in READ_ONLY:
            return JSONResponse({"error": f"{operation} est une opération « {op.kind} » : l'appeler en POST"},
                                status_code=405)
        query = dict(request.query_params)
        target = query.pop("target", None) or None
        with Session(db) as s:
            result = s.call(operation, nest(query), target)
        return JSONResponse(json.loads(result.to_json()), status_code=200 if result.status != "error" else 400)

    # --- Pages ---

    @app.get("/", response_class=HTMLResponse)
    def dashboard(request: Request) -> HTMLResponse:
        page = Page(db)
        ctx = context(request)
        target = ctx["target"] or None
        summary = page.call("world.summary", {}, target)
        check = page.call("state.check", params_of(ctx, "branch", "point"), target)
        runs = page.call("runs.list", {"limit": 12})
        return render(request, "dashboard.html", page, summary=summary, check=check, runs=runs)

    @app.get("/wiki", response_class=HTMLResponse)
    def wiki_index(request: Request) -> HTMLResponse:
        page = Page(db)
        ctx = context(request)
        index = page.call("wiki.index", params_of(ctx, "branch", "point", "filter"), ctx["target"] or None)
        return render(request, "wiki_index.html", page, index=index)

    @app.get("/schema", response_class=HTMLResponse)
    def schema_screen(request: Request) -> HTMLResponse:
        page = Page(db)
        ctx = context(request)
        params = params_of(ctx, "branch", "point")
        if request.query_params.get("scope"):
            params["scope"] = request.query_params["scope"]
        result = page.call("schema.show", params, ctx["target"] or None)
        return render(request, "schema.html", page, result=result)

    @app.get("/wiki/{entity}", response_class=HTMLResponse)
    def wiki_page(entity: str, request: Request) -> HTMLResponse:
        page = Page(db)
        ctx = context(request)
        result = page.call("wiki.page", {"entity": entity, **params_of(ctx, "branch", "point", "filter")},
                           ctx["target"] or None)
        return render(request, "wiki_page.html", page, entity=entity, result=result)

    @app.get("/compare/{entity}", response_class=HTMLResponse)
    def compare(entity: str, request: Request) -> HTMLResponse:
        page = Page(db)
        sides = nest({k: v for k, v in request.query_params.items() if k.startswith(("left.", "right."))})
        result = page.call("wiki.compare", {"entity": entity, **sides})
        marks: dict[str, dict[tuple[str, str], str]] = {"left": {}, "right": {}}
        for d in (result.output or {}).get("diff", []):
            key = (d["section"], d["key"])
            if d["status"] in ("removed", "changed"):
                marks["left"][key] = d["status"]
            if d["status"] in ("added", "changed"):
                marks["right"][key] = d["status"]
        return render(request, "compare.html", page, entity=entity, result=result, marks=marks, sides=sides)

    @app.get("/branches", response_class=HTMLResponse)
    def branches(request: Request) -> HTMLResponse:
        page = Page(db)
        ctx = context(request)
        result = page.call("branch.list", {}, ctx["target"] or None)
        return render(request, "branches.html", page, result=result, mermaid=_lineage(result))

    @app.get("/journal", response_class=HTMLResponse)
    def journal(request: Request) -> HTMLResponse:
        page = Page(db)
        ctx = context(request)
        result = page.call("journal.list", params_of(ctx, "branch"), ctx["target"] or None)
        return render(request, "journal.html", page, result=result)

    @app.get("/edit/{edit_id}", response_class=HTMLResponse)
    def edit(edit_id: str, request: Request) -> HTMLResponse:
        page = Page(db)
        ctx = context(request)
        result = page.call("edit.show", {"id": edit_id}, ctx["target"] or None)
        return render(request, "edit.html", page, result=result)

    @app.get("/runs", response_class=HTMLResponse)
    def runs(request: Request) -> HTMLResponse:
        page = Page(db)
        result = page.call("runs.list", {"limit": 100})
        return render(request, "runs.html", page, result=result)

    @app.get("/runs/{run_id}", response_class=HTMLResponse)
    def run(run_id: int, request: Request) -> HTMLResponse:
        page = Page(db)
        result = page.call("runs.show", {"id": run_id})
        stored = Result.model_validate(result.output) if result.ok else None
        return render(request, "run.html", page, result=result, stored=stored)

    @app.get("/ops", response_class=HTMLResponse)
    def ops(request: Request) -> HTMLResponse:
        page = Page(db)
        result = page.call("ops.list")
        return render(request, "ops.html", page, result=result)

    from .actions import register
    register(app, db, render, lambda: Page(db), templates)
    from .pipeline import register as register_pipeline
    register_pipeline(app, db, render, lambda: Page(db), templates)
    from .review import register as register_review
    register_review(app, db, render, lambda: Page(db), templates)
    from .graph import register as register_graph
    register_graph(app, db, render, lambda: Page(db), templates)
    from .measures import register as register_measures
    register_measures(app, db, render, lambda: Page(db), templates)
    from .atelier import register as register_atelier
    register_atelier(app, db, render, lambda: Page(db), templates)
    from . import help as aide
    aide.install(env)
    aide.register(app, db, render, lambda: Page(db))
    from worldkit.ingest.stages import STAGE_NAMES
    env.globals["names"] = STAGE_NAMES
    return app


def _lineage(result: Result) -> str:
    """Lignée des branches en Mermaid : mise en forme des données du service (présentation)."""
    if not result.ok:
        return ""
    lines = ["flowchart LR"]
    for b in result.output["branches"]:
        node = b["id"].replace("-", "_")
        label = f"{b['id']}<br/>tête {b['head']}" + (" · référence" if b["reference"] else "") + \
            (f" · {b['status']}" if b["status"] != "active" else "")
        lines.append(f'  {node}["{label}"]')
        if b["parent"]:
            lines.append(f'  {b["parent"].replace("-", "_")} -->|"rang {b["fork_seq"]}"| {node}')
        if b["status"] != "active":
            lines.append(f"  style {node} stroke-dasharray: 5 5,color:#777")
        if b["reference"]:
            lines.append(f"  style {node} stroke-width:3px")
    return "\n".join(lines)
