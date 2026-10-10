"""Graphe d'un état (cadre d'interface I-GRA-01 ; décisions I6).

Les **entités** sont des nœuds, les **relations** des arêtes ; les attributs, fiches et affirmations d'un nœud
vont dans son détail (panneau), pas sur le dessin (décision I6). Le service calcule tout ce qui relève du
domaine — ce qui est visible selon le filtre (R-NOT-03, R-NOT-04), les marques d'état (secret, masqué,
redéfini plus tard, orphelin, clos), les couches — ; l'interface ne fait que disposer (I-PRI-02).

Couches : `world` (entités du monde et leurs relations), `system` (éléments de système, contreparties),
`sheet` (fiches, `has_sheet` et `conforms_to` calculées), `identity` (`same_as`), `claim` (affirmations et
leur énonciateur), `document` (documents sources).
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field

from worldkit.core.schema import Visibility

from .registry import Output, Params, operation
from .session import Context, parse_target

LAYERS = ["world", "system", "sheet", "identity", "claim", "document"]
Layer = Literal["world", "system", "sheet", "identity", "claim", "document"]


def _label(state: Any, eid: str) -> str:
    f = state.facts.get(("attr", eid, "name"))
    return str(f.value) if f is not None else eid


def build(world: Any, branch: str | None, point: Any, flt_name: str, layers: list[str]) -> dict[str, Any]:
    """Le graphe complet d'un état, dans les couches demandées."""
    from worldkit.core.views.model import (Filter, attribute_label, effective_visibility, entity_visibility,
                                           entity_visible, fact_visible, relation_label, type_label)
    from worldkit.ingest.review import orphan_fact_ids, sources
    flt = Filter(flt_name)
    branch = branch or world.reference_branch
    state = world.state(branch, point)
    redefined = world.redefined_after(branch, state.seq)
    at_head = state.seq == world.store.head_seq(branch)
    orphans = {tuple(f) for f in orphan_fact_ids(world, branch)} if at_head else set()
    keys_of: dict[Any, list[Any]] = {}
    for k, fid in state.occupancy.items():
        keys_of.setdefault(fid, []).append(k)

    def marks(f: Any) -> list[str]:
        out = []
        if f.visibility is Visibility.PUBLIC and not f.propagation_lifted \
                and effective_visibility(f, state) is not Visibility.PUBLIC:
            out.append("masked")          # R-NOT-07
        if any(k in redefined for k in keys_of.get(f.id, [])):
            out.append("redefined_later")  # R-VUE-03
        if f.id in orphans:
            out.append("orphan")          # R-FAI-06
        return out

    nodes: dict[str, dict[str, Any]] = {}
    edges: dict[str, dict[str, Any]] = {}

    def layer_of(rec: Any) -> str:
        return "sheet" if rec.sheet is not None else "system" if rec.scope != "world" else "world"

    for eid, rec in sorted(state.entities.items()):
        layer = layer_of(rec)
        if layer not in layers or not entity_visible(state, eid, flt):
            continue
        attributes = [{"name": f.name, "label": attribute_label(state, eid, f.name), "value": f.value,
                       "visibility": str(f.visibility),
                       "effective": str(effective_visibility(f, state)), "provenance": f.established_by,
                       "marks": marks(f), "fact": list(f.id)}
                      for f in sorted(state.facts_of(eid), key=lambda f: repr(f.id))
                      if f.kind != "rel" and fact_visible(f, state, flt)]
        node = {"id": eid, "label": _label(state, eid), "type": rec.type, "type_label": type_label(state, eid),
                "layer": layer,
                "visibility": str(entity_visibility(state, eid)), "closed": rec.closed, "attributes": attributes,
                "provenance": rec.established_by}
        if rec.sheet is not None:
            node["sheet"] = {"of": rec.sheet.of, "system": rec.sheet.system, "category": rec.sheet.category}
            node["label"] = f"{rec.sheet.system} : {rec.sheet.category}"
        nodes[eid] = node

    for f in sorted(state.facts.values(), key=lambda f: repr(f.id)):
        if f.kind != "rel" or f.target is None or not fact_visible(f, state, flt):
            continue
        layer = "identity" if f.name == "same_as" else "system" if f.name == "counterpart_of" else "world"
        if layer not in layers or f.subject not in nodes or f.target not in nodes:
            continue
        eid = "|".join(map(str, f.id))
        edges[eid] = {"id": eid, "source": f.subject, "target": f.target, "relation": f.name,
                      "relation_label": relation_label(state, f.name, f.scope),
                      "visibility": str(f.visibility), "effective": str(effective_visibility(f, state)),
                      "provenance": f.established_by, "marks": marks(f), "layer": layer, "fact": list(f.id),
                      **({"kind": f.same_as_kind} if f.same_as_kind else {})}

    if "sheet" in layers:  # has_sheet et conforms_to, calculées (R-MET-02)
        for sid, node in list(nodes.items()):
            sheet = node.get("sheet")
            if not sheet:
                continue
            if sheet["of"] in nodes:
                edges[f"has_sheet|{sid}"] = {"id": f"has_sheet|{sid}", "source": sheet["of"], "target": sid,
                                             "relation": "has_sheet", "layer": "sheet", "computed": True,
                                             "visibility": node["visibility"], "marks": []}
            cat = f"{sheet['system']}:{sheet['category']}"
            nodes.setdefault(cat, {"id": cat, "label": cat, "type": "Catégorie", "layer": "sheet",
                                   "visibility": "public", "closed": False, "attributes": [], "computed": True})
            edges[f"conforms_to|{sid}"] = {"id": f"conforms_to|{sid}", "source": sid, "target": cat,
                                           "relation": "conforms_to", "layer": "sheet", "computed": True,
                                           "visibility": "public", "marks": []}

    if "claim" in layers:  # affirmations et leur énonciateur (R-DOC-06)
        for cid, c in sorted(state.claims.items()):
            vis = c.get("visibility") or "unqualified"
            speaker = c.get("speaker")
            if flt is Filter.PLAYER and (vis != "public" or speaker not in nodes):
                continue
            q = state.qualifications.get(cid)
            qual = q["value"] if q and (flt is Filter.AUTHOR or (q.get("visibility") == "public")) else None
            nodes[f"claim:{cid}"] = {"id": f"claim:{cid}", "label": f"« {str(c.get('text', ''))[:40]} »",
                                     "type": "Affirmation", "layer": "claim", "visibility": vis, "closed": False,
                                     "attributes": [{"name": "texte", "value": c.get("text"), "visibility": vis},
                                                    {"name": "qualification", "value": qual}],
                                     "provenance": c.get("established_by")}
            if speaker in nodes:
                edges[f"asserts|{cid}"] = {"id": f"asserts|{cid}", "source": speaker, "target": f"claim:{cid}",
                                           "relation": "asserts", "layer": "claim", "visibility": vis, "marks": []}

    if "document" in layers:  # documents sources (R-VUE-02), avec leur notoriété déclarée
        for eid, docs in sorted(sources(world, branch).items()):
            if eid not in nodes:
                continue
            for doc, vis in docs:
                if flt is Filter.PLAYER and vis is not Visibility.PUBLIC:
                    continue
                nodes.setdefault(f"doc:{doc}", {"id": f"doc:{doc}", "label": doc, "type": "Document",
                                                "layer": "document", "visibility": str(vis), "closed": False,
                                                "attributes": []})
                edges[f"source|{doc}|{eid}"] = {"id": f"source|{doc}|{eid}", "source": f"doc:{doc}", "target": eid,
                                                "relation": "source", "layer": "document", "visibility": str(vis),
                                                "marks": []}
    return {"branch": branch, "seq": state.seq, "filter": flt_name, "nodes": nodes, "edges": edges}


