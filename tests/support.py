"""Aides de test : chemins du corpus, contexte Valmont, état de base minimal.

`naive_snapshot` n'est PAS une projection (J2) : il replie les seules opérations
additives de `base.yaml` pour fournir un état à la vérification de conformité.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from worldkit.core.schema import (
    Change, SchemaContext, StateSnapshot, check_edit, load_schema, parse_changes, qualify, read_yaml,
)
from worldkit.core.schema.changes import AddRelation, AddValue, SetAttribute

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "corpus" / "valmont-v1"
SCHEMAS = CORPUS / "schemas"
VALMONT = CORPUS / "valmont"

VALID_SCHEMAS = [
    SCHEMAS / "fantasy-default.yaml",
    VALMONT / "schema.yaml",
    VALMONT / "systems" / "system-a.yaml",
    VALMONT / "systems" / "system-b.yaml",
]
INVALID_SCHEMAS = sorted((SCHEMAS / "invalid").glob("*.yaml"))

# Champs d'annotation du gold, étrangers au format d'un changement.
GOLD_FIELDS = {
    "outcome", "note", "hint", "diff", "optional", "collides_with", "conflicts_with", "competes_with",
    "depends_on", "internal_contradiction", "same_value_as", "same_fingerprint_as",
}


def empty_context() -> SchemaContext:
    """Schémas et fiches exigées déclarés par `world.yaml` (le chargeur de monde viendra en J2)."""
    world = read_yaml(VALMONT / "world.yaml")
    systems, requirements = {}, {}
    for declared in world["rule_systems"]:
        schema = load_schema(VALMONT / declared["schema"])
        systems[schema.id] = schema
        requirements[schema.id] = declared.get("sheets", {})
    return SchemaContext(load_schema(VALMONT / world["schema"]), systems, sheet_requirements=requirements)


def base_edits() -> list[dict[str, Any]]:
    return read_yaml(VALMONT / "edits" / "base.yaml")["edits"]


def parse_ok(raws: list[dict[str, Any]]) -> list[Change]:
    changes, issues = parse_changes(raws)
    assert not issues, [str(i) for i in issues]
    return changes


def base_changes() -> list[Change]:
    return [c for e in base_edits() for c in parse_ok(e["changes"])]


def base_context() -> SchemaContext:
    ctx = empty_context()
    for edit in base_edits():
        ctx = check_edit(parse_ok(edit["changes"]), ctx).context
    return ctx


def naive_snapshot(changes: list[Change], ctx: SchemaContext) -> StateSnapshot:
    attributes: dict[tuple[str, str], Any] = {}
    values: set[tuple[str, str, Any]] = set()
    relations: set[tuple[str, str, str, str]] = set()
    for c in changes:
        if isinstance(c, SetAttribute):
            attributes[(qualify(c.entity, c.scope), c.attribute)] = c.value
        elif isinstance(c, AddValue):
            values.add((qualify(c.entity, c.scope), c.attribute, c.value))
        elif isinstance(c, AddRelation):
            relations.add((qualify(c.from_, c.scope), c.relation, qualify(c.to, c.scope), c.scope))
    return StateSnapshot(ctx.entities, attributes, frozenset(values), frozenset(relations))


def strip_gold(change: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in change.items() if k not in GOLD_FIELDS}


# --- J2 : monde en mémoire ---

def new_world():
    """Monde Valmont vierge (e000 appliquée), en mémoire."""
    from worldkit.core.world import World
    return World.create(":memory:", VALMONT / "world.yaml")


def base_world():
    """Monde Valmont à l'état de base (@base), en mémoire."""
    from worldkit.core.journal.models import parse_edit
    world = new_world()
    for raw in base_edits():
        outcome = world.apply(parse_edit(raw))
        assert outcome.status == "applied", [str(i) for i in outcome.issues]
    world.set_point("@base")
    return world


_counter = [0]


def edit(*changes: dict[str, Any], origin: str = "enrichment", id: str | None = None, **extra: Any):
    """Édition de test à identifiant unique."""
    from worldkit.core.journal.models import parse_edit
    _counter[0] += 1
    return parse_edit({"id": id or f"t{_counter[0]:04d}", "origin": origin, "changes": list(changes), **extra})


def rel(src: str, relation: str, dst: str, **extra: Any) -> dict[str, Any]:
    return {"op": "add_relation", "from": src, "relation": relation, "to": dst, **extra}


def unrel(src: str, relation: str, dst: str) -> dict[str, Any]:
    return {"op": "remove_relation", "from": src, "relation": relation, "to": dst}


def attr(entity: str, attribute: str, value: Any, **extra: Any) -> dict[str, Any]:
    return {"op": "set_attribute", "entity": entity, "attribute": attribute, "value": value, **extra}


def create(entity: str, type_: str, name: str, visibility: str | None = None) -> list[dict[str, Any]]:
    vis = {"visibility": visibility} if visibility else {}
    return [{"op": "create_entity", "entity": entity, "type": type_, **vis}, attr(entity, "name", name, **vis)]
