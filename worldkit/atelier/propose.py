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


def batch_id_of(doc: Any) -> str:
    return f"atelier-{doc.doc_id}-{doc.fingerprint[:8]}"


def proposed(world: Any, doc: Any) -> bool:
    """La version de la source a-t-elle déjà été proposée (son lot existe) ?"""
    from worldkit.ingest.batch import ensure_tables
    ensure_tables(world.store.conn)
    return _batch_exists(world, batch_id_of(doc))


def attachments(world: Any, branch: str, doc: Any) -> list[dict[str, Any]]:
    """Rattachements de l'auteur dont la forme n'est pas encore un nom de l'entité visée (« Ostrel » pour Bertrand
    Ostrel, « jehan » pour Jehan Marcastel), avec `retained` : l'alias ne part que retenu pour le monde (Q4). Rend
    visible ce que « Proposer » enverra ou non (E-014)."""
    from worldkit.ingest.batch import extraction_context
    from worldkit.periphery.matching import fold
    context = extraction_context(world, world.state(branch))
    known = {e.id: (e.names[0] if e.names else e.id, {fold(n) for n in e.names}) for e in context.entities}
    groups = new_entities(world, branch, doc)
    out: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()  # (entité, forme pliée)
    for a in sorted(layers.effective(world, branch, doc), key=lambda a: (a.passage or 0, a.start or 0)):
        if not a.by_author or a.kind != "mention" or a.status not in ("kept", "corrected") or a.passage is None:
            continue
        v = a.value
        label = _label(v)
        if label is not None:
            group = groups.get(label)
            if group is None:
                continue
            target, name, names = f"new:{label}", group["name"], {fold(group["name"])}
        elif v.get("entity") in known:
            target = v["entity"]
            name, names = known[target]
        else:
            continue
        if fold(v["text"]) in names:
            continue
        key = (target, fold(v["text"]))
        if key in seen:
            row = next(r for r in out if (r["entity"], fold(r["text"])) == key)
            row["ann_ids"].append(a.ann_id)
            row["retained"] = row["retained"] or bool(v.get("retained"))
            continue
        seen.add(key)
        out.append({"ann_id": a.ann_id, "ann_ids": [a.ann_id], "passage": a.passage, "text": v["text"],
                    "entity": target, "name": name, "retained": bool(v.get("retained"))})
    return out


def _batch_exists(world: Any, batch_id: str) -> bool:
    from worldkit.ingest.batch import ensure_tables
    ensure_tables(world.store.conn)
    return world.store.conn.execute("SELECT 1 FROM batches WHERE batch_id = ?", (batch_id,)).fetchone() is not None


def facts_batch_id_of(doc: Any) -> str:
    return f"{batch_id_of(doc)}-faits"


def facts_proposed(world: Any, doc: Any) -> bool:
    return _batch_exists(world, facts_batch_id_of(doc))


def fact_drafts(world: Any, branch: str, doc: Any) -> dict[int, list[dict[str, Any]]]:
    """Les faits qui partent (Q1 d'I9) : tous ceux de la couche ou de l'auteur, sauf retirés et écartés non repris."""
    out: dict[int, list[dict[str, Any]]] = {}
    for a in sorted(layers.effective(world, branch, doc), key=lambda a: (a.passage or 0, a.ann_id)):
        if a.kind != "fact" or a.passage is None or layers.fact_excluded(a):
            continue
        draft = dict(a.value["draft"])
        if draft not in out.get(a.passage, []):
            out.setdefault(a.passage, []).append(draft)
    return out


def _settled(world: Any, branch: str, drafts: dict[int, list[dict[str, Any]]]) -> tuple[dict[int, list[dict[str, Any]]], int]:
    """Lot de faits après le lot des entités (Q2 d'I9) : une entité nouvelle de la source (`new:<étiquette>`) est
    désignée par son identifiant si sa création est acceptée, par `pending:<étiquette>` si elle attend encore en revue
    (T-ING-07) ; un fait sur une entité refusée ne part pas. Rend les brouillons et le nombre de faits écartés."""
    from worldkit.ingest.queue import pending_new_entities
    head = world.state(branch)
    pending = pending_new_entities(world, head)
    created = {label: eid for label, eid in world.store.conn.execute("SELECT label, entity_id FROM new_entities")}
    dropped = 0
    out: dict[int, list[dict[str, Any]]] = {}

    def settle(v: Any) -> Any:
        if isinstance(v, str) and v.startswith("new:"):
            label = v[len("new:"):]
            if label in pending:
                return f"pending:{label}"
            if created.get(label) in head.entities:
                return created[label]
            raise LookupError(label)
        return v
    for passage, ds in drafts.items():
        for d in ds:
            try:
                out.setdefault(passage, []).append({k: settle(v) for k, v in d.items()})
            except LookupError:
                dropped += 1
    return out, dropped


def _ingest(world: Any, branch: str, doc: Any, batch_id: str, by_passage: dict[int, list[dict[str, Any]]],
            reopen: bool = False) -> Any:
    from worldkit.ingest.batch import ingest
    texts = {p.index: p.text for p in doc.passages}
    drafts = {texts[i]: d for i, d in by_passage.items()}
    digest = hashlib.sha256(json.dumps(drafts, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:8]
    row = world.store.conn.execute("SELECT text FROM atelier_sources WHERE doc_id = ? AND version_fp = ?",
                                   (doc.doc_id, doc.fingerprint)).fetchone()
    return ingest(world, batch_id, [SourceText(f"atelier:{doc.doc_id}", row[0])],
                  AtelierExtractor(drafts, f"atelier:{digest}"), branch, reopen)


def propose(world: Any, branch: str, doc_id: str) -> Any:
    """Crée le lot de la source et l'enregistre (E1 à E9+) ; rend le compte rendu du lot.

    Premier « Proposer » d'une version : entités, alias **et faits** en un lot. Si les entités sont déjà parties, un
    second lot, `…-faits`, ne porte que les faits (Q2 d'I9) ; une version ne se propose qu'une fois de chaque sorte."""
    from worldkit.ingest.batch import BatchError
    doc = store.source(world, doc_id)
    facts = fact_drafts(world, branch, doc)
    if proposed(world, doc):
        if facts_proposed(world, doc):
            raise BatchError("déjà proposée : entités et faits de cette version sont partis")
        settled, dropped = _settled(world, branch, facts)
        if not settled:
            raise BatchError("rien à proposer : aucun fait à envoyer" + (f" ({dropped} sur des entités refusées)"
                                                                         if dropped else ""))
        return _ingest(world, branch, doc, facts_batch_id_of(doc), settled, reopen=True)
    by_passage = drafts_of(world, branch, doc)
    for passage, ds in facts.items():
        by_passage.setdefault(passage, []).extend(ds)
    if not by_passage:
        raise BatchError("rien à proposer : aucune entité nouvelle confirmée, aucun alias retenu, aucun fait")
    return _ingest(world, branch, doc, batch_id_of(doc), dict(sorted(by_passage.items())))
