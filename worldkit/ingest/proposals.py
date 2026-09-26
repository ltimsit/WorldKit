"""M9 (assemblage) : des brouillons extraits aux propositions qualifiées, contre l'état de base du lot.

Fonctions pures : même lot, même état de base → mêmes propositions (T-ARC-01), quel que soit
l'ordre des documents dans le lot (R-PRI-03, T-ING-07).

Qualification de chaque changement (cadre de fondation §5.2, T-ING-03) :

| Étiquette | Condition |
|---|---|
| `support` | même clé, même valeur que la base : enregistré hors journal, aucune question (T-ING-11) |
| `enrichment` | rien ne l'occupe dans la base |
| `anomaly` | la base occupe la clé autrement, document en mode `source` ; ou contradiction interne (R-ING-02) |
| `intention` | idem, document en mode `edit` |
| `internal_contradiction` | un autre passage du même document écrit la même clé autrement (R-ING-02) |
| `batch_conflict` | un autre document du lot écrit la même clé autrement : symétrique (R-PRI-03) |
| `out_of_schema`, `invalid_value` | non représentable (R-SCH-06) |
| `unresolved` | entité citée inconnue |
| `hint_visibility` | notoriété tirée d'un indice : proposition à part (T-ING-15) |
| `optional` | marqué facultatif par l'extracteur |

Une proposition = les changements d'un passage qui portent sur une même entité sujet ; une entité
nouvelle vient avec ses faits initiaux (T-ING-04). Dépendances : une proposition dépend de celle
qui écrit une clé qu'elle lit, dont l'existence d'une entité nouvelle (T-ING-05).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any

from worldkit.core.projection.state import State, relation_fact_id, target_fact_id
from worldkit.core.schema import Change, EntityInfo, FactKey, IssueCode, SchemaContext, fact_keys, qualify
from worldkit.core.schema.changes import (
    AddRelation, AddValue, CloseEntity, CreateEntity, DeleteEntity, RemoveRelation, RemoveValue, SetAttribute,
    SetVisibility, UnsetAttribute,
)
from worldkit.core.schema.check import check_edit, check_fact_change
from worldkit.core.schema.keys import UnknownRelation, target_keys

from .declaration import Mode, normalize

NEW = "new:"


@dataclass(frozen=True)
class Item:
    """Un changement extrait d'un passage, après résolution des entités nouvelles."""

    doc_id: str
    version_fp: str
    passage: int
    order: int                 # position dans le lot : départage déterministe
    change: Change
    mode: Mode
    optional: bool = False


@dataclass
class Qualified:
    item: Item
    keys: list[FactKey]
    value: Any
    tags: set[str] = field(default_factory=set)
    detail: dict[str, Any] = field(default_factory=dict)
    fingerprint: str = ""

    @property
    def is_support(self) -> bool:
        return self.tags == {"support"}


@dataclass
class ProposalDraft:
    id: str
    doc_id: str
    version_fp: str
    passage: int
    subject: str
    kind: str                  # "facts" | "hint"
    items: list[Qualified]
    issues: list[str] = field(default_factory=list)
    reads: set[FactKey] = field(default_factory=set)
    writes: set[FactKey] = field(default_factory=set)
    depends_on: set[str] = field(default_factory=set)


@dataclass(frozen=True)
class NewEntity:
    label: str       # étiquette de l'extracteur, sans « new: »
    id: str          # identifiant attribué dès la proposition (T-ING-05)
    type: str
    name: str | None


# ---------------------------------------------------------------------------
# Résolution des entités nouvelles au niveau du lot (T-ING-07)
# ---------------------------------------------------------------------------

def new_entities(drafts: list[dict[str, Any]], taken: set[str]) -> dict[str, NewEntity]:
    """Regroupe les mentions `new:` de tout le lot : une étiquette = une seule entité nouvelle."""
    types: dict[str, str] = {}
    names: dict[str, str] = {}
    for d in drafts:
        entity = d.get("entity")
        if isinstance(entity, str) and entity.startswith(NEW):
            label = entity[len(NEW):]
            if d.get("op") == "create_entity":
                types.setdefault(label, d["type"])
            elif d.get("op") == "set_attribute" and d.get("attribute") == "name":
                names.setdefault(label, str(d["value"]))
    out: dict[str, NewEntity] = {}
    for label in sorted(types):
        eid, n = label, 2
        while eid in taken:
            eid, n = f"{label}-{n}", n + 1
        taken.add(eid)
        out[label] = NewEntity(label, eid, types[label], names.get(label))
    return out


