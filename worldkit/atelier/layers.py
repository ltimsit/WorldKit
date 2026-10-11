"""Couches de l'atelier (I8, T3) : elles **écrivent des annotations**, que l'auteur garde, corrige ou retire.

Couche « mentions » : C1a (noms connus, sans modèle, et formes courtes des personnes, à vérifier : choix 40), C1b (le modèle, une question sur le document entier, si un
`finder` est donné), C2 (recoupement par score), énonciation (une note de travail ne crée pas d'entité), signaux en
option ; puis les décisions de l'auteur et les règles d'atelier.

Couche « faits » (I9) : la chaîne du chantier (C5, question ciblée, énonciation, critique ; `facts_chain`) entre les
entités de la source : connues et rattachées (sauf retirées, ignorées, en doute), nouvelles **confirmées par
l'auteur**. Chaque fait devient une annotation `fact` : brouillon, preuve, couche, verdict du critique et sa raison,
voix retenue (rumeur, note), entités que le passage ne nomme pas (preuve indirecte, E-015 : jugée par le critique même
si le fait est déjà connu). Rien n'est caché : un fait mis de côté ou retenu est écrit, l'écran le grise (Q3).

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
FACTS = "facts"
NOTES = "notes"  # couche « descriptions » (J9)


def _layer_origin(run: int, layer: str = LAYER) -> str:
    return f"layer:{layer}:{run}"


def runs_of(annotations: list[store.Annotation], layer: str = LAYER) -> int:
    nums = [int(a.origin.rsplit(":", 1)[1]) for a in annotations if a.origin.startswith(f"layer:{layer}:")]
    return max(nums, default=0)


def effective(world: Any, branch: str, doc: Any) -> list[store.Annotation]:
    """Les annotations qui comptent : celles de l'auteur, et celles du dernier lancement de chaque couche."""
    now = store.current(world, branch, doc)
    last = {layer: runs_of(now, layer) for layer in (LAYER, FACTS, NOTES)}

    def latest(a: store.Annotation) -> bool:
        return any(a.origin == _layer_origin(n, layer) for layer, n in last.items())
    return [a for a in now if a.by_author or latest(a) or a.status != "proposed"]


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


def decision_keys(kind: str, draft: dict[str, Any], passage: int | None, schema: Any = None) -> set[tuple[Any, ...]]:
    """Clé(s) de décision d'une proposition de couche (règle de relance, I-ATL-02) : une proposition dont une clé a
    déjà été décidée par l'auteur (gardée, corrigée, retirée) n'est plus proposée, même reformulée.

    - note : passage et citation pliée (facette et forme courte peuvent varier d'une passe à l'autre) ;
    - attribut simple : passage, entité, attribut — la valeur peut varier (« régent de Brume », « régent ») ;
    - valeur d'une liste : passage, entité, attribut, valeur pliée (une liste en reçoit légitimement plusieurs) ;
    - relation : passage, entités, relation ; dans les deux sens si la relation est symétrique."""
    from worldkit.periphery.matching import fold
    if kind == "note":
        return {("note", passage, fold(str(draft.get("text", ""))))}
    op = draft.get("op")
    if op == "set_attribute":
        return {("attr", passage, draft.get("entity"), draft.get("attribute"))}
    if op == "add_value":
        return {("value", passage, draft.get("entity"), draft.get("attribute"), fold(str(draft.get("value", ""))))}
    if op == "add_relation":
        keys = {("rel", passage, draft.get("from"), draft.get("relation"), draft.get("to"))}
        r = schema.relations.get(draft.get("relation")) if schema is not None else None
        if r is not None and r.symmetric:
            keys.add(("rel", passage, draft.get("to"), draft.get("relation"), draft.get("from")))
        return keys
    return {(op, passage, str(sorted(draft.items())))}


def decided_keys(annotations: list[store.Annotation], kind: str, schema: Any = None) -> set[tuple[Any, ...]]:
    """Les clés de décision de l'auteur pour une sorte d'annotation (brouillon d'origine et brouillon corrigé)."""
    out: set[tuple[Any, ...]] = set()
    for a in annotations:
        if a.kind == kind and a.by_author:
            for d in (a.value.get("origin_draft"), a.value.get("draft")):
                if d:
                    out |= decision_keys(kind, d, a.passage, schema)
    return out


