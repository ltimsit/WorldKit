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
    return SchemaContext(
        world=load_schema(VALMONT / "schema.yaml"),
        systems={
            "system-a": load_schema(VALMONT / "systems" / "system-a.yaml"),
            "system-b": load_schema(VALMONT / "systems" / "system-b.yaml"),
        },
    )


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
