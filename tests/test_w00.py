"""Parcours W00 — validateur de schéma (J1 ; R-SCH-01, R-SCH-02, R-SCH-07, R-NOY-01, T-SCH-01)."""

from __future__ import annotations

import pytest

from support import INVALID_SCHEMAS, VALID_SCHEMAS
from worldkit.cli import main
from worldkit.core.schema import SchemaError, SchemaKind, has_errors, load_schema, read_yaml, validate_schema

EXPECTED_RULE = {
    "bad-attribute-type.yaml": {"T-SCH-01"},
    "bad-cardinality.yaml": {"R-SCH-01"},
    "core-type.yaml": {"R-NOY-01"},
    "relation-unknown-type.yaml": {"R-SCH-01"},
    "unknown-parent.yaml": {"R-SCH-01"},
}


@pytest.mark.parametrize("path", VALID_SCHEMAS, ids=lambda p: p.name)
def test_w00_valid_schemas_pass_with_the_same_validator(path):
    """R-SCH-02 : monde et systèmes passent par le même validateur."""
    assert validate_schema(read_yaml(path)) == []


def test_w00_same_validator_accepts_world_and_rule_systems():
    kinds = {load_schema(p).kind for p in VALID_SCHEMAS}
    assert kinds == {SchemaKind.WORLD, SchemaKind.RULE_SYSTEM}


def test_w00_all_five_invalid_schemas_are_covered():
    assert {p.name for p in INVALID_SCHEMAS} == set(EXPECTED_RULE)


@pytest.mark.parametrize("path", INVALID_SCHEMAS, ids=lambda p: p.name)
def test_w00_invalid_schemas_rejected_citing_the_rule(path):
    issues = validate_schema(read_yaml(path))
    assert has_errors(issues)
    assert {i.rule for i in issues} == EXPECTED_RULE[path.name]
    with pytest.raises(SchemaError):
        load_schema(path)


def test_w00_bad_attribute_type_reports_grammar_and_bounds():
    """T-SCH-01 : les deux défauts du fichier sont signalés, pas seulement le premier."""
    issues = validate_schema(read_yaml(next(p for p in INVALID_SCHEMAS if p.name == "bad-attribute-type.yaml")))
    paths = {i.path for i in issues}
    assert paths == {"types.Creature.attributes.mood.type", "types.Creature.attributes.hp"}


def test_cli_exit_code(capsys):
    assert main(["schema", "validate", *map(str, VALID_SCHEMAS)]) == 0
    assert main(["schema", "validate", str(VALID_SCHEMAS[0]), str(INVALID_SCHEMAS[0])]) == 1
    out = capsys.readouterr().out
    assert "REJETÉ" in out and "[T-SCH-01]" in out


def test_cli_unreadable_file(tmp_path):
    assert main(["schema", "validate", str(tmp_path / "absent.yaml")]) == 2
