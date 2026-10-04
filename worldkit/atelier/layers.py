"""Couches de l'atelier (I8, T3) : elles **écrivent des annotations**, que l'auteur garde, corrige ou retire.

Couche « mentions » : C1a (noms connus, sans modèle), C1b (le modèle, une question sur le document entier, si un
`finder` est donné), C2 (recoupement par score), énonciation (une note de travail ne crée pas d'entité), signaux en
option ; puis les décisions de l'auteur et les règles d'atelier.

**Règle de relance** : chaque lancement a un numéro ; une annotation d'une couche, encore `proposed` et non
remplacée, n'est courante que si elle vient du **dernier** lancement de cette couche sur la source. Une annotation de
l'auteur n'est jamais remplacée par une couche. Une portion couverte par une décision de l'auteur (gardée,
corrigée, ajoutée, ignorée) n'est plus proposée par la couche. Rien n'est effacé (ajout seul).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from . import store

LAYER = "c1-c2"


def _layer_origin(run: int) -> str:
    return f"layer:{LAYER}:{run}"


def runs_of(annotations: list[store.Annotation]) -> int:
    nums = [int(a.origin.rsplit(":", 1)[1]) for a in annotations if a.origin.startswith(f"layer:{LAYER}:")]
    return max(nums, default=0)


def effective(world: Any, branch: str, doc: Any) -> list[store.Annotation]:
    """Les annotations qui comptent : celles de l'auteur, et celles du dernier lancement de la couche."""
    now = store.current(world, branch, doc)
    last = runs_of(now)
    return [a for a in now if a.by_author or a.origin == _layer_origin(last) or a.status != "proposed"]


@dataclass
class RunReport:
    run: int
    proposed: int = 0
    skipped_by_author: int = 0
    skipped_by_rules: int = 0
    doubts: int = 0
    new: int = 0
    known: int = 0
    calls: list[Any] = field(default_factory=list)


def _overlaps(a_start: int, a_end: int, b_start: int, b_end: int) -> bool:
    return a_start < b_end and b_start < a_end


def run_mentions(world: Any, branch: str, doc_id: str, finder: Any = None, with_signals: bool = False) -> RunReport:
    """Lance la couche « mentions » sur la dernière version de la source et écrit ses annotations."""
    from worldkit.ingest.batch import extraction_context
    from worldkit.periphery.facts import enunciation
    from worldkit.periphery.matching import fold
    from worldkit.periphery.mentions import Resolver, known_mentions, merge, similar_mentions, window_of
    doc = store.source(world, doc_id)
    state = world.state(branch)
    context = extraction_context(world, state)
    window = window_of(doc)
    meter = getattr(finder, "meter", None) if finder is not None else None
    first = len(meter.calls) if meter is not None else 0
    resolver = Resolver.from_state(context, state)
    found = finder.find(window, context) if finder is not None else []
    mentions = merge(known_mentions(window, context.entities, resolver.titles), found)
    if with_signals:
        mentions = sorted(mentions + similar_mentions(window, context.entities, mentions), key=lambda m: m.start)
    for m in mentions:
        resolver.resolve(m)
    resolver.cluster_new(mentions)
    starts = {index: start for index, start, _ in window.passages}
    author = [a for a in store.current(world, branch, doc) if a.by_author and a.passage is not None]
    rules = store.rules(world, branch)
    report = RunReport(runs_of(store.current(world, branch, doc)) + 1)
    origin = _layer_origin(report.run)
    for m in mentions:
        if m.passage is None or m.start < 0:
            continue
        start, end = m.start - starts[m.passage], m.end - starts[m.passage]
        if any(a.passage == m.passage and a.start is not None and _overlaps(start, end, a.start, a.end) for a in author):
            report.skipped_by_author += 1
            continue
        form = fold(m.text)
        if any(r.form == form and r.kind == "not_entity" for r in rules):
            report.skipped_by_rules += 1
            continue
        entity, candidates, rule = m.entity, list(m.candidates), m.rule
        for r in rules:  # « les veilleurs de nuit ne sont pas les Veilleurs » : jamais rattachée à cette entité
            if r.form == form and r.kind == "not_entity_of" and (entity == r.target or r.target in candidates):
                entity, rule = None, "doubt"
                candidates = [c for c in candidates if c != r.target]
                report.skipped_by_rules += 1
        if entity and entity.startswith("new:") and enunciation(window.passage_texts.get(m.passage, "")) == "note":
            continue  # une note de travail ne crée pas d'entité (X-010)
        value = {"text": m.text, "type": m.type, "entity": entity, "candidates": candidates, "rule": rule,
                 "source": m.source, "reason": m.reason}
        confidence = "doubt" if rule in ("doubt", "ambiguous") else m.confidence
        store.add_annotation(world, branch, doc, "mention", value, origin, m.passage, start, end, confidence)
        report.proposed += 1
        report.doubts += confidence == "doubt"
        report.new += bool(entity and entity.startswith("new:"))
        report.known += bool(entity and not entity.startswith("new:"))
    if meter is not None:
        report.calls = meter.calls[first:]
    return report
