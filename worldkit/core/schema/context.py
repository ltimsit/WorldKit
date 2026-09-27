"""Contexte de vérification : schémas de l'état visé et entités connues.

Objet pur et immuable. En J1, l'appelant le construit ; à partir de J2, il sera
tiré de la projection d'un état. Les éléments d'un système sont adressés
`système:élément` (ex. `system-a:bite`) ; une fiche, `entité@système` (R-MET-02).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, replace

from .changes import WORLD_SCOPE, SheetBinding
from .metaschema import Schema


def qualify(entity: str, scope: str) -> str:
    """Identifiant canonique d'une entité citée dans un changement de portée `scope`."""
    if scope == WORLD_SCOPE or ":" in entity:
        return entity
    return f"{scope}:{entity}"


@dataclass(frozen=True)
class EntityInfo:
    id: str
    type: str
    scope: str = WORLD_SCOPE
    sheet: SheetBinding | None = None


@dataclass(frozen=True)
class SchemaContext:
    world: Schema
    systems: Mapping[str, Schema] = field(default_factory=dict)
    entities: Mapping[str, EntityInfo] = field(default_factory=dict)
    # Fiches exigées (R-MET-06), déclarées par le monde : système → {type du monde → catégorie}.
    sheet_requirements: Mapping[str, Mapping[str, str]] = field(default_factory=dict)

    def schema_for(self, scope: str) -> Schema | None:
        return self.world if scope == WORLD_SCOPE else self.systems.get(scope)

    def with_schema(self, scope: str, schema: Schema) -> SchemaContext:
        if scope == WORLD_SCOPE:
            return replace(self, world=schema)
        return replace(self, systems={**self.systems, scope: schema})

    def with_entity(self, info: EntityInfo) -> SchemaContext:
        return replace(self, entities={**self.entities, info.id: info})

    def without_entity(self, entity_id: str) -> SchemaContext:
        return replace(self, entities={k: v for k, v in self.entities.items() if k != entity_id})

    def owner(self, info: EntityInfo) -> tuple[str, Schema, str] | None:
        """Portée, schéma et type qui définissent les attributs d'une entité.

        Une fiche prend les attributs de sa catégorie dans son système (R-MET-01).
        """
        if info.sheet is not None:
            schema = self.systems.get(info.sheet.system)
            return (info.sheet.system, schema, info.sheet.category) if schema else None
        schema = self.schema_for(info.scope)
        return (info.scope, schema, info.type) if schema else None
