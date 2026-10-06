"""Opérations de l'atelier d'ingestion (I8, T3 ; I9) : importer, voir, lancer une couche (mentions, faits), annoter,
proposer.

L'atelier écrit dans le **monde** (son magasin, hors journal) : c'est le travail de l'auteur, pas un essai ; les
appels au modèle passent par l'estimation et la confirmation (I-LLM-01). « Proposer » écrit un lot (E9+), comme
`pipeline.save`.
"""

from __future__ import annotations

from typing import Any

from pydantic import Field

from worldkit.core.schema import Issue, IssueCode, Severity

from .registry import Output, Params, operation
from .session import Context


class SourceParams(Params):
    doc_id: str = Field(..., description="identifiant de la source (document)")
    branch: str | None = Field(None, description="branche (défaut : référence)")


class ImportParams(Params):
    text: str = Field(..., description="le texte collé (avec ou sans en-tête YAML)")
    doc_id: str | None = Field(None, description="identifiant (défaut : tiré du titre)")
    mode: str = "source"
    nature: str = "diegetic"
    voice: str = "author"


def _branch(ctx: Context, p: Any) -> str:
    assert ctx.world is not None
    return p.branch or ctx.world.reference_branch


@operation("atelier.import", "write", ImportParams, "atelier : importer une source (texte collé ou fichier)",
           ("I-ATL-01", "R-DOC-02", "T-ING-10"))
def atelier_import(ctx: Context, p: ImportParams) -> Output:
    from worldkit.atelier import store
    assert ctx.world is not None
    doc = store.import_source(ctx.world, p.text, p.doc_id, mode=p.mode, nature=p.nature, voice=p.voice)
    return Output({"doc_id": doc.doc_id, "version": doc.fingerprint, "title": doc.title,
                   "passages": len(doc.passages)}, [], {"passages": len(doc.passages)})


class NoParams(Params):
    pass


@operation("atelier.sources", "read", NoParams, "atelier : les sources, la plus récente d'abord", ("I-ATL-05",))
def atelier_sources(ctx: Context, p: NoParams) -> Output:
    from worldkit.atelier import layers, store
    assert ctx.world is not None
    rows = []
    for doc_id, vfp in store.sources(ctx.world):
        doc = store.source(ctx.world, doc_id, vfp)
        current = layers.effective(ctx.world, ctx.world.reference_branch, doc)
        rows.append({"doc_id": doc_id, "version": vfp, "title": doc.title, "passages": len(doc.passages),
                     "to_review": sum(1 for a in current if not a.by_author),
                     "decided": sum(1 for a in current if a.by_author)})
    return Output(rows, [], {"sources": len(rows)})


def _annotation(a: Any) -> dict[str, Any]:
    return {"id": a.ann_id, "passage": a.passage, "start": a.start, "end": a.end, "kind": a.kind, "value": a.value,
            "origin": a.origin, "confidence": a.confidence, "status": a.status, "by_author": a.by_author}


@operation("atelier.view", "read", SourceParams, "atelier : une source, ses passages et ses annotations courantes",
           ("I-ATL-05",))
def atelier_view(ctx: Context, p: SourceParams) -> Output:
    from worldkit.atelier import layers, store
    assert ctx.world is not None
    branch = _branch(ctx, p)
    doc = store.source(ctx.world, p.doc_id)
    current = layers.effective(ctx.world, branch, doc)
    facts_view = _facts_view(ctx.world, branch, doc, current)
    passages = [{"index": x.index, "text": x.text,
                 "annotations": [_annotation(a) for a in sorted(current, key=lambda a: a.start or 0)
                                 if a.passage == x.index and a.kind == "mention"],
                 "facts": [f for f in facts_view["facts"] if f["passage"] == x.index]} for x in doc.passages]
    to_review = sum(1 for a in current if not a.by_author and a.kind == "mention")
    from worldkit.ingest.batch import extraction_context
    state = ctx.world.state(branch)
    entities = [{"id": e.id, "type": e.type, "name": e.names[0] if e.names else e.id}
                for e in extraction_context(ctx.world, state).entities]
    from worldkit.atelier.propose import attachments, facts_proposed, new_entities, proposed
    news = [{"id": e["id"], "type": e["type"], "name": e["name"]}
            for e in sorted(new_entities(ctx.world, branch, doc).values(), key=lambda e: e["name"].casefold())]
    return Output({"doc_id": doc.doc_id, "version": doc.fingerprint, "title": doc.title, "branch": branch,
                   "passages": passages, "rules": [r.__dict__ for r in store.rules(ctx.world, branch)],
                   "run": layers.runs_of(current), "entities": entities, "new_entities": news,
                   "attachments": attachments(ctx.world, branch, doc), "proposed": proposed(ctx.world, doc),
                   "facts_proposed": facts_proposed(ctx.world, doc), "types": sorted(state.world.types),
                   **{k: v for k, v in facts_view.items() if k != "facts"}},
                  [], {"to_review": to_review, "decided": sum(1 for a in current if a.by_author and a.kind == "mention"),
                       "facts": len(facts_view["facts"]), "facts_to_send": facts_view["to_send"]})


