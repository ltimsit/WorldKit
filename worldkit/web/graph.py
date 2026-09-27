"""Écran Graphe (cadre d'interface I-VUE-06, I-GRA-01 ; décisions I6).

Le service (`graph.view`, `graph.compare`) donne nœuds, arêtes, couches et marques d'état ; la page ne fait
que les disposer avec Cytoscape.js (copié dans le projet) et montrer le détail d'un nœud au clic (I-PRI-02).
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse

from worldkit.service.graph import LAYERS


def register(app: FastAPI, db: Path, render: Callable[..., HTMLResponse], page_factory: Callable[[], Any],
             templates: Any) -> None:

    @app.get("/graph", response_class=HTMLResponse)
    def graph(request: Request) -> HTMLResponse:
        page = page_factory()
        q = request.query_params
        target = q.get("target") or None
        layers = q.getlist("layer") or ["world"]
        entity = q.get("entity", "aldren-ii") if not q.get("full") else None
        depth = int(q.get("depth") or 1)
        flt = q.get("filter") or "author"
        compare = bool(q.get("compare"))
        if compare:
            left = {k: q.get(k) for k in ("target", "branch", "point") if q.get(k)}
            right = {k: q.get(f"cmp.{k}") for k in ("target", "branch", "point") if q.get(f"cmp.{k}")}
            result = page.call("graph.compare", {"entity": entity, "depth": depth, "layers": layers, "filter": flt,
                                                 "left": left, "right": right}, None)
        else:
            params: dict[str, Any] = {"depth": depth, "layers": layers, "filter": flt,
                                      **{k: q.get(k) for k in ("branch", "point") if q.get(k)}}
            if entity:
                params["entity"] = entity
            result = page.call("graph.view", params, target)
        index = page.call("wiki.index", {}, target)
        elements = []
        if result.ok and result.output:
            for n in result.output["nodes"]:
                classes = [f"layer-{n['layer']}", f"vis-{n.get('visibility')}"]
                if n.get("closed"):
                    classes.append("closed")
                if n.get("status"):
                    classes.append(f"status-{n['status']}")
                if n["id"] == result.output.get("center"):
                    classes.append("center")
                elements.append({"data": n, "classes": " ".join(classes)})
            for e in result.output["edges"]:
                classes = [f"vis-{e.get('visibility')}", *[f"mark-{m}" for m in e.get("marks", [])]]
                if e.get("computed"):
                    classes.append("computed")
                if e.get("status"):
                    classes.append(f"status-{e['status']}")
                elements.append({"data": {**e, "label": e["relation"]}, "classes": " ".join(classes)})
        safe_json = json.dumps(elements, ensure_ascii=False).replace("</", r"<\/")  # pas de </script> dans une donnée
        return render(request, "graph.html", page, result=result, elements=safe_json,
                      layers=LAYERS, chosen=layers, entity=entity or "", depth=depth, full=bool(q.get("full")),
                      compare=compare, cmp={k: q.get(f"cmp.{k}", "") for k in ("target", "branch", "point")},
                      entities=(index.output or {}).get("pages", []))
