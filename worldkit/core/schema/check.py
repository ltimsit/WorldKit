"""Vérification d'un changement, d'une édition ou d'un état contre les schémas (T-SCH-01).

Trois verdicts distincts (R-SCH-10) :

- **hors schéma** (`out_of_schema`, R-SCH-06) : le changement cite un type, un attribut ou une
  relation que le schéma de l'état visé ne déclare pas → non applicable ;
- **valeur invalide** (`invalid_value`, R-SCH-06 élargie : « non représentable ») : élément déclaré,
  mais valeur, type d'extrémité ou opération contraire à ses contraintes → non applicable ;
- **non-conformité** (`non_conforming`, R-SCH-10, R-MET-06) : élément d'un état, valide à son
  écriture, devenu invalide après une modification du schéma → toléré et signalé, jamais modifié.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field, replace

from .changes import (
    WORLD_SCOPE, AddRelation, AddValue, Change, CloseEntity, CreateEntity, DeleteEntity,
    RemoveRelation, RemoveValue, SCHEMA_OPS, Scalar, SchemaRemoveRelation, SchemaRemoveType,
    SchemaSetRelation, SchemaSetType, SetAttribute, SetVisibility, UnsetAttribute,
)
from .context import EntityInfo, SchemaContext, qualify
from .core_elements import CORE_RELATIONS, CORE_TYPES, PROVISIONAL_CORE_RELATIONS, SAME_AS_KINDS, SHEET_TYPE
from .issues import Issue, IssueCode, Severity
from .keys import FactKey, relation_keys, relation_shape
from .metaschema import AttributeDef, ScalarKind, Schema, TypeDef
from .validate import check_schema


# ---------------------------------------------------------------------------
# Valeurs
# ---------------------------------------------------------------------------

def value_problem(value: Scalar, attr: AttributeDef, owner_scope: str,
                  owner_schema: Schema, entities: Mapping[str, EntityInfo]) -> str | None:
    """Rend la raison pour laquelle `value` viole la définition de l'attribut, ou None."""
    t = attr.type
    match t.kind:
        case ScalarKind.TEXT:
            if not isinstance(value, str):
                return f"valeur {value!r} : texte attendu"
        case ScalarKind.BOOLEAN:
            if not isinstance(value, bool):
                return f"valeur {value!r} : booléen attendu"
        case ScalarKind.INTEGER:
            if isinstance(value, bool) or not isinstance(value, int):
                return f"valeur {value!r} : entier attendu"
            if attr.min is not None and value < attr.min:
                return f"valeur {value} inférieure au minimum {attr.min}"
            if attr.max is not None and value > attr.max:
                return f"valeur {value} supérieure au maximum {attr.max}"
        case ScalarKind.REF:
            if not isinstance(value, str):
                return f"valeur {value!r} : référence à une entité attendue"
            target = entities.get(qualify(value, owner_scope))
            if target is None:
                return f"référence « {value} » vers une entité inconnue"
            if target.scope != owner_scope or not owner_schema.is_subtype(target.type, t.ref_target or ""):
                return f"référence « {value} » : entité de type {target.type}, attendu {t.ref_target}"
    return None


# ---------------------------------------------------------------------------
# Changements de schéma (R-SCH-03)
# ---------------------------------------------------------------------------

class SchemaChangeError(ValueError):
    pass


def apply_schema_change(schema: Schema, change: Change) -> Schema:
    """Schéma obtenu après un changement `schema_*` ; ne valide pas le résultat (voir `check_schema`)."""
    match change:
        case SchemaSetType(attribute=None):
            assert isinstance(change.definition, TypeDef)
            return schema.with_type(change.type, change.definition)
        case SchemaSetType():
            if change.type not in schema.types:
                raise SchemaChangeError(f"type « {change.type} » non déclaré")
            t = schema.types[change.type]
            if change.definition is not None:
                new_attr = change.definition
            else:
                if change.attribute not in t.attributes:
                    raise SchemaChangeError(
                        f"attribut « {change.attribute} » non déclaré en propre par « {change.type} »")
                patch = change.constraint.model_dump(exclude_none=True) if change.constraint else {}
                try:
                    new_attr = AttributeDef.model_validate({**t.attributes[change.attribute].model_dump(), **patch})
                except ValueError as e:
                    raise SchemaChangeError(str(e)) from e
            attrs = {**t.attributes, change.attribute: new_attr}
            return schema.with_type(change.type, t.model_copy(update={"attributes": attrs}))
        case SchemaRemoveType():
            if change.type not in schema.types:
                raise SchemaChangeError(f"type « {change.type} » non déclaré")
            return schema.without_type(change.type)
        case SchemaSetRelation():
            return schema.with_relation(change.relation, change.definition)
        case SchemaRemoveRelation():
            if change.relation not in schema.relations:
                raise SchemaChangeError(f"relation « {change.relation} » non déclarée")
            return schema.without_relation(change.relation)
    raise TypeError(f"pas un changement de schéma : {change!r}")


