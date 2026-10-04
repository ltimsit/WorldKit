"""« Proposer » (I8, T5 ; Q3) : les décisions de l'auteur sur une source deviennent un lot, par le circuit existant.

Ce qui part : les entités nouvelles **confirmées par l'auteur** (gardées, corrigées en « nouvelle », ajoutées), en
`create_entity` et `name` ; les alias **retenus au monde** (une forme rattachée à une entité connue dont elle n'est pas
encore un nom), en `add_value aliases`. Ce qui ne part pas : les propositions des couches que l'auteur n'a pas
touchées, les doutes, les mentions retirées ou ignorées. Le lot passe par les étapes E1 à E9+ (qualification,
regroupement des créations, file de revue), sans modèle : l'extracteur d'atelier rend les brouillons tirés des
annotations, passage par passage (provenance, T-ING-11).

Limite de ce premier incrément : une version de source ne se propose qu'une fois (un passage déjà ingéré n'est pas
reproposé, T-ING-10) ; corriger après coup passe par une nouvelle version de la source.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from . import layers, store


@dataclass(frozen=True)
class SourceText:
    """Une source d'atelier présentée à l'étape E1 comme un document (chemin et texte)."""

    path: str
    text: str


@dataclass
class AtelierExtractor:
    """Rend, pour chaque passage de la source, les brouillons tirés des annotations confirmées."""

    drafts: dict[str, list[dict[str, Any]]]  # texte du passage → brouillons
    version: str = "atelier"

    def extract(self, doc_id: str, passage_text: str, context: Any = None) -> Any:
        from worldkit.periphery.extraction import Extraction
        return Extraction(tuple(self.drafts.get(passage_text, [])))


def drafts_of(world: Any, branch: str, doc: Any) -> dict[int, list[dict[str, Any]]]:
    """Brouillons par passage : créations des entités nouvelles confirmées, alias retenus au monde."""
    from worldkit.ingest.batch import extraction_context
    from worldkit.ingest.declaration import name_key
    from worldkit.periphery.matching import fold
    context = extraction_context(world, world.state(branch))
    names = {e.id: {fold(n) for n in e.names} for e in context.entities}
    out: dict[int, list[dict[str, Any]]] = {}
    created: set[str] = set()
    for a in sorted(layers.effective(world, branch, doc), key=lambda a: (a.passage or 0, a.start or 0)):
        if not a.by_author or a.kind != "mention" or a.status not in ("kept", "corrected") or a.passage is None:
            continue
        v = a.value
        entity = v.get("entity")
        if v.get("new") or (entity or "").startswith("new:"):
            label = (entity or "").split(":", 1)[1] if (entity or "").startswith("new:") else name_key(v["text"])
            label = label.replace(" ", "-")
            if label not in created and v.get("type"):
                created.add(label)
                out.setdefault(a.passage, []).extend([
                    {"op": "create_entity", "entity": f"new:{label}", "type": v["type"]},
                    {"op": "set_attribute", "entity": f"new:{label}", "attribute": "name", "value": v["text"]}])
        elif entity and v.get("retained") and fold(v["text"]) not in names.get(entity, set()):
            out.setdefault(a.passage, []).append(
                {"op": "add_value", "entity": entity, "attribute": "aliases", "value": v["text"]})
            names.setdefault(entity, set()).add(fold(v["text"]))
    return out


def propose(world: Any, branch: str, doc_id: str) -> Any:
    """Crée le lot de la source et l'enregistre (E1 à E9+) ; rend le compte rendu du lot."""
    from worldkit.ingest.batch import BatchError, ingest
    doc = store.source(world, doc_id)
    by_passage = drafts_of(world, branch, doc)
    if not by_passage:
        raise BatchError("rien à proposer : aucune entité nouvelle confirmée, aucun alias retenu")
    texts = {p.index: p.text for p in doc.passages}
    drafts = {texts[i]: d for i, d in by_passage.items()}
    digest = hashlib.sha256(json.dumps(drafts, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:8]
    row = world.store.conn.execute("SELECT text FROM atelier_sources WHERE doc_id = ? AND version_fp = ?",
                                   (doc.doc_id, doc.fingerprint)).fetchone()
    batch_id = f"atelier-{doc.doc_id}-{doc.fingerprint[:8]}"
    return ingest(world, batch_id, [SourceText(f"atelier:{doc.doc_id}", row[0])],
                  AtelierExtractor(drafts, f"atelier:{digest}"), branch)
