"""« Proposer » (I8, T5 ; Q3) : les décisions de l'auteur sur une source deviennent un lot, par le circuit existant.

Ce qui part : les entités nouvelles **confirmées par l'auteur** (gardées, corrigées en « nouvelle » ou vers une
entité nouvelle de la source, ajoutées), en `create_entity` et `name` ; les alias **retenus au monde** (une forme
rattachée à une entité, connue ou nouvelle de la source, dont elle n'est pas encore un nom), en `add_value aliases`. Ce
qui ne part pas : les propositions des couches que l'auteur n'a pas touchées, les doutes, les mentions retirées ou ignorées. Le lot passe par les étapes E1 à E9+ (qualification,
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


def _label(value: dict[str, Any]) -> str | None:
    """Étiquette d'entité nouvelle d'une mention (« new:bertrand ostrel » ou nouvelle sans étiquette : son texte)."""
    from worldkit.ingest.declaration import name_key
    entity = value.get("entity") or ""
    if entity.startswith("new:"):
        return entity[len("new:"):].replace(" ", "-")
    return name_key(value["text"]).replace(" ", "-") if value.get("new") else None


def new_entities(world: Any, branch: str, doc: Any) -> dict[str, dict[str, Any]]:
    """Entités nouvelles de la source (groupes des couches, créations de l'auteur) : étiquette → nom, type, formes,
    passage du nom. Le nom est la forme qui donne l'étiquette (« Bertrand Ostrel »), sinon la plus longue ; c'est à
    l'une d'elles que l'auteur rattache une autre forme (« Ostrel »)."""
    from worldkit.ingest.declaration import name_key
    out: dict[str, dict[str, Any]] = {}
    for a in sorted(layers.effective(world, branch, doc), key=lambda a: (a.passage or 0, a.start or 0)):
        if a.kind != "mention" or a.status in ("removed", "ignored") or a.passage is None:
            continue
        label = _label(a.value)
        if label is None:
            continue
        e = out.setdefault(label, {"id": f"new:{label}", "label": label, "type": None, "forms": {}})
        e["type"] = e["type"] or a.value.get("type")
        e["forms"].setdefault(a.value["text"], a.passage)
    for label, e in out.items():
        e["name"] = next((f for f in e["forms"] if name_key(f).replace(" ", "-") == label),
                         max(e["forms"], key=len))
        e["passage"] = e["forms"][e["name"]]
    return out


def drafts_of(world: Any, branch: str, doc: Any) -> dict[int, list[dict[str, Any]]]:
    """Brouillons par passage : créations des entités nouvelles confirmées, alias retenus au monde.

    Une entité nouvelle est créée une fois, sous le nom de son groupe, au passage où ce nom apparaît ; une autre forme
    que l'auteur y rattache et retient pour le monde (« Ostrel » pour Bertrand Ostrel) part en alias, comme pour une
    entité connue (Q4)."""
    from worldkit.ingest.batch import extraction_context
    from worldkit.periphery.matching import fold
    context = extraction_context(world, world.state(branch))
    names = {e.id: {fold(n) for n in e.names} for e in context.entities}
    groups = new_entities(world, branch, doc)
    out: dict[int, list[dict[str, Any]]] = {}
    created: dict[str, set[str]] = {}  # étiquette → formes pliées déjà nommées
    confirmed = [a for a in sorted(layers.effective(world, branch, doc), key=lambda a: (a.passage or 0, a.start or 0))
                 if a.by_author and a.kind == "mention" and a.status in ("kept", "corrected") and a.passage is not None]
    for a in confirmed:
        v = a.value
        label = _label(v)
        if label is not None and label not in created:
            group = groups.get(label) or {"name": v["text"], "type": v.get("type"), "passage": a.passage}
            type_ = v.get("type") or group["type"]
            if type_:
                created[label] = {fold(group["name"])}
                out.setdefault(group["passage"], []).extend([
                    {"op": "create_entity", "entity": f"new:{label}", "type": type_},
                    {"op": "set_attribute", "entity": f"new:{label}", "attribute": "name", "value": group["name"]}])
    for a in confirmed:
        v = a.value
        label = _label(v)
        if label is not None:
            if label in created and v.get("retained") and fold(v["text"]) not in created[label]:
                out.setdefault(a.passage, []).append(
                    {"op": "add_value", "entity": f"new:{label}", "attribute": "aliases", "value": v["text"]})
                created[label].add(fold(v["text"]))
        elif (entity := v.get("entity")) and v.get("retained") and fold(v["text"]) not in names.get(entity, set()):
            out.setdefault(a.passage, []).append(
                {"op": "add_value", "entity": entity, "attribute": "aliases", "value": v["text"]})
            names.setdefault(entity, set()).add(fold(v["text"]))
    return {i: out[i] for i in sorted(out)}


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