# ---------------------------------------------------------------------------
# Vérification d'un changement de fait
# ---------------------------------------------------------------------------

def _out(msg: str, path: str = "") -> Issue:
    return Issue(IssueCode.OUT_OF_SCHEMA, msg, "R-SCH-06", path=path)


def _invalid(msg: str, rule: str = "R-SCH-06", path: str = "") -> Issue:
    return Issue(IssueCode.INVALID_VALUE, msg, rule, path=path)


def _unknown(entity: str, path: str = "") -> Issue:
    return Issue(IssueCode.UNKNOWN_ENTITY,
                 f"entité « {entity} » absente de l'état visé", "R-EDI-04", path=path)


def _check_fact_change(change: Change, ctx: SchemaContext) -> list[Issue]:
    scope = change.scope
    if scope != WORLD_SCOPE and scope not in ctx.systems:
        return [_out(f"portée « {scope} » : ni le monde, ni un système déclaré")]
    match change:
        case CreateEntity():
            return _check_create(change, ctx)
        case CloseEntity() | DeleteEntity():
            entity = qualify(change.entity, scope)
            return [] if entity in ctx.entities else [_unknown(entity)]
        case SetAttribute() | UnsetAttribute() | AddValue() | RemoveValue():
            return _check_attribute(change, ctx)
        case AddRelation() | RemoveRelation():
            kind = change.kind if isinstance(change, AddRelation) else None
            return _check_relation(change.from_, change.relation, change.to, scope, ctx,
                                   kind=kind, adding=isinstance(change, AddRelation))
        case SetVisibility():
            t = change.target
            if t.relation is not None:
                return _check_relation(t.from_ or "", t.relation, t.to or "", scope, ctx,
                                       kind=None, adding=False)
            entity = qualify(t.entity or "", scope)
            info = ctx.entities.get(entity)
            if info is None:
                return [_unknown(entity)]
            if t.attribute is not None:
                owner = ctx.owner(info)
                if owner is None or t.attribute not in owner[1].attributes_of(owner[2]):
                    return [_out(f"attribut « {t.attribute} » non déclaré pour « {entity} »")]
            return []
    # Affirmations et documents : types noyau, rien à vérifier contre un schéma en J1.
    return []


def _check_create(change: CreateEntity, ctx: SchemaContext) -> list[Issue]:
    scope = change.scope
    schema = ctx.schema_for(scope)
    assert schema is not None
    if change.type == SHEET_TYPE:
        b = change.sheet
        if b is None:
            return [_invalid("une fiche (Sheet) doit porter sheet: {of, system, category}", "R-MET-01")]
        issues: list[Issue] = []
        system = ctx.systems.get(b.system)
        if system is None:
            issues.append(_out(f"fiche dans le système « {b.system} », non déclaré"))
        elif b.category not in system.types:
            issues.append(_out(f"catégorie « {b.category} » non déclarée par le système « {b.system} »"))
        if b.of not in ctx.entities:
            issues.append(_unknown(b.of))
        return issues
    if change.sheet is not None:
        return [_invalid("« sheet » est réservé aux entités de type Sheet", "R-MET-01")]
    if change.type in CORE_TYPES:
        return [_out(f"le type noyau « {change.type} » ne se crée pas par create_entity")]
    if change.type not in schema.types:
        return [_out(f"type « {change.type} » non déclaré (portée {scope})")]
    return []


