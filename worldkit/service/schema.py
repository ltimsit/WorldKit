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
from .registry import Output, Params, operation
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


# ---------------------------------------------------------------------------
# Ajouter une relation au schéma (chantier §6.6, I-ATL-09) : depuis un fait de l'atelier ou un changement hors
# schéma de la revue. Écrit dans le monde, après confirmation (une édition appliquée ne se retire jamais, R-CYC-01).
# ---------------------------------------------------------------------------

class AddRelationParams(Params):
    relation: str = Field("", description="identifiant de la relation, en anglais (R-SCH-07) : hates, runs…")
    from_: list[str] = Field(default_factory=list, alias="from",
                             description="types de la source ; défaut : le type de `subject`")
    to: list[str] = Field(default_factory=list, description="types de la cible ; défaut : le type de `object`")
    cardinality: str = Field("many_to_many", description="many_to_many, many_to_one, one_to_many, one_to_one")
    symmetric: bool = False
    label: str | None = Field(None, description="libellé français (R-SCH-08) : « déteste »")
    subject: str | None = Field(None, description="entité source du fait (pour en déduire le type)")
    object: str | None = Field(None, description="entité cible du fait")
    doc_id: str | None = Field(None, description="atelier : source du fait à rattacher")
    ann_id: int | None = Field(None, description="atelier : fait à rattacher à la nouvelle relation")
    branch: str | None = None
    confirm: bool = Field(False, description="écrire l'édition (sinon : aperçu, rien n'est écrit)")


def _entity_type(world: Any, branch: str, entity: str | None, doc_id: str | None) -> str | None:
    """Type d'une entité : de l'état, ou entité nouvelle confirmée dans une source de l'atelier."""
    if not entity:
        return None
    state = world.state(branch)
    if entity in state.entities:
        return state.entities[entity].type
    if doc_id:
        from worldkit.atelier import layers, store
        confirmed, _ = layers.confirmed_entities(world, branch, store.source(world, doc_id))
        return next((e.type for e in confirmed if e.id == entity), None)
    return None


def _edit_id(world: Any, relation: str) -> str:
    base, n = f"schema-{relation}", 2
    edit_id = base
    while world.store.has_edit(edit_id):
        edit_id, n = f"{base}-{n}", n + 1
    return edit_id


@operation("schema.add_relation", "write", AddRelationParams,
           "ajouter une relation au schéma du monde (aperçu, puis confirmation) et y rattacher un fait de l'atelier",
           ("R-SCH-03", "R-SCH-06", "R-CYC-01", "I-ATL-09"))
def schema_add_relation(ctx: Context, p: AddRelationParams) -> Output:
    from worldkit.core.conflicts import check_application
    from worldkit.core.journal.models import Edit, Origin
    from worldkit.core.schema import Issue, IssueCode, Severity
    from worldkit.core.schema.changes import SchemaSetRelation
    from worldkit.core.schema.metaschema import RelationDef
    w = ctx.world
    assert w is not None
    branch = p.branch or w.reference_branch
    state = w.state(branch)
    origin_types = [t for t in (_entity_type(w, branch, p.subject, p.doc_id),) if t]
    target_types = [t for t in (_entity_type(w, branch, p.object, p.doc_id),) if t]
    sources, targets = p.from_ or origin_types, p.to or target_types
    if not p.relation.strip():
        return Output({"relation": "", "from": sources, "to": targets, "label": p.label or "",
                       "cardinality": p.cardinality, "symmetric": p.symmetric},
                      [Issue(IssueCode.EDIT_RULE, "donner un nom à la relation (en anglais : hates, runs…)",
                             "R-SCH-07", Severity.WARNING)], status="pending")
    if p.relation in state.world.relations:
        r = state.world.relations[p.relation]
        return Output(None, [Issue(IssueCode.EDIT_RULE, f"la relation « {p.relation} » existe déjà "
                                   f"({_fr(r.labels, p.relation)} : {', '.join(r.from_)} → {', '.join(r.to)}) : "
                                   "corriger le fait vers elle", "R-SCH-03")])
    try:
        definition = RelationDef.model_validate({"from": sources, "to": targets, "cardinality": p.cardinality,
                                                 "symmetric": p.symmetric,
                                                 "labels": {"fr": p.label} if p.label else {}})
        change = SchemaSetRelation(op="schema_set_relation", relation=p.relation, definition=definition)
    except ValueError as e:
        return Output(None, [Issue(IssueCode.EDIT_RULE, f"relation invalide : {e}", "R-SCH-01")])
    edit = Edit(id=_edit_id(w, p.relation), branch=branch, origin=Origin.ENRICHMENT, tags=["schema"],
                note="ajoutée depuis l'atelier ou la revue (chantier §6.6)", changes=[change])
    summary = {"edit": edit.id, "relation": p.relation, "label": p.label or p.relation, "from": sources,
               "to": targets, "cardinality": p.cardinality, "symmetric": p.symmetric,
               "attach": {"doc_id": p.doc_id, "ann_id": p.ann_id} if p.ann_id else None}
    app = check_application(edit.changes, state, edit.id)
    if not app.applicable:
        return Output(summary, app.issues)
    if not p.confirm:
        return Output(summary, [Issue(IssueCode.EDIT_RULE, f"écrira l'édition {edit.id} au journal de {branch} "
                                      "(elle ne se retire pas ; une autre édition peut la défaire) : confirmer",
                                      "R-CYC-01", Severity.WARNING)], status="pending")
    outcome = w.apply(edit)
    if not outcome.ok:
        return Output(summary, outcome.issues)
    summary["seq"] = outcome.seq
    if p.doc_id and p.ann_id:
        from worldkit.atelier import gestures, layers, store
        fact = next((a for a in layers.effective(w, branch, store.source(w, p.doc_id))
                     if a.ann_id == p.ann_id and a.kind == "fact"), None)
        if fact is not None and fact.value["draft"].get("op") == "add_relation":
            draft = {**fact.value["draft"], "relation": p.relation}
            try:
                summary["attached"] = gestures.fact_gesture(w, branch, p.doc_id, "correct", p.ann_id, draft=draft)
            except ValueError as e:  # types restreints par l'auteur : la relation est ajoutée, le fait reste à corriger
                return Output(summary, [Issue(IssueCode.EDIT_RULE, f"relation ajoutée, fait non rattaché : {e}",
                                              "I-ATL-09", Severity.WARNING)])
    return Output(summary, [], {"relations": len(w.state(branch).world.relations)})