def neighborhood(graph: dict[str, Any], center: str, depth: int) -> dict[str, Any]:
    """Voisinage d'un nœud à `depth` pas, dans les deux sens (I-GRA-01)."""
    if center not in graph["nodes"]:
        return {**graph, "nodes": {}, "edges": {}}
    keep = {center}
    frontier = {center}
    for _ in range(depth):
        nxt = set()
        for e in graph["edges"].values():
            if e["source"] in frontier and e["target"] not in keep:
                nxt.add(e["target"])
            if e["target"] in frontier and e["source"] not in keep:
                nxt.add(e["source"])
        keep |= nxt
        frontier = nxt
    return {**graph, "nodes": {k: v for k, v in graph["nodes"].items() if k in keep},
            "edges": {k: v for k, v in graph["edges"].items() if v["source"] in keep and v["target"] in keep}}


class GraphParams(Params):
    entity: str | None = Field(None, description="entité centrale (voisinage) ; sans elle, le graphe complet")
    depth: int = Field(1, ge=0, le=6)
    layers: list[Layer] = Field(default_factory=lambda: ["world"])
    filter: Literal["author", "player"] = "author"
    branch: str | None = None
    point: str | int | None = None


def _shape(graph: dict[str, Any]) -> dict[str, Any]:
    return {**graph, "nodes": sorted(graph["nodes"].values(), key=lambda n: n["id"]),
            "edges": sorted(graph["edges"].values(), key=lambda e: e["id"])}