def _check_attribute(change: SetAttribute | UnsetAttribute | AddValue | RemoveValue,
                     ctx: SchemaContext) -> list[Issue]:
    entity = qualify(change.entity, change.scope)
    info = ctx.entities.get(entity)
    if info is None:
        return [_unknown(entity)]
    owner = ctx.owner(info)
    if owner is None:
        return [_out(f"aucun schéma ne définit les attributs de « {entity} »")]
    owner_scope, owner_schema, owner_type = owner
    attr = owner_schema.attributes_of(owner_type).get(change.attribute)
    if attr is None:
        return [_out(f"attribut « {change.attribute} » non déclaré pour {owner_type} (portée {owner_scope})")]
    multi = isinstance(change, (AddValue, RemoveValue))
    if attr.type.is_list and not multi:
        return [_invalid(f"« {change.attribute} » est un attribut à valeurs multiples ({attr.type}) : "
                         "il se modifie par add_value et remove_value", "R-SCH-01")]
    if multi and not attr.type.is_list:
        return [_invalid(f"« {change.attribute} » n'est pas à valeurs multiples : "
                         "add_value et remove_value ne s'y appliquent pas", "R-SCH-01")]
    if isinstance(change, UnsetAttribute):
        return [_invalid(f"« {change.attribute} » est requis : il ne peut pas être vidé")] if attr.required else []
    problem = value_problem(change.value, attr, owner_scope, owner_schema, ctx.entities)
    return [_invalid(f"{owner_type}.{change.attribute} : {problem}")] if problem else []


def _check_relation(source: str, relation: str, target: str, scope: str, ctx: SchemaContext,
                    *, kind: str | None, adding: bool) -> list[Issue]:
    source, target = qualify(source, scope), qualify(target, scope)
    issues: list[Issue] = []
    if relation in CORE_RELATIONS:
        if relation == "same_as" and adding and kind not in SAME_AS_KINDS:
            issues.append(_invalid(f"same_as doit être qualifiée : kind ∈ {sorted(SAME_AS_KINDS)}", "R-IDT-02"))
        if relation in PROVISIONAL_CORE_RELATIONS:
            issues.append(Issue(
                IssueCode.PROVISIONAL_CORE_RELATION,
                f"relation noyau provisoire « {relation} » (lacune L1 : nom et forme du lien double face à trancher)",
                "R-MET-04", severity=Severity.WARNING))
        issues.extend(_unknown(e) for e in (source, target) if e not in ctx.entities)
        return issues
    if kind is not None:
        issues.append(_invalid("« kind » ne qualifie que same_as", "R-IDT-02"))
    schema = ctx.schema_for(scope)
    assert schema is not None
    r = schema.relations.get(relation)
    if r is None:
        return issues + [_out(f"relation « {relation} » non déclarée (portée {scope})")]
    for end, entity, allowed in (("from", source, r.from_), ("to", target, r.to)):
        info = ctx.entities.get(entity)
        if info is None:
            issues.append(_unknown(entity))
        elif info.scope != scope or info.sheet is not None \
                or not any(schema.is_subtype(info.type, t) for t in allowed):
            issues.append(_invalid(
                f"{relation}.{end} : « {entity} » est de type {info.type}, attendu {' ou '.join(allowed)}"))
    return issues


# ---------------------------------------------------------------------------
# API : changement, édition
# ---------------------------------------------------------------------------

def check_change(change: Change, ctx: SchemaContext) -> list[Issue]:
    """Vérifie un changement isolé contre l'état visé (édition à un seul changement)."""
    return check_edit([change], ctx).issues


@dataclass(frozen=True)
class EditCheck:
    issues: list[Issue]
    context: SchemaContext  # contexte après l'édition : schémas modifiés, entités créées ou supprimées

    @property
    def applicable(self) -> bool:
        return not any(i.severity is Severity.ERROR for i in self.issues)