def resolve(draft: dict[str, Any], new: dict[str, NewEntity]) -> dict[str, Any]:
    def sub(v: Any) -> Any:
        if isinstance(v, str):
            if v.startswith(NEW) and v[len(NEW):] in new:
                return new[v[len(NEW):]].id
            if " " in v:  # désignation textuelle « a relation b » de set_visibility
                return " ".join(sub(t) for t in v.split(" "))
        return v
    return {k: sub(v) for k, v in draft.items()}


# ---------------------------------------------------------------------------
# Empreinte stable (T-ING-08)
# ---------------------------------------------------------------------------

def _norm_value(v: Any) -> Any:
    return normalize(v).casefold() if isinstance(v, str) else v


def change_fingerprint(q: Qualified, new_by_id: dict[str, NewEntity]) -> str:
    """hash(opération, clé canonique, valeur normalisée) ; une entité nouvelle est désignée par
    (type, nom normalisé) plutôt que par son identifiant."""
    def canon(x: Any) -> Any:
        if isinstance(x, tuple):
            return [canon(i) for i in x]
        if isinstance(x, str) and x in new_by_id:
            e = new_by_id[x]
            return ["new", e.type, _norm_value(e.name or e.label)]
        return x
    c = q.item.change
    keys = q.keys or [(c.op, getattr(c, "entity", None), getattr(c, "from_", None), getattr(c, "relation", None),
                       getattr(c, "to", None), getattr(c, "attribute", None))]
    payload = [c.op, canon(tuple(keys)), canon(_norm_value(getattr(c, "value", None)))]
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode()).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Qualification
# ---------------------------------------------------------------------------

def _context(base: State, new: dict[str, NewEntity]) -> SchemaContext:
    ctx = base.context()
    for e in new.values():
        ctx = ctx.with_entity(EntityInfo(e.id, e.type))
    return ctx


def _conflict_tag(mode: Mode) -> str:
    return "anomaly" if mode is Mode.SOURCE else "intention"


def qualify_item(item: Item, base: State, ctx: SchemaContext) -> Qualified:
    c = item.change
    q = Qualified(item, [], None)
    if item.optional:
        q.tags.add("optional")
    codes = {i.code for i in check_fact_change(c, ctx)}
    if IssueCode.OUT_OF_SCHEMA in codes:
        q.tags.add("out_of_schema")
    if IssueCode.INVALID_VALUE in codes:
        q.tags.add("invalid_value")
    if IssueCode.UNKNOWN_ENTITY in codes:
        q.tags.add("unresolved")
    try:
        q.keys = fact_keys(c, ctx)
    except UnknownRelation:
        return q
    if q.tags - {"optional"}:
        return q

    sc = c.scope
    match c:
        case SetVisibility():
            q.tags.add("hint_visibility")
            q.value = c.value
        case CreateEntity():
            q.value = ("created", c.type)
            q.tags.add("enrichment")
        case SetAttribute():
            q.value = c.value
            old = base.facts.get(("attr", qualify(c.entity, sc), c.attribute))
            if old is None:
                q.tags.add("enrichment")
            elif old.value == c.value:
                q.tags.add("support")
            else:
                q.tags.add(_conflict_tag(item.mode))
                q.detail["occupied_by"] = {"fact": list(old.id), "value": old.value}
        case AddValue():
            q.value = True
            q.tags.add("support" if q.keys[0] in base.occupancy else "enrichment")
        case AddRelation():
            fid = relation_fact_id(c.from_, c.relation, c.to, sc, ctx)
            q.value = fid
            occupants = {base.occupancy[k] for k in q.keys if k in base.occupancy}
            if occupants == {fid}:
                q.tags.add("support")
            elif occupants - {fid}:
                q.tags.add(_conflict_tag(item.mode))
                other = sorted(occupants - {fid}, key=repr)[0]
                q.detail["occupied_by"] = {"fact": list(other)}
            else:
                q.tags.add("enrichment")
        case UnsetAttribute() | RemoveValue() | RemoveRelation() | CloseEntity() | DeleteEntity():
            q.value = ("removed",)
            q.tags.add(_conflict_tag(item.mode))  # le document dit que quelque chose a cessé (R-PRI-01)
    return q


