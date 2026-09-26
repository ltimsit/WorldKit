"""Éditions et état de base (M2 ; cadre de fondation §6.1–6.2, T-EDI-01, T-ING-01).

Format d'entrée : celui du corpus (`id`, `branch`, `origin`, `tags`, `changes`),
provisoire (README du corpus §3).
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from worldkit.core.schema import Change, Issue, IssueCode
from worldkit.core.schema.changes import DeleteEntity, SetDocumentObsolete

REFERENCE_BRANCH = "reference"


class Origin(StrEnum):
    """Étiquettes d'origine (§6.1, R-EDI-05)."""

    ENRICHMENT = "enrichment"
    SCENARIO_CONSEQUENCE = "scenario_consequence"
    ADOPTED_DRAFT = "adopted_draft"
    REDEFINITION = "redefinition"
    CORRECTION = "correction"
    CURATION = "curation"


class RedefinitionKind(StrEnum):
    POINT = "point"
    RETROACTIVE = "retroactive"


class EditStatus(StrEnum):
    """R-CYC-04."""

    PENDING = "pending"
    APPLIED = "applied"
    ABANDONED = "abandoned"


class Edit(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    branch: str = REFERENCE_BRANCH  # T-BRA-01 : présent partout dès J2
    origin: Origin
    redefinition: RedefinitionKind | None = None
    tags: list[str] = Field(default_factory=list)
    derived_from: str | None = None  # R-EDI-08
    note: str | None = None  # commentaire d'auteur, sans effet
    changes: list[Change]


class BaseState(BaseModel):
    """État contre lequel une édition en attente est écrite (T-ING-01) : `(branch_id, seq, schema_rev)`."""

    model_config = ConfigDict(frozen=True)

    branch: str
    seq: int
    schema_rev: int


def edit_rule_issues(edit: Edit) -> list[Issue]:
    """Règles propres à l'édition, indépendantes de l'état (R-EDI-07, R-EDI-09)."""
    issues: list[Issue] = []
    if edit.origin is not Origin.CORRECTION and any(isinstance(c, DeleteEntity) for c in edit.changes):
        issues.append(Issue(IssueCode.EDIT_RULE,
                            "delete_entity n'est permise que dans une édition d'origine correction", "R-EDI-07"))
    curating = [isinstance(c, SetDocumentObsolete) for c in edit.changes]
    if edit.origin is Origin.CURATION and not all(curating):
        issues.append(Issue(IssueCode.EDIT_RULE,
                            "une édition curation ne contient que des set_document_obsolete", "R-EDI-09"))
    if edit.origin is not Origin.CURATION and any(curating):
        issues.append(Issue(IssueCode.EDIT_RULE,
                            "set_document_obsolete n'apparaît que dans une édition curation", "R-EDI-09"))
    if (edit.origin is Origin.REDEFINITION) != (edit.redefinition is not None):
        issues.append(Issue(IssueCode.EDIT_RULE,
                            "une redéfinition précise « redefinition: point | retroactive », et elle seule", "R-EDI-05"))
    return issues


def parse_edit(raw: Any) -> Edit:
    return Edit.model_validate(raw)