def check_edit(changes: Iterable[Change], ctx: SchemaContext) -> EditCheck:
    """Vérifie une édition.

    Les changements de fait sont vérifiés contre le schéma obtenu **après** les changements
    `schema_*` de la même édition, quel que soit leur ordre (R-SCH-03, R-SCH-06, R-MET-05 ;
    cadre technique §5, parcours W09). Les entités, elles, évoluent dans l'ordre de l'édition.
    """
    changes = list(changes)
    issues: list[Issue] = []

    # 1. Schémas : appliquer tous les changements schema_*, puis valider chaque schéma modifié.
    touched: list[str] = []
    for index, change in enumerate(changes):
        if not isinstance(change, SCHEMA_OPS):
            continue
        path = f"changes[{index}]"
        schema = ctx.schema_for(change.scope)
        if schema is None:
            issues.append(_out(f"portée « {change.scope} » : ni le monde, ni un système déclaré", path))
            continue
        try:
            ctx = ctx.with_schema(change.scope, apply_schema_change(schema, change))
        except SchemaChangeError as e:
            issues.append(Issue(IssueCode.UNDECLARED_REFERENCE, str(e), "R-SCH-01", path=path))
            continue
        if change.scope not in touched:
            touched.append(change.scope)
    for scope in touched:
        schema = ctx.schema_for(scope)
        assert schema is not None
        issues.extend(Issue(i.code, f"schéma « {scope} » après l'édition : {i.message}", i.rule, i.severity,
                            i.path) for i in check_schema(schema))

    # 2. Faits, dans l'ordre ; suivi des attributs posés pour contrôler les attributs requis.
    created: dict[str, EntityInfo] = {}
    filled: set[tuple[str, str]] = set()
    for index, change in enumerate(changes):
        if isinstance(change, SCHEMA_OPS):
            continue
        path = f"changes[{index}]"
        found = _check_fact_change(change, ctx)
        issues.extend(Issue(i.code, i.message, i.rule, i.severity, i.path or path) for i in found)
        blocking = any(i.severity is Severity.ERROR for i in found)
        if isinstance(change, CreateEntity) and not blocking:
            info = EntityInfo(qualify(change.entity, change.scope), change.type, change.scope, change.sheet)
            ctx = ctx.with_entity(info)
            created[info.id] = info
        elif isinstance(change, DeleteEntity):
            ctx = ctx.without_entity(qualify(change.entity, change.scope))
        elif isinstance(change, (SetAttribute, AddValue)):
            filled.add((qualify(change.entity, change.scope), change.attribute))

    # 3. Une entité créée par l'édition doit en sortir avec ses attributs requis (décision A, R-SCH-06).
    for entity, info in created.items():
        owner = ctx.owner(info)
        if owner is None:
            continue
        for name, attr in owner[1].attributes_of(owner[2]).items():
            if attr.required and (entity, name) not in filled:
                issues.append(_invalid(f"« {entity} » est créée sans l'attribut requis « {name} »"))
    return EditCheck(issues, ctx)


# ---------------------------------------------------------------------------
# Conformité d'un état (R-SCH-04, R-SCH-10, R-MET-06)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class StateSnapshot:
    """Faits d'un état, sous forme minimale (J2 fournira la projection).

    `attributes` : attributs simples ; `values` : valeurs des attributs `list[...]` ;
    `relations` : `(from, relation, to, portée)`.
    """

    entities: Mapping[str, EntityInfo]
    attributes: Mapping[tuple[str, str], Scalar] = field(default_factory=dict)
    values: frozenset[tuple[str, str, Scalar]] = frozenset()
    relations: frozenset[tuple[str, str, str, str]] = frozenset()


def _nc(msg: str, path: str = "") -> Issue:
    return Issue(IssueCode.NON_CONFORMING, msg, "R-SCH-10", Severity.WARNING, path)


def check_conformity(state: StateSnapshot, ctx: SchemaContext) -> list[Issue]:
    """Signale les éléments de l'état que les schémas actuels ne valident plus, et les fiches
    manquantes (R-MET-06). Ne modifie rien."""
    ctx = replace(ctx, entities=state.entities)
    issues: list[Issue] = []

    for entity, info in sorted(state.entities.items()):
        if info.sheet is not None:
            system = ctx.systems.get(info.sheet.system)
            if system is None or info.sheet.category not in system.types:
                issues.append(_nc(f"fiche « {entity} » : catégorie {info.sheet.category} absente du système "
                                  f"{info.sheet.system}", entity))
                continue
        else:
            schema = ctx.schema_for(info.scope)
            if schema is None or info.type not in schema.types:
                issues.append(_nc(f"« {entity} » : type {info.type} non déclaré (portée {info.scope})", entity))
                continue
        owner = ctx.owner(info)
        assert owner is not None
        owner_scope, owner_schema, owner_type = owner
        declared = owner_schema.attributes_of(owner_type)
        present = {a for (e, a) in state.attributes if e == entity} | {a for (e, a, _) in state.values if e == entity}
        for name in sorted(present - declared.keys()):
            issues.append(_nc(f"« {entity} » : attribut {name} non déclaré pour {owner_type}", f"{entity}.{name}"))
        for name, attr in sorted(declared.items()):
            path = f"{entity}.{name}"
            if attr.required and name not in present:
                issues.append(_nc(f"« {entity} » : attribut requis {name} absent", path))
            if name not in present:
                continue
            if attr.type.is_list != ((entity, name) not in state.attributes):
                issues.append(_nc(f"« {entity} » : {name} n'a plus la forme {attr.type}", path))
                continue
            found = [state.attributes[(entity, name)]] if not attr.type.is_list else \
                sorted((v for (e, a, v) in state.values if (e, a) == (entity, name)), key=repr)
            for value in found:
                problem = value_problem(value, attr, owner_scope, owner_schema, ctx.entities)
                if problem:
                    issues.append(_nc(f"{owner_type}.{name} de « {entity} » : {problem}", path))

    issues.extend(_relation_conformity(state, ctx))
    issues.extend(check_sheet_requirements(ctx))
    issues.extend(_missing_sheets(ctx))
    return issues


