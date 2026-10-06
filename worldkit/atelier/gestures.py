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
    - `correct` : vise `ann_id`, avec `entity` (un identifiant connu, « new » pour une entité nouvelle, ou
      « new:<étiquette> » pour une entité nouvelle déjà repérée dans la source) et/ou `type_` ;
    - `add` : une portion choisie (`passage`, `start`, `end`), avec `entity` et `type_` ; à la portée de la source,
      une autre occurrence contenue dans une mention plus longue (« Ostrel » dans « Bertrand Ostrel ») est laissée.
    """
    from worldkit.periphery.matching import fold
    from worldkit.periphery.mentions import _occurrences
    if action not in ACTIONS or scope not in SCOPES:
        raise ValueError(f"geste inconnu : {action} / {scope}")
    doc = store.source(world, doc_id)
    if entity and entity.startswith("new:"):
        from .propose import new_entities
        if entity[len("new:"):].replace(" ", "-") not in new_entities(world, branch, doc):
            raise ValueError(f"entité nouvelle inconnue dans cette source : {entity}")
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
        existing = [a for a in layers.effective(world, branch, doc) if a.kind == "mention"]
        for i, s, e in spans:
            covered = next((a for a in existing if a.passage == i and a.start is not None
                            and a.start < e and s < a.end), None)
            if covered is not None and (i, s) != (passage, start) and covered.start <= s and e <= covered.end                     and covered.end - covered.start > e - s:
                continue  # « Ostrel » ne remplace pas « Bertrand Ostrel » qui le contient (portion la plus longue)
            value = {"text": texts[i][s:e], "type": type_, "entity": None if entity == "new" else entity,
                     "new": entity == "new", "candidates": [], "rule": "author", "source": "author",
                     "retained": retained}
            written.append(store.add_annotation(world, branch, doc, "mention", value, "author", i, s, e, "sure",
                                                "kept", covered.ann_id if covered else None))
        return written
    target = next((a for a in layers.effective(world, branch, doc) if a.ann_id == ann_id and a.kind == "mention"),
                  None)
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


# ---------------------------------------------------------------------------
# Gestes sur un fait (I9) : garder, retirer, reprendre (= garder un fait écarté), corriger, ajouter
# ---------------------------------------------------------------------------

FACT_ACTIONS = ("keep", "remove", "correct", "add")
FACT_OPS = ("add_relation", "set_attribute", "add_value")


def _check_draft(draft: dict[str, Any] | None) -> dict[str, Any]:
    if not draft or draft.get("op") not in FACT_OPS:
        raise ValueError("fait : brouillon invalide (relation ou attribut attendu)")
    needed = ("from", "relation", "to") if draft["op"] == "add_relation" else ("entity", "attribute", "value")
    if any(not str(draft.get(k) or "").strip() for k in needed):
        raise ValueError(f"fait : il manque {', '.join(k for k in needed if not str(draft.get(k) or '').strip())}")
    return {"op": draft["op"], **{k: str(draft[k]).strip() for k in needed}}


def fact_gesture(world: Any, branch: str, doc_id: str, action: str, ann_id: int | None = None,
                 passage: int | None = None, draft: dict[str, Any] | None = None) -> list[int]:
    """Un geste sur un fait (Q1, Q4 d'I9) ; écrit une annotation d'origine « auteur » (ajout seul, R-HIS-01).

    - `keep` : garder ; sur un fait mis de côté par le critique ou retenu par l'énonciation, c'est le **reprendre** ;
    - `remove` : retirer (il ne partira pas) ;
    - `correct` : remplacer le brouillon (`draft`), le brouillon d'origine est gardé (`origin_draft`) ;
    - `add` : un fait manqué, sur un passage (`passage`, `draft`) ; sa preuve est le passage.
    """
    if action not in FACT_ACTIONS:
        raise ValueError(f"geste inconnu sur un fait : {action}")
    doc = store.source(world, doc_id)
    if action == "add":
        texts = {p.index: p.text for p in doc.passages}
        if passage not in texts:
            raise ValueError("ajout d'un fait : passage invalide")
        value = {"draft": _check_draft(draft), "evidence": texts[passage], "layer": "author", "phrase": "",
                 "exact": "", "verdict": None, "reason": None, "voice": None, "support": False}
        return [store.add_annotation(world, branch, doc, "fact", value, "author", passage, None, None, "sure", "kept")]
    target = next((a for a in layers.effective(world, branch, doc) if a.ann_id == ann_id and a.kind == "fact"), None)
    if target is None:
        raise ValueError(f"fait inconnu ou remplacé : {ann_id}")
    value = dict(target.value)
    if action == "correct":
        value["origin_draft"] = value.get("origin_draft") or value["draft"]
        value["draft"] = _check_draft(draft)
    status = {"keep": "kept", "remove": "removed", "correct": "corrected"}[action]
    return [store.add_annotation(world, branch, doc, "fact", value, "author", target.passage, target.start,
                                 target.end, "sure", status, target.ann_id)]