@operation("graph.view", "read", GraphParams,
           "graphe d'un état : voisinage ou complet, couches, marques d'état, filtre auteur ou joueur",
           ("R-NOT-03", "R-NOT-04", "R-NOT-07", "R-VUE-03", "R-FAI-06", "I-GRA-01"),
           example={"entity": "aldren-ii", "depth": 1, "layers": ["world", "claim"]})
def graph_view(ctx: Context, p: GraphParams) -> Output:
    assert ctx.world is not None
    g = build(ctx.world, p.branch, p.point, p.filter, list(p.layers))
    total = (len(g["nodes"]), len(g["edges"]))
    if p.entity:
        g = neighborhood(g, p.entity, p.depth)
    g = _shape(g)
    return Output({**g, "center": p.entity, "depth": p.depth, "layers": list(p.layers)}, [],
                  {"nodes": len(g["nodes"]), "edges": len(g["edges"]), "nodes_total": total[0],
                   "edges_total": total[1]})


class GraphSide(Params):
    target: str | int | None = None
    branch: str | None = None
    point: str | int | None = None


class GraphCompareParams(Params):
    entity: str | None = None
    depth: int = Field(1, ge=0, le=6)
    layers: list[Layer] = Field(default_factory=lambda: ["world"])
    filter: Literal["author", "player"] = "author"
    left: GraphSide = Field(default_factory=GraphSide)
    right: GraphSide = Field(default_factory=GraphSide)


def _signature(x: dict[str, Any]) -> Any:
    return (x.get("visibility"), x.get("closed"), x.get("label"),
            sorted((a["name"], str(a.get("value")), a.get("visibility")) for a in x.get("attributes", [])))


@operation("graph.compare", "read", GraphCompareParams,
           "deux états sur un même dessin : nœuds et arêtes ajoutés, retirés, changés", ("I-GRA-01", "R-VUE-03"),
           needs_world=False,
           example={"entity": "aldren-ii", "left": {"branch": "reference"}, "right": {"branch": "reference-r1"}})
def graph_compare(ctx: Context, p: GraphCompareParams) -> Output:
    graphs = []
    for side in (p.left, p.right):
        world = ctx.session.open(parse_target(side.target))
        try:
            graphs.append(build(world, side.branch, side.point, p.filter, list(p.layers)))
        finally:
            world.close()
    left, right = graphs
    nodes, edges = {}, {}
    for kind, a, b, out in (("node", left["nodes"], right["nodes"], nodes), ("edge", left["edges"], right["edges"], edges)):
        for key in sorted(set(a) | set(b)):
            if key not in b:
                out[key] = {**a[key], "status": "removed"}
            elif key not in a:
                out[key] = {**b[key], "status": "added"}
            elif _signature(a[key]) != _signature(b[key]):
                before = {x["name"]: x.get("value") for x in a[key].get("attributes", [])}
                changed = [{"name": x["name"], "before": before.get(x["name"]), "after": x.get("value")}
                           for x in b[key].get("attributes", []) if before.get(x["name"]) != x.get("value")]
                out[key] = {**b[key], "status": "changed", "before": {"visibility": a[key].get("visibility"),
                                                                      "closed": a[key].get("closed")},
                            "changed_attributes": changed}
            else:
                out[key] = {**b[key], "status": "same"}
    union = {"nodes": nodes, "edges": edges}
    if p.entity:
        union = neighborhood(union, p.entity, p.depth)
    g = _shape(union)
    counts = {s: sum(1 for x in [*g["nodes"], *g["edges"]] if x["status"] == s) for s in ("added", "removed", "changed")}
    return Output({**g, "left": {"branch": left["branch"], "seq": left["seq"]},
                   "right": {"branch": right["branch"], "seq": right["seq"]}, "center": p.entity}, [], counts)
