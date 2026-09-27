"""Clés de fait (R-FAI-05, T-FAI-01).

Une clé est un tuple **étiqueté** par sa forme, pour qu'aucune clé d'une forme ne
puisse égaler une clé d'une autre forme (sans étiquette, la clé de relation
`(rules, brume)` aurait la forme d'une clé d'attribut `(entité, attribut)`) :

| Forme | Clé |
|---|---|
| existence d'une entité | `("entity", e)` |
| fiche d'une entité dans un système | `("sheet", e, système)` — une fiche par système (R-MET-02, L2) |
| attribut simple | `("attr", e, a)` |
| valeur d'un attribut `list[...]` | `("value", e, a, v)` |
| relation `many_to_many` | `("rel", from, r, to)` |
| relation `one_to_many` | `("rel_to", r, to)` — une cible a au plus une source |
| relation `many_to_one` | `("rel_from", from, r)` |
| relation `one_to_one` | les deux précédentes |
| contrepartie | `("counterpart", élément du monde, système)` — une par système (R-MET-04, L1) |
| notoriété d'un fait | `("visibility", clé)` (T-FAI-01) |
| affirmation / sa qualification | `("claim", c)` / `("qualification", c)` (T-FAI-01) |
| statut d'un document | `("document_status", d)` |
| élément de schéma | `("schema", portée, "type"|"relation", nom[, attribut])` — écrite par les seules éditions de schéma ; une édition ordinaire ne la lit pas, sa dépendance aux définitions est vérifiée par la revalidation (M1, T-ING-14, R-SCH-10) (L6) |

Relation symétrique : extrémités rangées par ordre lexicographique avant calcul ;
en `one_to_one`, une clé `("rel_from", extrémité, r)` par extrémité, car les rôles
from/to n'ont pas de sens (spouse_of : chacun a au plus un conjoint).
Les valeurs sont prises telles quelles, sans normalisation. Aucune dépendance au
hasard ni à l'ordre d'itération : même entrée, même sortie (T-ARC-01).
"""

from __future__ import annotations

from typing import Any

from .changes import (
    AddClaim, AddRelation, AddValue, Change, CloseEntity, CreateEntity, DeleteEntity,
    FactTarget, QualifyClaim, RemoveRelation, RemoveValue, SchemaRemoveRelation,
    SchemaRemoveType, SchemaSetRelation, SchemaSetType, SetAttribute, SetDocumentObsolete,
    SetVisibility, UnsetAttribute,
)
from .context import SchemaContext, qualify
from .core_elements import CORE_RELATIONS, COUNTERPART
from .metaschema import Cardinality

FactKey = tuple[Any, ...]


class UnknownRelation(LookupError):
    """La relation n'est déclarée ni par le schéma de la portée ni par le noyau (R-SCH-06) :
    un changement hors schéma n'a pas de clé."""


def relation_shape(relation: str, scope: str, ctx: SchemaContext) -> tuple[Cardinality, bool]:
    if relation in CORE_RELATIONS:
        return CORE_RELATIONS[relation]
    schema = ctx.schema_for(scope)
    if schema is None or relation not in schema.relations:
        raise UnknownRelation(f"relation « {relation} » non déclarée (portée {scope})")
    r = schema.relations[relation]
    return r.cardinality, r.symmetric


def relation_keys(source: str, relation: str, target: str,
                  cardinality: Cardinality, symmetric: bool) -> list[FactKey]:
    if symmetric:
        source, target = sorted((source, target))
        if cardinality is Cardinality.ONE_TO_ONE:
            # Les rôles from/to sont interchangeables : l'unicité porte sur chaque extrémité,
            # sinon spouse_of(mervin, isabeau) et spouse_of(mervin, zoe) ne collisionneraient
            # pas quand mervin tombe d'un côté puis de l'autre après tri.
            return [("rel_from", source, relation), ("rel_from", target, relation)]
        # Une relation symétrique n'admet que one_to_one ou many_to_many (validate.py, R-SCH-01).
    if cardinality is Cardinality.MANY_TO_MANY:
        return [("rel", source, relation, target)]
    if cardinality is Cardinality.ONE_TO_MANY:
        return [("rel_to", relation, target)]
    if cardinality is Cardinality.MANY_TO_ONE:
        return [("rel_from", source, relation)]
    return [("rel_from", source, relation), ("rel_to", relation, target)]


