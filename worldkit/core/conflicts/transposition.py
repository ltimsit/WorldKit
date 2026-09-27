"""Transposition d'une édition appliquée sur une autre branche (R-HIS-05, R-EDI-02 ; cadre de fondation §6.3).

L'édition est confrontée à un état autre que celui contre lequel elle a été écrite. Le noyau compare,
clé par clé, l'état qu'elle **supposait** (sa branche d'origine juste avant elle) à la tête de la cible :

| Relation (§6.3) | Condition | Transposition |
|---|---|---|
| indépendante | rien de ce qu'elle lit ou écrit n'a divergé | automatique |
| dépendante | elle lit un fait (ou une entité) absent de la cible | conflit : non applicable en l'état |
| contradictoire | la cible occupe une clé lue ou écrite par une autre valeur | décision humaine |

Décisions humaines : **garder** (appliquer quand même, les faits occupants retirés explicitement),
**adapter** (d'autres changements), **écarter** (tracé, rien n'est appliqué). Conflits de la famille
`history` (R-CON-04).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from worldkit.core.projection.state import State
from worldkit.core.schema import FactKey
from worldkit.core.schema.keys import format_key


@dataclass(frozen=True)
class Divergence:
    key: FactKey
    kind: str             # "missing" (dépendance absente) | "different" (contradiction)
    assumed: Any          # fait supposé par l'édition (identifiant, ou valeur d'attribut)
    found: Any            # ce que la cible contient
    written: bool = True  # l'édition écrit la clé (sinon elle ne fait que la lire)

    def describe(self) -> str:
        if self.kind == "missing":
            return f"{format_key(self.key)} : supposé {self.assumed}, absent de la branche cible"
        return f"{format_key(self.key)} : supposé {self.assumed}, la branche cible a {self.found}"


@dataclass
class Analysis:
    edit_id: str
    source: str
    source_seq: int
    target: str
    divergences: list[Divergence] = field(default_factory=list)

    @property
    def missing(self) -> list[Divergence]:
        return [d for d in self.divergences if d.kind == "missing"]

    @property
    def contradictions(self) -> list[Divergence]:
        return [d for d in self.divergences if d.kind == "different"]

    @property
    def relation(self) -> str:
        if self.missing:
            return "dependent"
        return "contradictory" if self.contradictions else "independent"


def keep_changes(analysis: Analysis, changes: list[Any], head: State) -> tuple[list[Any], int]:
    """Garder malgré une contradiction : retirer explicitement chaque fait qui occupe une clé visée
    (R-FAI-05) — une clé seulement lue n'est pas touchée ; abandonner les retraits devenus sans objet sur
    la cible (le fait n'y existe pas),
    puisque libérer la clé est l'affaire du retrait de l'occupant réel. Rend (changements, abandonnés)."""
    from worldkit.core.projection.state import fact_id_of
    from worldkit.core.schema.changes import RemoveRelation
    removals: list[Any] = []
    for d in analysis.contradictions:
        if not d.written:
            continue  # clé seulement lue : garder l'édition ne touche pas au fait de la cible
        fid = head.occupancy.get(d.key)
        fact = head.facts.get(fid) if fid is not None else None
        if fact is not None and fact.kind == "rel":
            removal = RemoveRelation(op="remove_relation", scope=fact.scope, **{"from": fact.subject},
                                     relation=fact.name, to=fact.target or "")
            if removal not in removals:
                removals.append(removal)
    ctx = head.context()
    dropped = [c for c in changes if c.op in ("remove_relation", "unset_attribute", "remove_value")
               and fact_id_of(c, ctx) not in head.facts]
    return removals + [c for c in changes if c not in dropped], len(dropped)


def _value(state: State, key: FactKey) -> Any:
    """Ce qu'une clé désigne dans un état : l'identifiant du fait, et sa valeur pour un attribut."""
    fid = state.occupancy.get(key)
    if fid is None:
        return None
    fact = state.facts.get(fid)
    if fact is not None and fact.kind == "attr":
        return (fid, fact.value)
    return fid


def analyse(edit_id: str, source: str, source_seq: int, before: State, after: State, target_name: str,
            target: State, reads: frozenset[FactKey], writes: frozenset[FactKey]) -> Analysis:
    """`before` / `after` : branche d'origine juste avant / juste après l'édition ; `target` : tête de la cible."""
    out = Analysis(edit_id, source, source_seq, target_name)
    unwrap = {k[1] if k[0] == "visibility" else k for k in reads | writes}  # sous-clé de notoriété → sa clé
    reads = frozenset(k[1] if k[0] == "visibility" else k for k in reads)
    writes = frozenset(k[1] if k[0] == "visibility" else k for k in writes)
    for key in sorted(unwrap, key=repr):
        assumed, found = _value(before, key), _value(target, key)
        if assumed == found or (key in writes and found is not None and found == _value(after, key)):
            continue  # rien n'a divergé, ou la cible contient déjà ce que l'édition écrit
        if key in reads and assumed is not None and found is None:
            out.divergences.append(Divergence(key, "missing", assumed, found))
        elif found is not None:
            out.divergences.append(Divergence(key, "different", assumed, found, key in writes))
    return out
