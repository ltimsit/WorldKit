"""Méta-schéma unique (T-SCH-01, R-SCH-01, R-SCH-02).

Ce qu'un schéma YAML — de monde ou de système de règles — peut déclarer.
Les modèles fixent la **forme** ; les contrôles croisés (références déclarées,
types noyau, héritage…) sont dans `validate.py`.
"""

from __future__ import annotations

import re
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator, model_validator


class StrictModel(BaseModel):
    # Clé inconnue = erreur : une faute de frappe (« cardinalty ») ne doit pas
    # retomber silencieusement sur une valeur par défaut.
    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)


class SchemaKind(StrEnum):
    WORLD = "world"
    RULE_SYSTEM = "rule_system"


class Cardinality(StrEnum):
    """Se lit de `from` vers `to` (R-SCH-01)."""

    ONE_TO_ONE = "one_to_one"
    ONE_TO_MANY = "one_to_many"
    MANY_TO_ONE = "many_to_one"
    MANY_TO_MANY = "many_to_many"


class ScalarKind(StrEnum):
    TEXT = "text"
    INTEGER = "integer"
    BOOLEAN = "boolean"
    REF = "ref"


_IDENT = r"[A-Za-z_][A-Za-z0-9_]*"
_REF_RE = re.compile(rf"ref\[({_IDENT})\]")
_LIST_RE = re.compile(r"list\[(.+)\]")


class AttrType(StrictModel):
    """Type d'attribut analysé : `text | integer | boolean | ref[T]`, éventuellement dans `list[...]`."""

    kind: ScalarKind
    is_list: bool = False
    ref_target: str | None = None

    @classmethod
    def parse(cls, text: str) -> AttrType:
        s = text.strip()
        is_list = False
        m = _LIST_RE.fullmatch(s)
        if m:
            is_list, s = True, m.group(1).strip()
        m = _REF_RE.fullmatch(s)
        if m:
            return cls(kind=ScalarKind.REF, is_list=is_list, ref_target=m.group(1))
        if s in (ScalarKind.TEXT, ScalarKind.INTEGER, ScalarKind.BOOLEAN):
            return cls(kind=ScalarKind(s), is_list=is_list)
        raise ValueError(
            f"type d'attribut « {text} » hors grammaire : attendu text, integer, boolean, "
            "ref[Type], ou list[…] de l'un d'eux"
        )

    def __str__(self) -> str:
        inner = f"ref[{self.ref_target}]" if self.kind is ScalarKind.REF else str(self.kind)
        return f"list[{inner}]" if self.is_list else inner


class AttributeDef(StrictModel):
    type: AttrType
    required: bool = False
    min: int | None = None
    max: int | None = None
    labels: dict[str, str] = Field(default_factory=dict)  # préparé (R-SCH-08)

    @field_validator("type", mode="before")
    @classmethod
    def _parse_type(cls, v: Any) -> Any:
        return AttrType.parse(v) if isinstance(v, str) else v

    @field_serializer("type")
    def _type_as_text(self, t: AttrType) -> str:
        return str(t)

    @model_validator(mode="after")
    def _check_bounds(self) -> AttributeDef:
        if (self.min is not None or self.max is not None) and self.type.kind is not ScalarKind.INTEGER:
            raise ValueError("bornes min/max permises seulement sur un attribut integer")
        if self.min is not None and self.max is not None and self.min > self.max:
            raise ValueError(f"bornes incohérentes : min ({self.min}) > max ({self.max})")
        return self


class TypeDef(StrictModel):
    extends: str | None = None
    attributes: dict[str, AttributeDef] = Field(default_factory=dict)
    labels: dict[str, str] = Field(default_factory=dict)  # préparé (R-SCH-08)


def _as_list(v: Any) -> Any:
    """`from: Place` équivaut à `from: [Place]`."""
    return [v] if isinstance(v, str) else v


class RelationDef(StrictModel):
    from_: list[str] = Field(alias="from", min_length=1)
    to: list[str] = Field(min_length=1)
    cardinality: Cardinality = Cardinality.MANY_TO_MANY
    symmetric: bool = False
    labels: dict[str, str] = Field(default_factory=dict)  # préparé (R-SCH-08)

    @field_validator("from_", "to", mode="before")
    @classmethod
    def _one_or_many(cls, v: Any) -> Any:
        return _as_list(v)


class Schema(StrictModel):
    """Schéma de monde ou de système de règles : même langage (R-SCH-02)."""

    id: str = Field(alias="schema")
    version: int = 1
    kind: SchemaKind = SchemaKind.WORLD
    copied_from: str | None = None
    types: dict[str, TypeDef] = Field(default_factory=dict)
    relations: dict[str, RelationDef] = Field(default_factory=dict)

    # --- Lecture (suppose un schéma validé : pas de cycle d'héritage) ---

    def ancestors(self, type_name: str) -> list[str]:
        """Le type puis ses parents successifs (`extends`)."""
        chain: list[str] = []
        current: str | None = type_name
        while current is not None and current in self.types and current not in chain:
            chain.append(current)
            current = self.types[current].extends
        return chain

    def is_subtype(self, type_name: str, parent: str) -> bool:
        return parent in self.ancestors(type_name)

    def attributes_of(self, type_name: str) -> dict[str, AttributeDef]:
        """Attributs propres et hérités."""
        merged: dict[str, AttributeDef] = {}
        for t in reversed(self.ancestors(type_name)):
            merged.update(self.types[t].attributes)
        return merged

    # --- Modifications (R-SCH-03) : rendent un nouveau schéma, sans toucher l'original ---

    def with_type(self, name: str, definition: TypeDef) -> Schema:
        return self.model_copy(update={"types": {**self.types, name: definition}})

    def without_type(self, name: str) -> Schema:
        return self.model_copy(update={"types": {k: v for k, v in self.types.items() if k != name}})

    def with_relation(self, name: str, definition: RelationDef) -> Schema:
        return self.model_copy(update={"relations": {**self.relations, name: definition}})

    def without_relation(self, name: str) -> Schema:
        return self.model_copy(update={"relations": {k: v for k, v in self.relations.items() if k != name}})
