"""Types et relations noyau (cadre de fondation §4.4, R-NOY-01, R-NOY-02).

Fournis par la plateforme, non configurables : aucun schéma ne peut les déclarer.
"""

from __future__ import annotations

from .metaschema import Cardinality

CORE_TYPES: frozenset[str] = frozenset({
    "Document", "Batch", "Claim", "Edit", "Draft", "Proposal",
    "Scenario", "ScenarioVersion", "Playthrough", "Sheet",
})

# Seul type noyau créé par `create_entity` : la fiche, qui porte son rattachement immuable
# `sheet: {of, system, category}` (R-MET-01, R-MET-02 ; lacune L2 tranchée).
SHEET_TYPE = "Sheet"

# Cardinalité et symétrie des relations noyau, utilisées pour le calcul des clés (R-FAI-05).
# `counterpart_of` relie un élément du monde à sa face dans un système (R-MET-04) ; sa clé est
# propre : au plus une contrepartie par système (keys.py ; lacune L1 tranchée).
CORE_RELATIONS: dict[str, tuple[Cardinality, bool]] = {
    "concerns": (Cardinality.MANY_TO_MANY, False),
    "asserts": (Cardinality.MANY_TO_MANY, False),
    "has_sheet": (Cardinality.ONE_TO_MANY, False),
    "conforms_to": (Cardinality.MANY_TO_ONE, False),
    "same_as": (Cardinality.MANY_TO_MANY, True),
    "counterpart_of": (Cardinality.MANY_TO_MANY, False),
}

COUNTERPART = "counterpart_of"

# Relations calculées à partir du rattachement d'une fiche (lacune L2) : exposées par les vues et
# l'export, jamais écrites par une édition.
COMPUTED_CORE_RELATIONS: frozenset[str] = frozenset({"has_sheet", "conforms_to"})

SAME_AS_KINDS: frozenset[str] = frozenset({"revelation", "duplicate"})  # R-IDT-02
