"""Schéma d'un état (écran « Schéma », I-VUE-12) : ce que le monde accepte, à une branche et un point.

Le schéma est versionné dans le journal (R-SCH-03) : celui d'un état est sa projection, pas l'édition `e000` seule.
Rien n'est recalculé du domaine (I-PRI-02) : le service met en forme le schéma projeté, compte l'usage dans l'état
(entités par type, faits par relation) et retrouve la **provenance** de chaque définition en relisant le journal de
la lignée jusqu'au point (dernière édition qui l'a posée). Les libellés français (`labels`) sont montrés à côté des
identifiants (R-SCH-08, R-SCH-09).
"""

from __future__ import annotations

import re
from typing import Any

from pydantic import Field

from .ops import Where
from .registry import Output, operation
from .session import Context


def _fr(labels: dict[str, str] | None, default: str) -> str:
    return (labels or {}).get("fr", default)


def provenance(world: Any, branch: str, seq: int) -> dict[tuple[str, ...], str]:
    """(portée, « type » | « relation », nom[, attribut]) → dernière édition qui a posé cette définition."""
    from worldkit.core.schema.changes import (SchemaRemoveRelation, SchemaRemoveType, SchemaSetRelation,
                                              SchemaSetType)
    out: dict[tuple[str, ...], str] = {}
    for _, edit_id in world.store.journal_ids(branch, upto=seq):
        for c in world.store.edit(edit_id).edit.changes:
            match c:
                case SchemaSetType(attribute=None):
                    out[(c.scope, "type", c.type)] = edit_id
                    for attr in getattr(c.definition, "attributes", {}) or {}:
                        out[(c.scope, "type", c.type, attr)] = edit_id
                case SchemaSetType():
                    out[(c.scope, "type", c.type, c.attribute)] = edit_id
                case SchemaRemoveType():
                    out = {k: v for k, v in out.items() if k[:3] != (c.scope, "type", c.type)}
                case SchemaSetRelation():
                    out[(c.scope, "relation", c.relation)] = edit_id
                case SchemaRemoveRelation():
                    out.pop((c.scope, "relation", c.relation), None)
    return out


def _attribute(name: str, d: Any, owner: str, origin: str | None) -> dict[str, Any]:
    return {"name": name, "label": _fr(d.labels, name), "type": str(d.type), "required": d.required,
            "min": d.min, "max": d.max, "owner": owner, "provenance": origin}


def describe_schema(schema: Any, scope: str, prov: dict[tuple[str, ...], str], state: Any) -> dict[str, Any]:
    """Types (héritage, attributs propres et hérités, sous-types, entités de l'état ; pour un système, ses éléments et
    les fiches de chaque catégorie) et relations (de → vers, cardinalité, symétrie, faits de l'état), triés par nom."""
    entities: dict[str, int] = {}
    for rec in state.entities.values():
        if rec.closed:
            continue
        if rec.sheet is not None:  # une fiche compte dans la catégorie de son système (R-MET-06)
            if rec.sheet.system == scope:
                entities[rec.sheet.category] = entities.get(rec.sheet.category, 0) + 1
        elif rec.scope == scope:
            entities[rec.type] = entities.get(rec.type, 0) + 1
    facts: dict[str, int] = {}
    for f in state.facts.values():
        if f.kind == "rel" and f.scope == scope:
            facts[f.name] = facts.get(f.name, 0) + 1
    types = []
    for name in sorted(schema.types):
        t = schema.types[name]
        own = [_attribute(a, d, name, prov.get((scope, "type", name, a))) for a, d in sorted(t.attributes.items())]
        inherited = [_attribute(a, d, owner, prov.get((scope, "type", owner, a)))
                     for owner in schema.ancestors(name)[1:] for a, d in sorted(schema.types[owner].attributes.items())
                     if a not in t.attributes]
        types.append({"name": name, "label": _fr(t.labels, name), "extends": t.extends,
                      "ancestors": schema.ancestors(name)[1:],
                      "subtypes": sorted(n for n, d in schema.types.items() if d.extends == name),
                      "attributes": own, "inherited": inherited, "entities": entities.get(name, 0),
                      "provenance": prov.get((scope, "type", name))})
    relations = [{"name": r, "label": _fr(d.labels, r), "from": list(d.from_), "to": list(d.to),
                  "cardinality": str(d.cardinality), "symmetric": d.symmetric, "facts": facts.get(r, 0),
                  "provenance": prov.get((scope, "relation", r))} for r, d in sorted(schema.relations.items())]
    return {"id": schema.id, "kind": str(schema.kind), "version": schema.version, "types": types,
            "relations": relations}


def _node(name: str) -> str:
    return re.sub(r"\W", "_", name)


def mermaid(described: dict[str, Any]) -> str:
    """Diagramme des types et des relations (flowchart) : flèche pleine pour une relation, pointillée pour
    « hérite de »."""
    lines = ["flowchart LR"]
    for t in described["types"]:
        label = t["label"] if t["label"] == t["name"] else f"{t['label']} · {t['name']}"
        lines.append(f'  {_node(t["name"])}["{label}"]')
    for t in described["types"]:
        if t["extends"]:
            lines.append(f'  {_node(t["name"])} -.->|hérite de| {_node(t["extends"])}')
    for r in described["relations"]:
        arrow = "<-->" if r["symmetric"] else "-->"
        for a in r["from"]:
            for b in r["to"]:
                lines.append(f'  {_node(a)} {arrow}|{r["label"].replace("|", "/")}| {_node(b)}')
    return "\n".join(lines)


class SchemaParams(Where):
    scope: str | None = Field(None, description="world (défaut) ou l'identifiant d'un système de règles")


@operation("schema.show", "read", SchemaParams,
           "schéma d'un état : types, attributs, relations (de → vers), systèmes, fiches exigées, provenance",
           ("R-SCH-01", "R-SCH-03", "R-SCH-08", "R-MET-06"))
def schema_show(ctx: Context, p: SchemaParams) -> Output:
    from worldkit.core.schema.changes import WORLD_SCOPE
    from worldkit.core.schema import Issue, IssueCode
    w = ctx.world
    assert w is not None
    branch = p.branch or w.reference_branch
    state = w.state(branch, p.point)
    scope = p.scope or WORLD_SCOPE
    schemas = {WORLD_SCOPE: state.world, **state.systems}
    if scope not in schemas:
        return Output(None, [Issue(IssueCode.EDIT_RULE, f"portée inconnue : {scope} (possibles : "
                                   f"{', '.join(sorted(schemas))})", "R-SCH-01")])
    prov = provenance(w, branch, state.seq)
    described = describe_schema(schemas[scope], scope, prov, state)
    systems = [{"id": sid, "types": len(sch.types), "relations": len(sch.relations)}
               for sid, sch in sorted(state.systems.items())]
    sheets = [{"world_type": wt, "system": sid, "category": cat}  # fiches exigées : système → type du monde → catégorie
              for sid, by_type in sorted(state.sheet_requirements.items()) for wt, cat in sorted(by_type.items())]
    return Output({"branch": state.branch, "seq": state.seq, "schema_rev": state.schema_rev, "scope": scope,
                   "scopes": sorted(schemas), "schema": described, "systems": systems, "sheets": sheets,
                   "mermaid": mermaid(described)}, [],
                  {"types": len(described["types"]), "relations": len(described["relations"]),
                   "systems": len(systems)})