def _overlaps(a_start: int, a_end: int, b_start: int, b_end: int) -> bool:
    return a_start < b_end and b_start < a_end


def run_mentions(world: Any, branch: str, doc_id: str, finder: Any = None, with_signals: bool = False) -> RunReport:
    """Lance la couche « mentions » sur la dernière version de la source et écrit ses annotations."""
    from worldkit.ingest.batch import extraction_context
    from worldkit.periphery.facts import enunciation
    from worldkit.periphery.matching import fold
    from worldkit.periphery.mentions import (Resolver, check_of, known_mentions, merge, short_forms, similar_mentions,
                                             window_of)
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
    mentions = sorted(mentions + short_forms(window, mentions, context.entities, context.schema, anywhere=True),
                      key=lambda m: m.start)  # « Ysolde », « Ostrel » : à vérifier (choix 40)
    names = {e.id: e.names for e in context.entities}
    starts = {index: start for index, start, _ in window.passages}
    author = [a for a in store.current(world, branch, doc)
              if a.by_author and a.kind == "mention" and a.passage is not None]
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
                 "source": m.source, "reason": m.reason, "check": check_of(m, names.get(m.entity or "", ()))}
        confidence = "doubt" if rule in ("doubt", "ambiguous") else m.confidence
        store.add_annotation(world, branch, doc, "mention", value, origin, m.passage, start, end, confidence)
        report.proposed += 1
        report.doubts += confidence == "doubt"
        report.new += bool(entity and entity.startswith("new:"))
        report.known += bool(entity and not entity.startswith("new:"))
    if meter is not None:
        report.calls = meter.calls[first:]
    return report


# ---------------------------------------------------------------------------
# Couche « faits » (I9)
# ---------------------------------------------------------------------------

def confirmed_entities(world: Any, branch: str, doc: Any) -> tuple[list[Any], dict[str, set[str]]]:
    """Les entités de la source pour la couche « faits », et leurs formes dans le texte : connues et rattachées (sauf
    retirées, ignorées, en doute) ; nouvelles seulement si l'auteur les a confirmées (elles seules seront créées)."""
    from worldkit.ingest.batch import extraction_context
    from worldkit.periphery.facts import Confirmed

    from .propose import _label, new_entities
    context = extraction_context(world, world.state(branch))
    known = {e.id: e for e in context.entities}
    groups = new_entities(world, branch, doc)
    out: dict[str, Any] = {}
    forms: dict[str, set[str]] = {}
    for a in effective(world, branch, doc):
        if a.kind != "mention" or a.status in ("removed", "ignored") or a.confidence == "doubt":
            continue
        v = a.value
        label = _label(v)
        if label is not None:
            if not (a.by_author and a.status in ("kept", "corrected")):
                continue
            group = groups.get(label, {})
            eid = f"new:{label}"
            out.setdefault(eid, Confirmed(eid, v.get("type") or group.get("type") or "", group.get("name") or v["text"]))
        elif v.get("entity") in known and known[v["entity"]].names:
            eid = v["entity"]
            out.setdefault(eid, Confirmed(eid, known[eid].type, known[eid].names[0]))
            forms.setdefault(eid, set(known[eid].names))  # noms et alias connus
        else:
            continue
        forms.setdefault(eid, {out[eid].name}).add(v["text"])
    return sorted(out.values(), key=lambda e: e.id), forms


@dataclass
class FactsReport:
    run: int
    entities: int = 0
    proposed: int = 0
    set_aside: int = 0
    withheld: int = 0
    indirect: int = 0
    doubts: int = 0
    skipped_by_author: int = 0
    unplaced: int = 0
    calls: list[Any] = field(default_factory=list)