def fact_keys(change: Change, ctx: SchemaContext) -> list[FactKey]:
    """Clés des faits qu'écrit un changement. Lève `UnknownRelation` si la relation est hors schéma."""
    s = change.scope
    match change:
        case CreateEntity():
            eid = qualify(change.entity, s)
            return [("entity", eid)] + ([("sheet", change.sheet.of, change.sheet.system)] if change.sheet else [])
        case CloseEntity() | DeleteEntity():
            eid = qualify(change.entity, s)
            info = ctx.entities.get(eid)
            sheet = info.sheet if info is not None else None
            return [("entity", eid)] + ([("sheet", sheet.of, sheet.system)] if sheet else [])
        case SetAttribute() | UnsetAttribute():
            return [("attr", qualify(change.entity, s), change.attribute)]
        case AddValue() | RemoveValue():
            return [("value", qualify(change.entity, s), change.attribute, change.value)]
        case AddRelation() | RemoveRelation():
            return _relation_keys(change.from_, change.relation, change.to, s, ctx)
        case SetVisibility():
            return [("visibility", k) for k in target_keys(change.target, s, ctx)]
        case AddClaim():
            return [("claim", change.claim)]
        case QualifyClaim():
            return [("qualification", change.claim)]
        case SetDocumentObsolete():
            return [("document_status", change.document)]
        case SchemaSetType() | SchemaRemoveType():
            key: FactKey = ("schema", s, "type", change.type)
            attribute = getattr(change, "attribute", None)
            return [key + (attribute,) if attribute else key]
        case SchemaSetRelation() | SchemaRemoveRelation():
            return [("schema", s, "relation", change.relation)]
    raise TypeError(f"opération inconnue : {change!r}")  # pragma: no cover — catalogue fermé


def target_keys(target: FactTarget, scope: str, ctx: SchemaContext) -> list[FactKey]:
    """Clés du fait désigné (pour les sous-clés de notoriété)."""
    if target.relation is not None:
        return _relation_keys(target.from_ or "", target.relation, target.to or "", scope, ctx)
    entity = qualify(target.entity or "", scope)
    if target.attribute is None:
        return [("entity", entity)]
    if target.value is not None:
        return [("value", entity, target.attribute, target.value)]
    return [("attr", entity, target.attribute)]


def system_of(entity: str, ctx: SchemaContext) -> str:
    """Portée d'un élément : celle qui l'a créé, sinon le préfixe `système:` de son identifiant."""
    info = ctx.entities.get(entity)
    if info is not None:
        return info.scope
    return entity.split(":", 1)[0] if ":" in entity else "world"


def _relation_keys(source: str, relation: str, target: str, scope: str, ctx: SchemaContext) -> list[FactKey]:
    if relation == COUNTERPART:  # au plus une contrepartie par système (R-MET-04, L1)
        target = qualify(target, scope)
        return [("counterpart", qualify(source, scope), system_of(target, ctx))]
    cardinality, symmetric = relation_shape(relation, scope, ctx)
    return relation_keys(qualify(source, scope), relation, qualify(target, scope), cardinality, symmetric)


def format_key(key: FactKey) -> str:
    """Forme lisible : `(rules, brume)`, `visibility(odon, rules)`."""
    tag, *parts = key
    if tag == "visibility":
        return f"visibility{format_key(parts[0])}"
    return "(" + ", ".join(str(p) for p in parts) + ")"