def _cross_checks(qualified: list[Qualified]) -> None:
    """Contradictions internes au document (R-ING-02) et conflits symétriques du lot (R-PRI-03)."""
    by_key: dict[FactKey, list[Qualified]] = {}
    for q in qualified:
        if "hint_visibility" in q.tags or q.value is None:
            continue
        for k in q.keys:
            by_key.setdefault(k, []).append(q)
    for key, group in sorted(by_key.items(), key=lambda kv: repr(kv[0])):
        for a in group:
            if a.is_support:
                continue
            for b in group:
                if b is a or b.value == a.value:
                    continue
                label = f"{b.item.doc_id} p{b.item.passage}"
                if b.item.doc_id == a.item.doc_id:
                    a.tags |= {"internal_contradiction", "anomaly"}
                    a.detail.setdefault("contradicts", []).append(label)
                elif not b.is_support:
                    a.tags.add("batch_conflict")
                    a.detail.setdefault("conflicts_with", []).append(label)


# ---------------------------------------------------------------------------
# Assemblage
# ---------------------------------------------------------------------------

def _subject(c: Change, sc: str) -> str:
    if isinstance(c, (AddRelation, RemoveRelation)):
        return qualify(c.from_, sc)
    if isinstance(c, SetVisibility):
        t = c.target
        return qualify(t.from_ if t.relation else t.entity or "", sc)
    return qualify(getattr(c, "entity", ""), sc)


def _cited(c: Change, sc: str) -> list[str]:
    if isinstance(c, (AddRelation, RemoveRelation)):
        return [qualify(c.from_, sc), qualify(c.to, sc)]
    if isinstance(c, SetVisibility):
        t = c.target
        return [qualify(e, sc) for e in ((t.from_, t.to) if t.relation else (t.entity,)) if e]
    if isinstance(c, CreateEntity):
        return []
    return [qualify(getattr(c, "entity", ""), sc)]


def assemble(batch_id: str, items: list[Item], base: State,
             new: dict[str, NewEntity]) -> tuple[list[Qualified], list[ProposalDraft]]:
    """Qualifie les changements du lot ; rend (supports, propositions)."""
    ctx = _context(base, new)
    new_by_id = {e.id: e for e in new.values()}
    qualified = [qualify_item(i, base, ctx) for i in items]
    _cross_checks(qualified)
    for q in qualified:
        q.fingerprint = change_fingerprint(q, new_by_id)
    supports = [q for q in qualified if q.is_support]

    groups: dict[tuple[Any, ...], list[Qualified]] = {}
    for q in qualified:
        if q.is_support:
            continue
        c = q.item.change
        kind = "hint" if isinstance(c, SetVisibility) else "facts"
        key = (q.item.doc_id, q.item.version_fp, q.item.passage, kind, _subject(c, c.scope))
        groups.setdefault(key, []).append(q)

    proposals: list[ProposalDraft] = []
    counters: dict[tuple[str, int], int] = {}
    for (doc, vfp, passage, kind, subject), group in sorted(groups.items(), key=lambda kv: kv[1][0].item.order):
        n = counters[(doc, passage)] = counters.get((doc, passage), 0) + 1
        p = ProposalDraft(f"{batch_id}.{doc}.p{passage}.{n}", doc, vfp, passage, subject, kind, group)
        created = {qualify(q.item.change.entity, q.item.change.scope) for q in group
                   if isinstance(q.item.change, CreateEntity)}
        for q in group:
            c = q.item.change
            p.writes.update(q.keys)
            if c.visibility is not None and not isinstance(c, SetVisibility):
                p.writes.update(("visibility", k) for k in q.keys)
            if "occupied_by" in q.detail or "anomaly" in q.tags or "intention" in q.tags:
                p.reads.update(q.keys)  # valeur supposée (T-ING-02)
            if isinstance(c, SetVisibility):
                try:
                    p.reads.update(target_keys(c.target, c.scope, ctx))
                except UnknownRelation:
                    pass
            for e in _cited(c, c.scope):
                if e not in created and (e in base.entities or e in new_by_id):
                    p.reads.add(("entity", e))
        edit_issues = check_edit([q.item.change for q in group], ctx).issues
        p.issues = sorted({str(i) for i in edit_issues if i.code is IssueCode.MISSING_REQUIRED})
        proposals.append(p)
    for p in proposals:
        for other in proposals:
            if other is not p and p.reads & other.writes:
                p.depends_on.add(other.id)
    return supports, proposals


__all__ = ["Item", "NewEntity", "ProposalDraft", "Qualified", "assemble", "new_entities", "resolve",
           "target_fact_id"]
