"""Ontologie pivot de l'extraction (X-016, voie A) : un schéma de genre complet, et sa correspondance sans modèle vers
le schéma du monde.

Le modèle répond dans le vocabulaire du schéma de genre (une énumération : il ne peut pas en sortir). Une table de
correspondance par schéma de monde ramène chaque relation à celle de l'auteur, en remontant la hiérarchie (`broader`) :
« mother_of » devient `parent_of` si le monde n'a que celle-ci, et la forme exacte est gardée pour le critique. Sans
correspondant, la relation est proposée hors schéma (R-SCH-06) : l'auteur décide. Le schéma du monde ne change pas
(R-SCH-03) ; la correspondance est déterministe (T-ARC-01).

Le schéma de genre est placé tel quel dans le prompt système, identique d'un appel à l'autre : c'est ce qui permet sa
mise en cache par l'API (seuil de 4 096 tokens pour Claude Haiku 4.5).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

HERE = Path(__file__).parent


@dataclass(frozen=True)
class PivotRelation:
    id: str
    from_: tuple[str, ...]
    to: tuple[str, ...]
    fr: str
    definition: str
    example: str
    symmetric: bool = False
    broader: str | None = None


@dataclass(frozen=True)
class Pivot:
    name: str
    version: int
    types: dict[str, str]
    relations: dict[str, PivotRelation]

    @property
    def signature(self) -> str:
        return f"{self.name}-{self.version}"

    def chain(self, relation: str) -> list[str]:
        """La relation puis ses relations plus générales (« mother_of », « parent_of », « kin_of »)."""
        out: list[str] = []
        current: str | None = relation
        while current is not None and current in self.relations and current not in out:
            out.append(current)
            current = self.relations[current].broader
        return out

    def compatible(self, from_type: str | None, to_type: str | None) -> list[str]:
        """Les relations dont les types conviennent à la paire (dans un sens ou dans l'autre)."""
        def fits(r: PivotRelation, a: str | None, b: str | None) -> bool:
            return a in r.from_ and b in r.to
        return [r.id for r in self.relations.values()
                if fits(r, from_type, to_type) or fits(r, to_type, from_type)]

    def render(self) -> str:
        """Texte stable du schéma de genre, pour le prompt système (même entrée, même texte : cache)."""
        lines = [f"Schéma de genre « {self.name} » (version {self.version}).", "", "Types :"]
        lines += [f"- {t} : {d}" for t, d in self.types.items()]
        lines += ["", "Relations (sujet → objet, sens canonique ; « ⊂ x » : cas particulier de x ; "
                      "« symétrique » : l'ordre ne compte pas) :"]
        for r in self.relations.values():
            marks = [f"{'|'.join(r.from_)} → {'|'.join(r.to)}"]
            if r.broader:
                marks.append(f"⊂ {r.broader}")
            if r.symmetric:
                marks.append("symétrique")
            lines.append(f"- {r.id} ({' ; '.join(marks)}) : {r.fr}. {r.definition[0].upper()}{r.definition[1:]}. "
                         f"Ex. {r.example}")
        return "\n".join(lines)


def _tuple(v: Any) -> tuple[str, ...]:
    return tuple(v) if isinstance(v, list) else (str(v),)


def load_pivot(name_or_path: str = "fantasy-jdr") -> Pivot:
    import yaml
    path = Path(name_or_path)
    if not path.suffix:
        path = HERE / f"{name_or_path}.yaml"
    d = yaml.safe_load(path.read_text(encoding="utf-8"))
    relations = {rid: PivotRelation(rid, _tuple(r["from"]), _tuple(r["to"]), r["fr"], r["def"], r["ex"],
                                    bool(r.get("symmetric", False)), r.get("broader"))
                 for rid, r in d["relations"].items()}
    return Pivot(d["pivot"], int(d["version"]), dict(d["types"]), relations)


@dataclass(frozen=True)
class PivotMap:
    """Correspondance d'un schéma de monde : types du monde → types du pivot ; relations du pivot → relations du monde."""

    pivot: Pivot
    schema: str
    types: dict[str, str]
    relations: dict[str, str] = field(default_factory=dict)

    def type_of(self, world_type: str) -> str | None:
        return self.types.get(world_type)

    def to_world(self, relation: str) -> tuple[str | None, str]:
        """(relation du monde ou None, relation exacte si la retenue est plus générale)."""
        for i, r in enumerate(self.pivot.chain(relation)):
            if r in self.relations:
                return self.relations[r], (relation if i else "")
        return None, ""


def load_map(path: str | Path, pivot: Pivot | None = None) -> PivotMap:
    import yaml
    d = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    pivot = pivot or load_pivot(d["pivot"])
    unknown = [r for r in d.get("relations", {}) if r not in pivot.relations]
    if unknown:
        raise ValueError(f"correspondance : relations inconnues du pivot {pivot.name} : {unknown}")
    return PivotMap(pivot, d["schema"], dict(d["types"]), dict(d.get("relations", {})))