# ---------------------------------------------------------------------------
# Exporter le schéma projeté (I-VUE-12) : pour reporter dans le fichier d'un monde d'auteur ce qui a été ajouté en
# session (`worldkit schema export --out mondes/corbelle/schema.yaml`).
# ---------------------------------------------------------------------------

def schema_yaml(schema: Any, header: list[str]) -> str:
    """Le schéma au format des fichiers du projet : types en blocs, une relation par ligne ; valeurs par défaut
    omises. Relu par le même validateur (R-SCH-02)."""
    import yaml
    data = schema.model_dump(mode="json", by_alias=True, exclude_defaults=True)
    head = {k: data[k] for k in ("schema", "kind", "copied_from", "version") if k in data}
    if "version" not in head:
        head["version"] = schema.version
    out = [f"# {line}" for line in header] + [yaml.safe_dump(head, allow_unicode=True, sort_keys=False).rstrip(), ""]
    def flow(value: Any) -> str:
        text = yaml.safe_dump(value, allow_unicode=True, sort_keys=False, default_flow_style=True, width=10_000).strip()
        return text.removesuffix("...").strip()  # une valeur simple sort avec une marque de fin de document

    out.append("types:" if data.get("types") else "types: {}")
    for name, t in data.get("types", {}).items():
        out.append(f"  {name}:")
        for key in ("extends", "labels"):
            if key in t:
                out.append(f"    {key}: {flow(t[key])}")
        attributes = t.get("attributes", {})
        if attributes:
            out.append("    attributes:")
            width = max(len(a) for a in attributes) + 1
            out += [f"      {(a + ':').ljust(width)} {flow(d)}" for a, d in attributes.items()]
    out += ["", "relations:" if data.get("relations") else "relations: {}"]
    width = max((len(r) for r in data.get("relations", {})), default=0) + 1
    for name, d in data.get("relations", {}).items():
        out.append(f"  {(name + ':').ljust(width)} {flow(d)}")
    return "\n".join(out) + "\n"


class ExportParams(Where):
    scope: str | None = Field(None, description="world (défaut) ou l'identifiant d'un système de règles")


@operation("schema.export", "read", ExportParams,
           "schéma projeté d'un état, au format YAML d'un fichier de schéma (pour le reporter dans un monde d'auteur)",
           ("R-SCH-02", "R-SCH-03"))
def schema_export(ctx: Context, p: ExportParams) -> Output:
    from datetime import date
    from worldkit.core.schema import Issue, IssueCode
    from worldkit.core.schema.changes import WORLD_SCOPE
    w = ctx.world
    assert w is not None
    branch = p.branch or w.reference_branch
    state = w.state(branch, p.point)
    scope = p.scope or WORLD_SCOPE
    schemas = {WORLD_SCOPE: state.world, **state.systems}
    if scope not in schemas:
        return Output(None, [Issue(IssueCode.EDIT_RULE, f"portée inconnue : {scope}", "R-SCH-01")])
    added = sorted({e for k, e in provenance(w, branch, state.seq).items() if k[0] == scope and e != "e000"})
    header = [f"Schéma {schemas[scope].id} exporté du monde {w.decl.world} ({branch}, rang {state.seq}) le "
              f"{date.today().isoformat()} par « worldkit schema export ».",
              "Éditions de schéma depuis le départ : " + (", ".join(added) if added else "aucune") + ".",
              "Identifiants en anglais (R-SCH-07), libellés français via labels (R-SCH-08)."]
    text = schema_yaml(schemas[scope], header)
    return Output({"scope": scope, "yaml": text, "edits": added}, [],
                  {"types": len(schemas[scope].types), "relations": len(schemas[scope].relations)})
