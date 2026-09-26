"""État projeté (M3 ; R-HIS-02, T-STO-01).

Un état = schémas + entités + faits indexés par identifiant et par clé de fait.
`apply_change` fait confiance à son entrée : les contrôles (M1, collisions M4)
ont lieu avant l'application ; le rejeu du journal n'applique que des éditions
qui les ont passés.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from typing import Any, Literal

from worldkit.core.schema import (
    Change, EntityInfo, FactKey, Schema, SchemaContext, SchemaKind, SheetBinding, Visibility, fact_keys, qualify,
)
from worldkit.core.schema.changes import (
    WORLD_SCOPE, AddClaim, AddRelation, AddValue, CloseEntity, CreateEntity, DeleteEntity, FactTarget,
    QualifyClaim, RemoveRelation, RemoveValue, SCHEMA_OPS, Scalar, SetAttribute, SetDocumentObsolete,
    SetVisibility, UnsetAttribute,
)
from worldkit.core.schema.check import apply_schema_change
from worldkit.core.schema.keys import relation_shape
from worldkit.core.schema.metaschema import ScalarKind

FactId = tuple[Any, ...]  # ("attr", e, a) | ("value", e, a, v) | ("rel", from, r, to)


@dataclass(frozen=True)
class EntityRecord(EntityInfo):
    visibility: Visibility = Visibility.UNQUALIFIED
    closed: bool = False
    established_by: str = ""
    created_seq: int = 0  # rang de l'édition de création : départage les doublons (R-IDT-04)


@dataclass(frozen=True)
class Fact:
    id: FactId
    kind: Literal["attr", "value", "rel"]
    subject: str            # entité (attribut) ou source (relation)
    name: str               # attribut ou relation
    value: Scalar | None    # attributs
    target: str | None      # relations
    scope: str
    visibility: Visibility
    established_by: str     # provenance : édition qui a établi le fait (R-FAI-01)
    propagation_lifted: bool = False
    same_as_kind: str | None = None
    diegetic_window: Any = None  # préparé (R-FAI-03) : conservé, sans effet


@dataclass(frozen=True)
class WorldDeclaration:
    """Ce que déclare `world.yaml`, hors du journal (R-MON-01 à R-MON-03)."""

    world: str
    reference_branch: str
    world_schema: Schema               # en-tête seul ; le contenu arrive par e000
    systems: Mapping[str, Schema]      # idem
    sheet_requirements: Mapping[str, Mapping[str, str]] = field(default_factory=dict)


@dataclass
class State:
    branch: str
    seq: int
    schema_rev: int
    world: Schema
    systems: dict[str, Schema]
    sheet_requirements: Mapping[str, Mapping[str, str]]
    entities: dict[str, EntityRecord] = field(default_factory=dict)
    facts: dict[FactId, Fact] = field(default_factory=dict)
    occupancy: dict[FactKey, FactId] = field(default_factory=dict)
    claims: dict[str, dict[str, Any]] = field(default_factory=dict)
    qualifications: dict[str, dict[str, Any]] = field(default_factory=dict)
    obsolete_documents: dict[str, bool] = field(default_factory=dict)

    def context(self) -> SchemaContext:
        return SchemaContext(self.world, self.systems, self.entities, self.sheet_requirements)

    def copy(self) -> State:
        return replace(self, systems=dict(self.systems), entities=dict(self.entities), facts=dict(self.facts),
                       occupancy=dict(self.occupancy), claims=dict(self.claims),
                       qualifications=dict(self.qualifications), obsolete_documents=dict(self.obsolete_documents))

    def facts_of(self, entity: str) -> list[Fact]:
        return sorted((f for f in self.facts.values() if entity in (f.subject, f.target)), key=lambda f: repr(f.id))


def empty_state(decl: WorldDeclaration, branch: str) -> State:
    return State(branch=branch, seq=0, schema_rev=0, world=decl.world_schema, systems=dict(decl.systems),
                 sheet_requirements=decl.sheet_requirements)


def empty_schema(like: Schema) -> Schema:
    return like.model_copy(update={"types": {}, "relations": {}})


# ---------------------------------------------------------------------------
# Identifiants de faits
# ---------------------------------------------------------------------------

def relation_fact_id(source: str, relation: str, target: str, scope: str, ctx: SchemaContext) -> FactId:
    _, symmetric = relation_shape(relation, scope, ctx)
    s, t = qualify(source, scope), qualify(target, scope)
    if symmetric:
        s, t = sorted((s, t))
    return ("rel", s, relation, t)


def fact_id_of(change: Change, ctx: SchemaContext) -> FactId | None:
    sc = change.scope
    match change:
        case SetAttribute() | UnsetAttribute():
            return ("attr", qualify(change.entity, sc), change.attribute)
        case AddValue() | RemoveValue():
            return ("value", qualify(change.entity, sc), change.attribute, change.value)
        case AddRelation() | RemoveRelation():
            return relation_fact_id(change.from_, change.relation, change.to, sc, ctx)
    return None


def target_fact_id(target: FactTarget, scope: str, ctx: SchemaContext) -> FactId | None:
    """Identifiant du fait désigné par `set_visibility`, ou None si la cible est une entité."""
    if target.relation is not None:
        return relation_fact_id(target.from_ or "", target.relation, target.to or "", scope, ctx)
    entity = qualify(target.entity or "", scope)
    if target.attribute is None:
        return None
    if target.value is not None:
        return ("value", entity, target.attribute, target.value)
    return ("attr", entity, target.attribute)


def mentioned_entities(fact: Fact, state: State) -> list[str]:
    """Entités qu'un fait mentionne (R-NOT-04) : sujet, cible, et entité référencée par un attribut `ref`."""
    out = [fact.subject]
    if fact.target is not None:
        out.append(fact.target)
    elif isinstance(fact.value, str):
        info = state.entities.get(fact.subject)
        owner = state.context().owner(info) if info else None
        if owner is not None:
            attr = owner[1].attributes_of(owner[2]).get(fact.name)
            if attr is not None and attr.type.kind is ScalarKind.REF:
                out.append(qualify(fact.value, owner[0]))
    return out


# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------

def _put(state: State, fact: Fact, keys: list[FactKey]) -> None:
    state.facts[fact.id] = fact
    for k in keys:
        state.occupancy[k] = fact.id


def _drop(state: State, fid: FactId) -> None:
    state.facts.pop(fid, None)
    for k in [k for k, v in state.occupancy.items() if v == fid]:
        del state.occupancy[k]


def apply_change(state: State, change: Change, edit_id: str) -> None:
    """Applique un changement déjà vérifié (mutation de `state`)."""
    sc = change.scope
    ctx = state.context()
    if isinstance(change, SCHEMA_OPS):
        schema = ctx.schema_for(sc)
        assert schema is not None
        new = apply_schema_change(schema, change)
        if sc == WORLD_SCOPE:
            state.world = new
        else:
            state.systems[sc] = new
        state.schema_rev = state.seq
        return
    match change:
        case CreateEntity():
            eid = qualify(change.entity, sc)
            state.entities[eid] = EntityRecord(eid, change.type, sc, change.sheet,
                                               visibility=change.visibility or Visibility.UNQUALIFIED,
                                               established_by=edit_id, created_seq=state.seq)
            state.occupancy[("entity", eid)] = ("entity", eid)
        case CloseEntity():
            eid = qualify(change.entity, sc)
            state.entities[eid] = replace(state.entities[eid], closed=True)
        case DeleteEntity():
            eid = qualify(change.entity, sc)
            for f in list(state.facts.values()):
                if eid in mentioned_entities(f, state):
                    _drop(state, f.id)
            del state.entities[eid]
            state.occupancy.pop(("entity", eid), None)
        case SetAttribute() | AddValue() | AddRelation():
            fid = fact_id_of(change, ctx)
            assert fid is not None
            old = state.facts.get(fid)
            # T-FAI-01 : sans notoriété explicite, remplacer une valeur garde la notoriété du fait.
            visibility = change.visibility or (old.visibility if old else Visibility.UNQUALIFIED)
            if isinstance(change, AddRelation):
                fact = Fact(fid, "rel", fid[1], change.relation, None, fid[3], sc, visibility, edit_id,
                            old.propagation_lifted if old else False, change.kind, change.diegetic_window)
            else:
                kind: Literal["attr", "value"] = "attr" if isinstance(change, SetAttribute) else "value"
                fact = Fact(fid, kind, fid[1], change.attribute, change.value, None, sc, visibility, edit_id,
                            old.propagation_lifted if old else False, None, change.diegetic_window)
            _put(state, fact, fact_keys(change, ctx))
        case UnsetAttribute() | RemoveValue() | RemoveRelation():
            fid = fact_id_of(change, ctx)
            assert fid is not None
            _drop(state, fid)
        case SetVisibility():
            fid = target_fact_id(change.target, sc, ctx)
            if fid is None:
                eid = qualify(change.target.entity or "", sc)
                state.entities[eid] = replace(state.entities[eid], visibility=change.value)
            else:
                old = state.facts[fid]
                lifted = old.propagation_lifted if change.propagation_lifted is None else change.propagation_lifted
                state.facts[fid] = replace(old, visibility=change.value, propagation_lifted=lifted)
        case AddClaim():
            state.claims[change.claim] = {"document": change.document, "speaker": change.speaker,
                                          "text": change.text, "claimed": change.claimed,
                                          "visibility": change.visibility, "established_by": edit_id}
        case QualifyClaim():
            state.qualifications[change.claim] = {"value": change.value, "visibility": change.visibility,
                                                  "established_by": edit_id}
        case SetDocumentObsolete():
            state.obsolete_documents[change.document] = change.value


__all__ = [
    "EntityRecord", "Fact", "FactId", "SheetBinding", "State", "WorldDeclaration", "SchemaKind",
    "apply_change", "empty_schema", "empty_state", "fact_id_of", "mentioned_entities", "relation_fact_id",
    "target_fact_id",
]