def _fact_state(a: Any) -> str:
    """La pastille d'un fait à l'écran (Q3 d'I9) : ce que la couche ou l'auteur en a fait."""
    v = a.value
    if a.by_author:
        return {"removed": "retiré", "corrected": "corrigé"}.get(a.status, "ajouté" if v.get("layer") == "author"
                                                                 else "gardé")
    if v.get("voice"):
        return "rumeur" if v["voice"] == "attribution" else "note"
    if v.get("verdict") == "not_supported":
        return "mis de côté"
    if v.get("verdict") == "unsure":
        return "douteux"
    if v.get("support"):
        return "déjà connu"
    return "soutenu" if v.get("verdict") == "supported" else "proposé"


def _facts_view(world: Any, branch: str, doc: Any, current: list[Any]) -> dict[str, Any]:
    """Les faits de la source en français (libellés du schéma), et ce qu'il faut pour les corriger ou en ajouter."""
    from worldkit.atelier import layers
    schema = world.state(branch).world
    entities, _ = layers.confirmed_entities(world, branch, doc)
    names = {e.id: e.name for e in entities}
    types = {e.id: e.type for e in entities}

    def name(eid: str) -> str:
        return names.get(eid) or eid

    def label(d: dict[str, Any], phrase: str = "") -> str:
        if d.get("op") == "add_relation":
            r = schema.relations.get(d["relation"])
            rel = (r.labels or {}).get("fr", d["relation"]) if r is not None else (phrase or d["relation"])
            return f"{name(d['from'])} — {rel}{'' if r is not None else ' (hors schéma)'} — {name(d['to'])}"
        definition = schema.attributes_of(types[d["entity"]]).get(d["attribute"]) \
            if types.get(d.get("entity")) in schema.types else None
        attr = (definition.labels or {}).get("fr", d["attribute"]) if definition is not None else d["attribute"]
        return f"{name(d['entity'])} — {attr} : {d['value']}"
    facts = []
    for a in sorted((a for a in current if a.kind == "fact"), key=lambda a: (a.passage or 0, a.start or 0, a.ann_id)):
        v = a.value
        excluded = layers.fact_excluded(a)
        facts.append({"id": a.ann_id, "passage": a.passage, "start": a.start, "end": a.end, "draft": v["draft"],
                      "label": label(v["draft"], v.get("phrase", "")),
                      "origin_label": label(v["origin_draft"]) if v.get("origin_draft") else None,
                      "evidence": v.get("evidence"), "layer": v.get("layer"), "verdict": v.get("verdict"),
                      "reason": v.get("reason"), "voice": v.get("voice"), "exact": v.get("exact"),
                      "state": _fact_state(a), "excluded": excluded, "by_author": a.by_author, "status": a.status})
    relations = [{"id": r, "label": (d.labels or {}).get("fr", r)} for r, d in sorted(schema.relations.items())]
    attributes = sorted({(attr, (d.labels or {}).get("fr", attr)) for t in schema.types
                         for attr, d in schema.attributes_of(t).items() if attr not in ("name",)})
    return {"facts": facts, "to_send": sum(1 for f in facts if not f["excluded"]),
            "fact_entities": [{"id": e.id, "name": e.name, "type": e.type} for e in entities],
            "relations": relations, "attributes": [{"id": a, "label": lbl} for a, lbl in attributes],
            "facts_run": layers.runs_of(current, layers.FACTS)}


