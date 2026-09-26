"""Changements élémentaires : catalogue fermé d'opérations (cadre de fondation §6.1, R-EDI-06).

Format provisoire, celui du corpus Valmont (README §3). Les champs préparés
(`diegetic_window`, `authority`, `labels` — invariant 10, R-FAI-03) sont acceptés,
conservés et ignorés ; toute autre clé inconnue est refusée.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError, field_validator, model_validator

from .issues import Issue, IssueCode
from .metaschema import AttributeDef, RelationDef, TypeDef

WORLD_SCOPE = "world"
Scalar = Union[bool, int, str]  # bool d'abord : pydantic ne doit pas convertir True en 1


class Visibility(StrEnum):
    """R-NOT-01 ; absente = `unqualified`."""

    SECRET = "secret"
    PUBLIC = "public"
    UNQUALIFIED = "unqualified"


class _Change(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)

    scope: str = WORLD_SCOPE
    visibility: Visibility | None = None
    # Champs préparés : conservés, sans effet en fondation (invariant 10).
    diegetic_window: Any = None
    authority: Any = None
    labels: dict[str, str] | None = None


# --- Entités ---

class SheetBinding(BaseModel):
    """Format provisoire d'une fiche (lacune L2) : `sheet: {of, system, category}`."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    of: str
    system: str
    category: str


class CreateEntity(_Change):
    op: Literal["create_entity"]
    entity: str
    type: str
    sheet: SheetBinding | None = None


class CloseEntity(_Change):
    op: Literal["close_entity"]
    entity: str


class DeleteEntity(_Change):
    op: Literal["delete_entity"]
    entity: str


# --- Faits ---

class SetAttribute(_Change):
    op: Literal["set_attribute"]
    entity: str
    attribute: str
    value: Scalar


class UnsetAttribute(_Change):
    op: Literal["unset_attribute"]
    entity: str
    attribute: str


class AddValue(_Change):
    op: Literal["add_value"]
    entity: str
    attribute: str
    value: Scalar


class RemoveValue(_Change):
    op: Literal["remove_value"]
    entity: str
    attribute: str
    value: Scalar


class AddRelation(_Change):
    op: Literal["add_relation"]
    from_: str = Field(alias="from")
    relation: str
    to: str
    kind: str | None = None  # qualification de same_as (R-IDT-02)


class RemoveRelation(_Change):
    op: Literal["remove_relation"]
    from_: str = Field(alias="from")
    relation: str
    to: str


class FactTarget(BaseModel):
    """Désignation d'un fait existant : entité, attribut (et valeur), ou relation."""

    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)
    entity: str | None = None
    attribute: str | None = None
    value: Scalar | None = None
    from_: str | None = Field(default=None, alias="from")
    relation: str | None = None
    to: str | None = None

    @classmethod
    def parse(cls, target: Any) -> FactTarget:
        """Accepte aussi la forme textuelle du corpus : « a relation b », « entité.attribut », « entité »."""
        if not isinstance(target, str):
            return cls.model_validate(target)
        parts = target.split()
        if len(parts) == 3:
            return cls(from_=parts[0], relation=parts[1], to=parts[2])
        if len(parts) == 1 and "." in target:
            entity, attribute = target.split(".", 1)
            return cls(entity=entity, attribute=attribute)
        if len(parts) == 1:
            return cls(entity=target)
        raise ValueError(f"désignation de fait illisible : « {target} »")


class SetVisibility(_Change):
    op: Literal["set_visibility"]
    target: FactTarget
    value: Visibility

    @field_validator("target", mode="before")
    @classmethod
    def _parse_target(cls, v: Any) -> Any:
        return v if isinstance(v, FactTarget) else FactTarget.parse(v)


# --- Affirmations et documents ---

class AddClaim(_Change):
    op: Literal["add_claim"]
    claim: str
    document: str | None = None
    claimed: Any = None


class QualifyClaim(_Change):
    op: Literal["qualify_claim"]
    claim: str
    value: str


class SetDocumentObsolete(_Change):
    op: Literal["set_document_obsolete"]
    document: str
    value: bool


# --- Schémas (R-SCH-03 ; `scope` désigne le monde ou un système, R-SCH-02) ---

class ConstraintPatch(BaseModel):
    """Forme provisoire du corpus : modifier les contraintes d'un attribut existant."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    required: bool | None = None
    min: int | None = None
    max: int | None = None


class SchemaSetType(_Change):
    op: Literal["schema_set_type"]
    type: str
    attribute: str | None = None
    definition: TypeDef | AttributeDef | None = None
    constraint: ConstraintPatch | None = None

    @model_validator(mode="after")
    def _one_form(self) -> SchemaSetType:
        """Trois formes : type entier (`definition`), attribut entier (`attribute` + `definition`),
        contraintes d'un attribut (`attribute` + `constraint`, forme du corpus)."""
        if self.attribute is None:
            if not isinstance(self.definition, TypeDef) or self.constraint is not None:
                raise ValueError("sans « attribute », attendu une « definition » de type")
        elif (self.definition is None) == (self.constraint is None) or isinstance(self.definition, TypeDef):
            raise ValueError("avec « attribute », attendu soit une « definition » d'attribut, soit une « constraint »")
        return self


class SchemaRemoveType(_Change):
    op: Literal["schema_remove_type"]
    type: str


class SchemaSetRelation(_Change):
    op: Literal["schema_set_relation"]
    relation: str
    definition: RelationDef


class SchemaRemoveRelation(_Change):
    op: Literal["schema_remove_relation"]
    relation: str


Change = Annotated[
    Union[
        CreateEntity, CloseEntity, DeleteEntity,
        SetAttribute, UnsetAttribute, AddValue, RemoveValue,
        AddRelation, RemoveRelation, SetVisibility,
        AddClaim, QualifyClaim, SetDocumentObsolete,
        SchemaSetType, SchemaRemoveType, SchemaSetRelation, SchemaRemoveRelation,
    ],
    Field(discriminator="op"),
]

SCHEMA_OPS = (SchemaSetType, SchemaRemoveType, SchemaSetRelation, SchemaRemoveRelation)

_ADAPTER: TypeAdapter[Any] = TypeAdapter(Change)


def parse_change(raw: Any) -> Change:
    """Lève `ValueError` (dont `ValidationError`) si le changement est malformé."""
    return _ADAPTER.validate_python(raw)


def parse_changes(raws: list[Any]) -> tuple[list[Change], list[Issue]]:
    """Analyse une liste de changements ; un changement malformé devient un signalement (R-EDI-06)."""
    changes: list[Change] = []
    issues: list[Issue] = []
    for index, raw in enumerate(raws):
        try:
            changes.append(parse_change(raw))
        except (ValidationError, ValueError) as e:
            detail = "; ".join(
                f"{'.'.join(str(p) for p in err['loc'])} : {err['msg']}" for err in e.errors()
            ) if isinstance(e, ValidationError) else str(e)
            issues.append(Issue(
                IssueCode.MALFORMED_CHANGE,
                f"changement hors du catalogue d'opérations ou mal formé ({detail})",
                "R-EDI-06", path=f"changes[{index}]",
            ))
    return changes, issues
