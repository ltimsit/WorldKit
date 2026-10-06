"""Gestes de l'auteur dans l'atelier (I8, T3 ; Q4) : garder, retirer, corriger, ajouter, ignorer, avec une portée.

Chaque geste écrit des annotations d'origine « auteur » (ajout seul) qui remplacent celles qu'il vise.

Portées (Q4) :
- `occurrence` : la seule annotation visée ;
- `source` (défaut) : toutes les annotations courantes de la source qui portent la même forme (pliée), et, pour un
  ajout, toutes les autres occurrences de la forme dans le texte ;
- `world` : comme `source`, et le geste est **retenu** : positif (garder, corriger vers une entité, ajouter) → l'alias
  sera proposé au journal par « Proposer » si la forme n'est pas déjà un nom de l'entité ; négatif (retirer,
  ignorer, corriger en s'écartant d'une entité) → **règle d'atelier** pour les sources futures de la branche.
"""

from __future__ import annotations

from typing import Any

from . import layers, store

ACTIONS = ("keep", "remove", "correct", "add", "ignore")
SCOPES = ("occurrence", "source", "world")
STATUS = {"keep": "kept", "remove": "removed", "correct": "corrected", "add": "kept", "ignore": "ignored"}


def _same_form(a: store.Annotation, form: str) -> bool:
    from worldkit.periphery.matching import fold
    return a.kind == "mention" and fold(a.value.get("text", "")) == form


def gesture(world: Any, branch: str, doc_id: str, action: str, scope: str = "source", ann_id: int | None = None,
            passage: int | None = None, start: int | None = None, end: int | None = None,
            entity: str | None = None, type_: str | None = None) -> list[int]:
    """Applique un geste ; rend les identifiants des annotations écrites (et des règles, en négatif si portée monde).

    - `keep`, `remove`, `ignore` : visent `ann_id` ;
    - `correct` : vise `ann_id`, avec `entity` (un identifiant, ou « new » pour une entité nouvelle) et/ou `type_` ;
    - `add` : une portion choisie (`passage`, `start`, `end`), avec `entity` et `type_`.
    """
    from worldkit.periphery.matching import fold
    from worldkit.periphery.mentions import _occurrences
    if action not in ACTIONS or scope not in SCOPES:
        raise ValueError(f"geste inconnu : {action} / {scope}")
    doc = store.source(world, doc_id)
    texts = {p.index: p.text for p in doc.passages}
    retained = scope == "world"
    written: list[int] = []
    if action == "add":
        if passage not in texts or start is None or end is None or not 0 <= start < end <= len(texts[passage]):
            raise ValueError("ajout : portion invalide")
        text = texts[passage][start:end]
        spans = [(passage, start, end)]
        if scope != "occurrence":
            spans += [(i, s, s + len(text)) for i, t in sorted(texts.items()) for s in _occurrences(t, text)
                      if (i, s) != (passage, start)]
        existing = layers.effective(world, branch, doc)
        for i, s, e in spans:
            covered = next((a for a in existing if a.passage == i and a.start is not None
                            and a.start < e and s < a.end), None)
            value = {"text": texts[i][s:e], "type": type_, "entity": None if entity == "new" else entity,
                     "new": entity == "new", "candidates": [], "rule": "author", "source": "author",
                     "retained": retained}
            written.append(store.add_annotation(world, branch, doc, "mention", value, "author", i, s, e, "sure",
                                                "kept", covered.ann_id if covered else None))
        return written
    target = next((a for a in layers.effective(world, branch, doc) if a.ann_id == ann_id), None)
    if target is None:
        raise ValueError(f"annotation inconnue ou remplacée : {ann_id}")
    form = fold(target.value.get("text", ""))
    targets = [target] if scope == "occurrence" else \
        [a for a in layers.effective(world, branch, doc) if _same_form(a, form)]
    for a in targets:
        value = dict(a.value)
        if action == "correct":
            if entity is not None:
                value["entity"] = None if entity == "new" else entity
                value["new"] = entity == "new"
            if type_ is not None:
                value["type"] = type_
        if action in ("ignore", "remove"):
            value["entity"] = None
        value["retained"] = retained
        written.append(store.add_annotation(world, branch, doc, "mention", value, "author", a.passage, a.start, a.end,
                                            "sure", STATUS[action], a.ann_id))
    if retained and action in ("remove", "ignore"):
        store.add_rule(world, branch, target.value.get("text", ""), "not_entity")
    if retained and action == "correct" and target.value.get("entity") and entity != target.value.get("entity"):
        store.add_rule(world, branch, target.value.get("text", ""), "not_entity_of", target.value["entity"])
    return written