def check_sheet_requirements(ctx: SchemaContext) -> list[Issue]:
    """La correspondance type du monde → catégorie ne cite que des éléments déclarés.

    Signalement non bloquant : une modification de schéma peut la rendre caduque (R-SCH-04).
    """
    issues: list[Issue] = []
    for system_id, mapping in sorted(ctx.sheet_requirements.items()):
        system = ctx.systems.get(system_id)
        for world_type, category in sorted(mapping.items()):
            path = f"rule_systems.{system_id}.sheets.{world_type}"
            if world_type not in ctx.world.types:
                issues.append(_nc(f"fiches exigées pour le type « {world_type} », non déclaré par le monde", path))
            if system is None:
                issues.append(_nc(f"fiches exigées dans le système « {system_id} », non déclaré", path))
            elif category not in system.types:
                issues.append(_nc(f"catégorie « {category} » non déclarée par le système « {system_id} »", path))
    return issues


def _missing_sheets(ctx: SchemaContext) -> list[Issue]:
    """R-MET-06 : une entité du monde dont le type (ou un parent) exige une fiche dans un système, sans fiche."""
    have = {(i.sheet.of, i.sheet.system) for i in ctx.entities.values() if i.sheet is not None}
    issues: list[Issue] = []
    for entity, info in sorted(ctx.entities.items()):
        if info.sheet is not None or info.scope != WORLD_SCOPE:
            continue
        lineage = ctx.world.ancestors(info.type)
        for system_id, mapping in sorted(ctx.sheet_requirements.items()):
            required = next((mapping[t] for t in lineage if t in mapping), None)
            if required is not None and (entity, system_id) not in have:
                issues.append(Issue(
                    IssueCode.MISSING_SHEET,
                    f"« {entity} » ({info.type}) n'a pas de fiche dans le système « {system_id} » "
                    f"(catégorie attendue : {required})",
                    "R-MET-06", Severity.WARNING, f"{entity}@{system_id}"))
    return issues


def _relation_conformity(state: StateSnapshot, ctx: SchemaContext) -> list[Issue]:
    issues: list[Issue] = []
    occupied: dict[FactKey, tuple[str, str, str]] = {}
    for source, relation, target, scope in sorted(state.relations):
        label = f"{relation}({source}, {target})"
        if relation not in CORE_RELATIONS:
            found = _check_relation(source, relation, target, scope, ctx, kind=None, adding=False)
            if found:
                issues.extend(_nc(f"{label} : {i.message}", label) for i in found)
                continue
        cardinality, symmetric = relation_shape(relation, scope, ctx)
        fact = (*sorted((source, target)),) if symmetric else (source, target)
        fact = (fact[0], relation, fact[1])
        # Deux faits de même clé dans un état : la cardinalité a changé depuis leur écriture (R-FAI-05).
        for key in relation_keys(source, relation, target, cardinality, symmetric):
            other = occupied.get(key)
            if other is not None and other != fact:
                issues.append(_nc(f"{label} et {other[1]}({other[0]}, {other[2]}) occupent la même clé "
                                  f"(cardinalité {cardinality})", label))
            occupied.setdefault(key, fact)
    return issues

