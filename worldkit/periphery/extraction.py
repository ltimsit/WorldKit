"""Frontière d'extraction (T-LLM-01) et extracteur oracle (T-ING-19).

`extract(document, passage) → Extraction` : brouillons de changements (`ChangeDraft`, forme brute
d'un changement dont les entités nouvelles sont des références `new:étiquette`), affirmations,
et indices sur le passage. La périphérie ne décide rien : le noyau qualifie (T-ARC-02, T-ARC-03).

L'oracle lit les annotations `gold/` et n'en transmet QUE ce qu'un extracteur produirait :
les conclusions attendues du noyau (`outcome`, `collides_with`…) sont retirées, pour que les
tests prouvent que le noyau les retrouve seul.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

import yaml

# Annotations du gold qui décrivent la conclusion attendue, pas l'extraction.
_EXPECTATIONS = {"outcome", "note", "collides_with", "conflicts_with", "competes_with", "depends_on",
                 "internal_contradiction", "same_value_as", "same_fingerprint_as", "diff", "hint"}


@dataclass(frozen=True)
class Extraction:
    drafts: tuple[dict[str, Any], ...] = ()
    optional: frozenset[int] = frozenset()   # indices des brouillons marqués facultatifs
    claims: tuple[dict[str, Any], ...] = ()  # J3.3
    flags: tuple[str, ...] = ()              # ex. "attribution" (R-DEC-03)
    nature: str | None = None                # nature détectée du passage (R-DEC-02 : proposée)


@dataclass(frozen=True)
class KnownEntity:
    id: str
    type: str
    names: tuple[str, ...]  # nom, puis autres noms (aliases)


@dataclass(frozen=True)
class ExtractionContext:
    """Ce que l'extracteur voit de l'état de base du lot. Ce n'est pas une lecture au sens des
    dépendances (T-ING-02) : le contexte fourni au LLM ne rend pas les propositions dépendantes."""

    schema: Any
    entities: tuple[KnownEntity, ...] = ()
    voice: str = "author"
    speaker: str | None = None
    systems: dict[str, Any] = field(default_factory=dict)  # systèmes de règles (J8)
    document: str | None = None                             # titre du document : sujet par défaut (J8)


class Extractor(Protocol):
    version: str

    def extract(self, doc_id: str, passage_text: str, context: ExtractionContext | None = None) -> Extraction: ...


@dataclass
class OracleExtractor:
    gold_dir: Path
    version: str = "oracle-1"
    _index: dict[str, list[dict[str, Any]]] = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        for path in sorted(Path(self.gold_dir).glob("*.yaml")):
            doc = yaml.safe_load(path.read_text(encoding="utf-8"))
            for passage in doc.get("passages", []):
                self._index.setdefault(doc["document"], []).append(passage)

    def extract(self, doc_id: str, passage_text: str, context: ExtractionContext | None = None) -> Extraction:
        # Le passage annoté le plus spécifique (préfixe le plus long) : « régent par intérim »
        # (v2) l'emporte sur « régent » (v1) quand les deux préfixes conviennent.
        matches = [p for p in self._index.get(doc_id, []) if passage_text.startswith(p["starts_with"])]
        if not matches:
            return Extraction()
        gold = max(matches, key=lambda p: len(p["starts_with"]))
        # Un passage annoté par segments (marqueurs) : on aplatit, l'énonciateur restant attaché.
        parts = gold.get("segments") or [gold]
        drafts, optional, claims = [], set(), []
        for part in parts:
            for change in part.get("changes") or []:
                if change.get("optional"):
                    optional.add(len(drafts))
                drafts.append({k: v for k, v in change.items() if k not in _EXPECTATIONS and k != "optional"})
            for claim in part.get("claims") or []:
                claims.append({"text": claim["text"], "claimed": claim.get("claimed"),
                               "speaker": part.get("speaker")})  # « suggested » : conclusion du noyau, retirée
        flags = ("attribution",) if gold.get("outcome") == "attribution" else ()
        return Extraction(tuple(drafts), frozenset(optional), tuple(claims), flags, gold.get("nature"))
