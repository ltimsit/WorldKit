"""Rendu Markdown des pages (M10) et export JSON pour un LLM (M11, R-LLM-01).

Identifiants affichés tels quels : les libellés (`labels`) restent préparés (R-SCH-08).
Le wiki d'auteur montre notoriété et provenance de chaque fait (R-FAI-01, R-IDT-05).
"""

from __future__ import annotations

import json
from typing import Any

from worldkit.core.projection.state import State

from .model import AttributeLine, EntityPage, Filter, View, entity_visible, fact_visible

NON_PUBLIC = "(entité non publique)"


def _meta(flt: Filter, visibility: object, provenance: str, member: str | None = None, page: str = "") -> str:
    if flt is Filter.PLAYER:
        return ""
    via = f", via {member}" if member and member != page else ""
    return f"  _[{visibility} · {provenance}{via}]_"


def _name(view: View, entity: str) -> str:
    title = view.title(entity)
    return f"{title} (`{entity}`)" if title != entity else f"`{entity}`"


def render_page(page: EntityPage, view: View) -> str:
    flt = view.filter
    status = " — close" if page.closed else ""
    out = [f"# {page.title}", "", f"`{page.id}` · {page.type}{status}"]
    if flt is Filter.AUTHOR:
        out[-1] += f" · {page.visibility}"
    if len(page.members) > 1:
        out += ["", "Page consolidée : " + ", ".join(f"`{m}`" for m in page.members)]

    out += ["", "## Attributs"]
    grouped: dict[tuple[str, str], list[AttributeLine]] = {}
    for a in page.attributes:
        grouped.setdefault((a.entity, a.name), []).append(a)
    for (entity, name), lines in grouped.items():
        for a in lines:
            later = " — redéfini plus tard" if a.redefined_later else ""
            out.append(f"- {name} : {a.value}{later}{_meta(flt, a.visibility, a.provenance, entity, page.id)}")
    if not page.attributes:
        out.append("- (aucun)")

    out += ["", "## Relations"]
    for r in page.relations:
        other = _name(view, r.other) if r.other else NON_PUBLIC
        text = f"- {r.relation} → {other}" if r.direction == "out" else f"- {other} {r.relation} → (cette entité)"
        later = " — redéfini plus tard" if r.redefined_later else ""
        out.append(text + later + _meta(flt, r.visibility, r.provenance, r.entity, page.id))
    if not page.relations:
        out.append("- (aucune)")

    if page.identities:
        out += ["", "## Identité"]
        for i in page.identities:
            out.append(f"- même que `{i.other}` ({i.kind})" + _meta(flt, i.visibility, i.provenance))

    if page.claims:
        out += ["", "## Affirmations"]
        labels = {"true": "vraie", "false": "fausse", "undetermined": "non établie"}
        for c in page.claims:
            verdict = f" — qualifiée {labels.get(c.qualification, c.qualification)}" if c.qualification else ""
            meta = _meta(flt, f"{c.visibility} ; qualification {c.qualification_visibility}"
                         if c.qualification else c.visibility, c.provenance)
            out.append(f"- « {c.text} »{verdict}{meta}")

    out += ["", "## Fiches"]
    for sh in page.sheets:
        values = ", ".join(f"{a.name} {a.value}" for a in sh.attributes) or "vide"
        out.append(f"- {sh.system} ({sh.category}) : {values}")
    if not page.sheets:
        out.append("- (aucune)")
    out += ["", "## Pistes ouvertes"]
    out += [f"- {d}" for d in page.drafts] or ["- (aucune)"]
    out += ["", "## Documents sources"]
    out += [f"- {d}" for d in page.documents] or ["- (aucun)"]
    out.append("")
    return "\n".join(out)


def export_graph(state: State, flt: Filter) -> dict[str, Any]:
    """Graphe filtré pour un LLM : entités et faits visibles dans la vue, rien d'autre (R-LLM-01, R-NOT-03)."""
    view = View(state, flt)
    duplicates = view._duplicates()
    entities = []
    for eid in view.entity_ids():
        members = set(duplicates.get(eid, [eid]))
        attrs: dict[str, Any] = {}
        for f in sorted(state.facts.values(), key=lambda f: repr(f.id)):
            if f.subject in members and f.kind != "rel" and fact_visible(f, state, flt):
                if f.kind == "value":
                    attrs.setdefault(f.name, []).append(f.value)
                else:
                    attrs[f.name] = f.value
        rec = state.entities[eid]
        entities.append({"id": eid, "type": rec.type, "closed": rec.closed, "attributes": attrs})
    relations = []
    for f in sorted(state.facts.values(), key=lambda f: repr(f.id)):
        if f.kind == "rel" and f.name != "same_as" and fact_visible(f, state, flt):
            src, dst = view.display(f.subject), view.display(f.target or "")
            relations.append({"from": src, "relation": f.name, "to": dst})
    sheets = []  # fiches ouvertes et visibles, avec leur rattachement (L2)
    for sid, rec in sorted(state.entities.items()):
        b = rec.sheet
        if b is None or rec.closed or not entity_visible(state, sid, flt) or b.of not in view.entity_ids():
            continue
        values: dict[str, Any] = {}
        for f in sorted(state.facts_of(sid), key=lambda f: repr(f.id)):
            if f.kind == "value" and fact_visible(f, state, flt):
                values.setdefault(f.name, []).append(f.value)
            elif f.kind == "attr" and fact_visible(f, state, flt):
                values[f.name] = f.value
        # `of` porte has_sheet, `system` et `category` portent conforms_to : calculées, elles restent hors
        # de `relations`, qui ne contient que des faits.
        sheets.append({"id": sid, "of": view.display(b.of), "system": b.system, "category": b.category,
                       "attributes": values})
    identities = [{"a": f.subject, "b": f.target, "kind": f.same_as_kind}
                  for f in sorted(state.facts.values(), key=lambda f: repr(f.id))
                  if f.name == "same_as" and fact_visible(f, state, flt)]
    claims = []
    for eid in view.entity_ids():
        for c in view.claims_of({eid}):
            claims.append({"speaker": eid, "text": c.text, "qualification": c.qualification})
    return {"branch": state.branch, "seq": state.seq, "filter": str(flt),
            "entities": entities, "relations": relations, "sheets": sheets, "identities": identities,
            "claims": claims}


def export_json(state: State, flt: Filter) -> str:
    return json.dumps(export_graph(state, flt), ensure_ascii=False, indent=2, sort_keys=True)