class RunParams(SourceParams):
    layer: str = Field("mentions", description="mentions (défaut) ou facts (C5, question ciblée, énonciation, critique)")
    model: bool = Field(False, description="faire appel au modèle (C1b) ; sinon noms connus et recoupement seuls")
    profile: str | None = Field(None, description="profil du modèle (défaut : tâche « mentions »)")
    llm_config: str | None = None
    signals: bool = Field(False, description="signaler sans décider (X-012)")
    confirm: bool = False


@operation("atelier.run", "write", RunParams,
           "atelier : lancer la couche « mentions » (noms connus, modèle en option, recoupement), avec estimation",
           ("I-ATL-02", "I-LLM-01", "T-ING-07"))
def atelier_run(ctx: Context, p: RunParams) -> Output:
    from worldkit.atelier import layers
    assert ctx.world is not None
    if p.layer == "facts":
        return _run_facts(ctx, p)
    if p.layer != "mentions":
        return Output(None, [Issue(IssueCode.EDIT_RULE, f"couche inconnue : {p.layer}", "I-ATL-02")])
    finder = None
    if p.model:
        from worldkit.periphery.llm import load_config, make_adapter
        from worldkit.periphery.mentions import MentionFinder
        profile = load_config(p.llm_config).profile(p.profile, "mentions")
        if not p.confirm:
            return Output({"estimate": {"calls": 1, "model": profile.model, "profile": profile.name,
                                        "adapter": profile.adapter, "layer": "mentions"}},
                          [Issue(IssueCode.EDIT_RULE, f"1 appel au modèle {profile.model} (profil {profile.name}, "
                                 f"{profile.adapter}) : confirmer pour lancer",
                                 "I-LLM-01", Severity.WARNING)], {"estimated_calls": 1}, status="pending")
        finder = MentionFinder(make_adapter(profile), profile)
    report = layers.run_mentions(ctx.world, _branch(ctx, p), p.doc_id, finder, p.signals)
    from worldkit.periphery.llm.usage import input_budget, summarize
    usage = summarize(report.calls, input_budget()) | {"seconds": round(sum(c.seconds for c in report.calls), 1)}
    return Output(report.__dict__ | {"calls": len(report.calls), "usage": usage}, [],
                  {"proposed": report.proposed, "doubts": report.doubts, "new": report.new,
                   "llm_calls": len(report.calls)})


def _run_facts(ctx: Context, p: RunParams) -> Output:
    """Couche « faits » (I9) : toujours avec le modèle, donc estimée puis confirmée (I-LLM-01)."""
    from worldkit.atelier import layers, store
    from worldkit.periphery.facts import Critic, FactFinder, RelationProbe
    from worldkit.periphery.llm import load_config, make_adapter
    from worldkit.periphery.llm.usage import input_budget, summarize
    assert ctx.world is not None
    branch = _branch(ctx, p)
    doc = store.source(ctx.world, p.doc_id)
    entities, _ = layers.confirmed_entities(ctx.world, branch, doc)
    if len(entities) < 1:
        return Output(None, [Issue(IssueCode.EDIT_RULE, "aucune entité confirmée : lancer d'abord la couche "
                                   "« mentions » et confirmer les entités nouvelles", "I-ATL-02")])
    profile = load_config(p.llm_config).profile(p.profile, "facts")
    passages = len(doc.passages)
    calls = 1 + passages + 2 * passages  # C5 ; au plus une question ciblée par passage ; le critique, par fait
    if not p.confirm:
        return Output({"estimate": {"calls": calls, "model": profile.model, "profile": profile.name,
                                    "adapter": profile.adapter, "entities": len(entities), "layer": "facts"}},
                      [Issue(IssueCode.EDIT_RULE, f"environ {calls} appels au modèle {profile.model} (profil "
                             f"{profile.name}, {profile.adapter}) : 1 pour C5, au plus {passages} questions ciblées, "
                             "un jugement par fait qui pose une question : confirmer pour lancer",
                             "I-LLM-01", Severity.WARNING)], {"estimated_calls": calls}, status="pending")
    adapter = make_adapter(profile)
    report = layers.run_facts(ctx.world, branch, p.doc_id, FactFinder(adapter, profile),
                              RelationProbe(adapter, profile, with_relations=True, by_pair=True),
                              Critic(adapter, profile))
    usage = summarize(report.calls, input_budget()) | {"seconds": round(sum(c.seconds for c in report.calls), 1)}
    return Output(report.__dict__ | {"calls": len(report.calls), "usage": usage}, [],
                  {"proposed": report.proposed, "set_aside": report.set_aside, "withheld": report.withheld,
                   "doubts": report.doubts, "llm_calls": len(report.calls)})


