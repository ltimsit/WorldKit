"""Opérations de l'atelier d'ingestion (I8, T3) : importer, voir, lancer une couche, annoter, proposer.

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
    passages = [{"index": x.index, "text": x.text,
                 "annotations": [_annotation(a) for a in sorted(current, key=lambda a: a.start or 0)
                                 if a.passage == x.index]} for x in doc.passages]
    to_review = sum(1 for a in current if not a.by_author)
    from worldkit.ingest.batch import extraction_context
    state = ctx.world.state(branch)
    entities = [{"id": e.id, "type": e.type, "name": e.names[0] if e.names else e.id}
                for e in extraction_context(ctx.world, state).entities]
    return Output({"doc_id": doc.doc_id, "version": doc.fingerprint, "title": doc.title, "branch": branch,
                   "passages": passages, "rules": [r.__dict__ for r in store.rules(ctx.world, branch)],
                   "run": layers.runs_of(current), "entities": entities, "types": sorted(state.world.types)},
                  [], {"to_review": to_review, "decided": sum(1 for a in current if a.by_author)})


class RunParams(SourceParams):
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
    finder = None
    if p.model:
        from worldkit.periphery.llm import load_config, make_adapter
        from worldkit.periphery.mentions import MentionFinder
        profile = load_config(p.llm_config).profile(p.profile, "mentions")
        if not p.confirm:
            return Output({"estimate": {"calls": 1, "model": profile.model, "profile": profile.name,
                                        "adapter": profile.adapter}},
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


class AnnotateParams(SourceParams):
    action: str = Field(..., description="keep, remove, correct, add, ignore")
    scope: str = Field("source", description="occurrence, source (défaut) ou world (retenu)")
    ann_id: int | None = None
    passage: int | None = None
    start: int | None = None
    end: int | None = None
    entity: str | None = Field(None, description="identifiant d'entité, ou « new »")
    type: str | None = None


@operation("atelier.annotate", "write", AnnotateParams,
           "atelier : un geste de l'auteur (garder, retirer, corriger, ajouter, ignorer) et sa portée",
           ("I-ATL-03", "R-HIS-01"))
def atelier_annotate(ctx: Context, p: AnnotateParams) -> Output:
    from worldkit.atelier import gestures
    assert ctx.world is not None
    try:
        written = gestures.gesture(ctx.world, _branch(ctx, p), p.doc_id, p.action, p.scope, p.ann_id, p.passage,
                                   p.start, p.end, p.entity, p.type)
    except ValueError as e:
        return Output(None, [Issue(IssueCode.EDIT_RULE, str(e), "I-ATL-03")])
    return Output({"written": written}, [], {"written": len(written)})


@operation("atelier.propose", "write", SourceParams,
           "atelier : proposer les entités confirmées et les alias retenus (un lot, jusqu'à la revue)",
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
