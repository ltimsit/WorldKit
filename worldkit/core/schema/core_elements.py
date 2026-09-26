"""Types et relations noyau (cadre de fondation §4.4, R-NOY-01, R-NOY-02).

Fournis par la plateforme, non configurables : aucun schéma ne peut les déclarer.
"""

from __future__ import annotations

from .metaschema import Cardinality

CORE_TYPES: frozenset[str] = frozenset({
    "Document", "Batch", "Claim", "Edit", "Draft", "Proposal",
    "Scenario", "ScenarioVersion", "Playthrough", "Sheet",
})

# Seul type noyau créé par `create_entity` en J1 : la fiche (format provisoire, lacune L2).
SHEET_TYPE = "Sheet"

# Cardinalité et symétrie des relations noyau, utilisées pour le calcul des clés (R-FAI-05).
# `counterpart_of` est provisoire : lien entre les deux nœuds d'un élément à double face
# (R-MET-04), nom et cardinalité à fixer avec la lacune L1.
CORE_RELATIONS: dict[str, tuple[Cardinality, bool]] = {
    "concerns": (Cardinality.MANY_TO_MANY, False),
    "asserts": (Cardinality.MANY_TO_MANY, False),
    "has_sheet": (Cardinality.ONE_TO_MANY, False),
    "conforms_to": (Cardinality.MANY_TO_ONE, False),
    "same_as": (Cardinality.MANY_TO_MANY, True),
    "counterpart_of": (Cardinality.MANY_TO_MANY, False),
}

PROVISIONAL_CORE_RELATIONS: frozenset[str] = frozenset({"counterpart_of"})

SAME_AS_KINDS: frozenset[str] = frozenset({"revelation", "duplicate"})  # R-IDT-02