class AnnotateParams(SourceParams):
    action: str = Field(..., description="keep, remove, correct, add, ignore")
    scope: str = Field("source", description="occurrence, source (défaut) ou world (retenu)")
    ann_id: int | None = None
    passage: int | None = None
    start: int | None = None
    end: int | None = None
    entity: str | None = Field(None, description="identifiant d'entité, « new », ou « new:<étiquette> » (une entité nouvelle de la source)")
    type: str | None = None
    kind: str = Field("mention", description="mention (défaut) ou fact (I9)")
    subject: str | None = Field(None, description="fait : sujet (identifiant d'entité)")
    relation: str | None = Field(None, description="fait : relation du schéma")
    object: str | None = Field(None, description="fait : objet d'une relation (identifiant d'entité)")
    attribute: str | None = Field(None, description="fait : attribut du schéma")
    value: str | None = Field(None, description="fait : valeur de l'attribut")


@operation("atelier.annotate", "write", AnnotateParams,
           "atelier : un geste de l'auteur (garder, retirer, corriger, ajouter, ignorer) et sa portée",
           ("I-ATL-03", "R-HIS-01"))
def atelier_annotate(ctx: Context, p: AnnotateParams) -> Output:
    from worldkit.atelier import gestures
    assert ctx.world is not None
    if p.kind == "fact":
        try:
            written = gestures.fact_gesture(ctx.world, _branch(ctx, p), p.doc_id, p.action, p.ann_id, p.passage,
                                            _fact_draft(ctx, p) if p.action in ("correct", "add") else None)
        except ValueError as e:
            return Output(None, [Issue(IssueCode.EDIT_RULE, str(e), "I-ATL-03")])
        return Output({"written": written}, [], {"written": len(written)})
    try:
        written = gestures.gesture(ctx.world, _branch(ctx, p), p.doc_id, p.action, p.scope, p.ann_id, p.passage,
                                   p.start, p.end, p.entity, p.type)
    except ValueError as e:
        return Output(None, [Issue(IssueCode.EDIT_RULE, str(e), "I-ATL-03")])
    return Output({"written": written}, [], {"written": len(written)})


def _fact_draft(ctx: Context, p: AnnotateParams) -> dict[str, Any]:
    """Le brouillon d'un fait choisi dans les listes : une relation, ou un attribut (simple ou liste, selon le schéma)."""
    from worldkit.atelier import layers, store
    branch = _branch(ctx, p)
    if p.relation:
        return {"op": "add_relation", "from": p.subject or "", "relation": p.relation, "to": p.object or ""}
    schema = ctx.world.state(branch).world
    entities, _ = layers.confirmed_entities(ctx.world, branch, store.source(ctx.world, p.doc_id))
    type_ = next((e.type for e in entities if e.id == p.subject), None)
    definition = schema.attributes_of(type_).get(p.attribute or "") if type_ in schema.types else None
    op = "add_value" if definition is not None and definition.type.is_list else "set_attribute"
    return {"op": op, "entity": p.subject or "", "attribute": p.attribute or "", "value": p.value or ""}


@operation("atelier.propose", "write", SourceParams,
           "atelier : proposer les entités confirmées, les alias retenus et les faits (un lot, jusqu'à la revue ; "
           "les faits seuls si les entités sont déjà parties)",
           ("I-ATL-04", "T-ING-07", "T-ING-11"))
def atelier_propose(ctx: Context, p: SourceParams) -> Output:
    from worldkit.atelier import propose
    from worldkit.ingest.batch import BatchError
    assert ctx.world is not None
    try:
        report = propose.propose(ctx.world, _branch(ctx, p), p.doc_id)
    except BatchError as e:
        return Output(None, [Issue(IssueCode.EDIT_RULE, str(e), "I-ATL-04")])
    return Output({"batch": report.batch_id, "proposals": [x.id for x in report.proposals],
                   "new_entities": [e.id for e in report.new_entities]}, [],
                  {"proposals": len(report.proposals)})