def _span(text: str, evidence: str) -> tuple[int | None, int | None]:
    """La preuve dans le texte du passage (pour la surligner), si elle s'y trouve telle quelle."""
    i = text.find(evidence.strip())
    return (i, i + len(evidence.strip())) if evidence.strip() and i >= 0 else (None, None)


def run_facts(world: Any, branch: str, doc_id: str, finder: Any, probe: Any = None, critic: Any = None) -> FactsReport:
    """Lance la couche « faits » sur la dernière version de la source ; écrit une annotation par fait, gardé ou non."""
    import json

    from worldkit.ingest.batch import extraction_context
    from worldkit.periphery.evaluation import is_support, key
    from worldkit.periphery.facts import facts_chain, missing_entities
    from worldkit.periphery.mentions import window_of
    doc = store.source(world, doc_id)
    state = world.state(branch)
    context = extraction_context(world, state)
    entities, forms = confirmed_entities(world, branch, doc)
    now = store.current(world, branch, doc)
    report = FactsReport(runs_of(now, FACTS) + 1, len(entities))
    meter = getattr(finder, "meter", None)
    first = len(meter.calls) if meter is not None else 0
    window = window_of(doc)
    result = facts_chain(window, entities, context.schema, state, finder, probe, forms, critic, True, {},
                         {e.id: e.names for e in context.entities})
    verdicts = {id(f): v for f, v in result.judged}
    texts = window.passage_texts
    every = result.kept + [f for f, _ in result.judged] + [f for f, _ in result.withheld]
    missing = {id(f): missing_entities(f, texts.get(f.passage, ""), forms) for f in every if f.passage is not None}
    if critic is not None:  # une preuve indirecte est jugée même si le fait est déjà connu (E-015)
        for f in result.kept:
            if missing.get(id(f)) and id(f) not in verdicts:
                verdicts[id(f)] = critic.judge(f, texts[f.passage], entities, context.schema,
                                               {e.id: e.names for e in context.entities})
    voices = {id(f): voice for f, voice in result.withheld}
    decided = decided_keys(now, "fact", context.schema)  # règle de relance, normalisée (I-ATL-02)
    origin = _layer_origin(report.run, FACTS)
    seen: set[tuple[str, int | None]] = set()
    for f in result.kept + [f for f, _ in result.judged if f not in result.kept] + [f for f, _ in result.withheld]:
        signature = json.dumps(f.draft, sort_keys=True)
        if (signature, f.passage) in seen:
            continue  # un même fait dans deux passages : deux preuves, deux annotations (T-ING-11)
        seen.add((signature, f.passage))
        if f.passage is None:
            report.unplaced += 1
            continue
        if decision_keys("fact", f.draft, f.passage, context.schema) & decided:
            report.skipped_by_author += 1
            continue
        verdict = verdicts.get(id(f)) or {}
        voice = voices.get(id(f))
        start, end = _span(texts.get(f.passage, ""), f.evidence)
        value = {"draft": f.draft, "evidence": f.evidence, "layer": f.layer, "phrase": f.phrase, "exact": f.exact,
                 "verdict": verdict.get("verdict"), "reason": verdict.get("reason"), "voice": voice,
                 "support": is_support(key(f.draft, {}), state), "indirect": missing.get(id(f), [])}
        confidence = "doubt" if verdict.get("verdict") == "unsure" else "sure"
        store.add_annotation(world, branch, doc, "fact", value, origin, f.passage, start, end, confidence)
        report.proposed += 1
        report.set_aside += verdict.get("verdict") == "not_supported"
        report.withheld += voice is not None
        report.indirect += bool(value["indirect"])
        report.doubts += confidence == "doubt"
    if meter is not None:
        report.calls = meter.calls[first:]
    return report


def fact_excluded(a: store.Annotation) -> bool:
    """Un fait qui ne partira pas avec « Proposer » (Q1) : retiré, ou écarté par la couche et non repris."""
    if a.status == "removed":
        return True
    if a.by_author:
        return False
    return a.value.get("verdict") == "not_supported" or a.value.get("voice") is not None


# ---------------------------------------------------------------------------
# Couche « descriptions » (J9 ; R-NTE-01 à R-NTE-05)
# ---------------------------------------------------------------------------

