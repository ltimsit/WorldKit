"""Signalements produits par le module M1.

Chaque signalement (`Issue`) porte un code stable, un message en français et
l'identifiant de la règle du cadre qui le fonde (brief J1 §5).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Severity(StrEnum):
    ERROR = "error"      # bloquant : schéma rejeté, changement non applicable
    WARNING = "warning"  # signalé, non bloquant (non-conformité, lacune connue)


class IssueCode(StrEnum):
    # Validation d'un schéma
    MALFORMED_SCHEMA = "malformed_schema"
    CORE_TYPE_DECLARED = "core_type_declared"
    UNDECLARED_REFERENCE = "undeclared_reference"
    INHERITANCE_CYCLE = "inheritance_cycle"
    INHERITED_ATTRIBUTE_REDEFINED = "inherited_attribute_redefined"
    INVALID_BOUNDS = "invalid_bounds"
    ASYMMETRIC_SYMMETRIC_RELATION = "asymmetric_symmetric_relation"
    NON_ENGLISH_IDENTIFIER = "non_english_identifier"
    # Vérification d'un changement
    MALFORMED_CHANGE = "malformed_change"
    OUT_OF_SCHEMA = "out_of_schema"
    INVALID_VALUE = "invalid_value"
    MISSING_REQUIRED = "missing_required"
    UNKNOWN_ENTITY = "unknown_entity"
    PROVISIONAL_CORE_RELATION = "provisional_core_relation"
    # Conformité d'un état
    NON_CONFORMING = "non_conforming"
    MISSING_SHEET = "missing_sheet"
    MASKED_PUBLIC_FACT = "masked_public_fact"
    ORPHAN_FACT = "orphan_fact"
    # Application d'une édition (M2, M4)
    EDIT_RULE = "edit_rule"
    KEY_COLLISION = "key_collision"
    INTERNAL_CONTRADICTION = "internal_contradiction"
    MISSING_FACT = "missing_fact"
    STALE_EDIT = "stale_edit"
    DOCUMENT_OBSOLETE = "document_obsolete"
    SCENARIO_DEPENDENCY = "scenario_dependency"
    ARCHIVED_BRANCH = "archived_branch"


@dataclass(frozen=True)
class Issue:
    code: IssueCode
    message: str
    rule: str
    severity: Severity = Severity.ERROR
    path: str = ""

    def __str__(self) -> str:
        where = f" {self.path}" if self.path else ""
        return f"[{self.rule}] {self.code}{where} : {self.message}"


def has_errors(issues: list[Issue]) -> bool:
    return any(i.severity is Severity.ERROR for i in issues)