@dataclass
class NotesReport:
    run: int
    entities: int = 0
    proposed: int = 0
    rejected: int = 0
    skipped_by_author: int = 0
    calls: list[Any] = field(default_factory=list)


def kept_facts(world: Any, branch: str, doc: Any) -> tuple[list[str], dict[str, set[str]], list[tuple[int, str, set[str]]]]:
    """Les faits de la source qui partiront (R-NTE-05) : dits **en clair** pour la couche « descriptions » (noms et
    libellés : « Ysolde Marcastel — déteste — la Guilde des Bateliers »), les valeurs d'attribut pliées par entité, et
    les preuves extraites (passage, preuve, entités) pour le garde-fou sans modèle. Un fait ajouté à la main n'a pour
    preuve que son passage entier : il ne sert pas au garde-fou."""
    from worldkit.periphery.matching import fold
    schema = world.state(branch).world
    entities, _ = confirmed_entities(world, branch, doc)
    names = {e.id: e.name for e in entities}
    types = {e.id: e.type for e in entities}

    def name(eid: str) -> str:
        return names.get(eid, eid)
    known: list[str] = []
    values: dict[str, set[str]] = {}
    evidence: list[tuple[int, str, set[str]]] = []
    for a in effective(world, branch, doc):
        if a.kind != "fact" or fact_excluded(a):
            continue
        d = a.value["draft"]
        if d.get("op") == "add_relation":
            r = schema.relations.get(d["relation"])
            label = (r.labels or {}).get("fr", d["relation"]) if r is not None else d["relation"]
            known.append(f"{name(d['from'])} — {label} — {name(d['to'])}")
            cited = {d["from"], d["to"]}
        else:
            t = types.get(d["entity"])
            definition = schema.attributes_of(t).get(d["attribute"]) if t in schema.types else None
            label = (definition.labels or {}).get("fr", d["attribute"]) if definition is not None else d["attribute"]
            known.append(f"{name(d['entity'])} — {label} : {d['value']}")
            values.setdefault(d["entity"], set()).add(fold(str(d["value"])))
            cited = {d["entity"]}
        if a.passage is not None and a.value.get("layer") != "author" and a.value.get("evidence"):
            evidence.append((a.passage, str(a.value["evidence"]), cited))
    return sorted(set(known)), values, evidence


def run_notes(world: Any, branch: str, doc_id: str, finder: Any) -> NotesReport:
    """Lance la couche « descriptions » après les faits, entre les entités confirmées ; écrit une annotation par bribe
    (`kind: note`). Relancée, elle ne repropose pas une citation que l'auteur a décidée."""

    from worldkit.periphery.mentions import window_of
    doc = store.source(world, doc_id)
    entities, _ = confirmed_entities(world, branch, doc)
    now = store.current(world, branch, doc)
    report = NotesReport(runs_of(now, NOTES) + 1, len(entities))
    meter = getattr(finder, "meter", None)
    first = len(meter.calls) if meter is not None else 0
    window = window_of(doc)
    known, values, evidence = kept_facts(world, branch, doc)
    before = len(finder.rejected)
    found = finder.find(window, entities, world.state(branch).world, known, values, evidence)
    report.rejected = len(finder.rejected) - before
    decided = decided_keys(now, "note")  # règle de relance, normalisée (I-ATL-02)
    origin = _layer_origin(report.run, NOTES)
    for n in found:
        if decision_keys("note", n.draft, n.passage) & decided:
            report.skipped_by_author += 1
            continue
        start, end = _span(window.passage_texts.get(n.passage, ""), n.draft["text"])
        store.add_annotation(world, branch, doc, "note", {"draft": n.draft, "layer": NOTES}, origin, n.passage,
                             start, end, "sure")
        report.proposed += 1
    if meter is not None:
        report.calls = meter.calls[first:]
    return report


def note_excluded(a: store.Annotation) -> bool:
    """Une bribe qui ne partira pas avec « Proposer » : retirée par l'auteur."""
    return a.status == "removed"
