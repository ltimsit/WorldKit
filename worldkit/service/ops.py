"""Opérations du service, jalon I1 (cadre d'interface §3, §8 ; fiche `docs/i1-brief.md`).

Chaque fonction appelle le code métier existant et met en forme sa réponse ; aucune règle du domaine n'est
recalculée ici (I-PRI-02). Les paramètres sont des modèles pydantic : un paramètre inconnu est refusé.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field

from worldkit.core.journal.models import EditStatus, parse_edit
from worldkit.core.schema import Issue, IssueCode

from .registry import REGISTRY, Output, Params, describe, operation
from .session import Context

FilterName = Literal["author", "player"]


def _branch(ctx: Context, branch: str | None) -> str:
    assert ctx.world is not None
    return branch or ctx.world.reference_branch


def _view(ctx: Context, flt: str, branch: str | None, point: str | int | None) -> Any:
    from worldkit.core.views import Filter, View
    from worldkit.core.workflows.scenarios import open_drafts
    from worldkit.ingest.review import sources
    w = ctx.world
    assert w is not None
    b = _branch(ctx, branch)
    state = w.state(b, point)
    return View(state, Filter(flt), sources(w, b), w.redefined_after(b, state.seq), open_drafts(w, b)), state


class NoParams(Params):
    pass


class Where(Params):
    branch: str | None = Field(None, description="branche (défaut : référence)")
    point: str | int | None = Field(None, description="rang, point nommé (@base) ou head")


# ---------------------------------------------------------------------------
# Consultations du monde
# ---------------------------------------------------------------------------

@operation("world.summary", "read", NoParams, "monde : branches, compteurs, signalements, questions ouvertes")
def world_summary(ctx: Context, p: NoParams) -> Output:
    from worldkit.core.views import state_report
    from worldkit.core.workflows import replay as R
    from worldkit.ingest.meta import open_questions
    from worldkit.ingest.queue import load
    from worldkit.ingest.review import orphan_facts
    w = ctx.world
    assert w is not None
    ref = w.reference_branch
    state = w.state(ref)
    by_visibility: dict[str, int] = {}
    for f in state.facts.values():
        by_visibility[str(f.visibility)] = by_visibility.get(str(f.visibility), 0) + 1
    signals = R.lineage_notices(w, ref) + state_report(state) + orphan_facts(w, ref)
    families: dict[str, int] = {}
    for i in signals:
        families[str(i.code)] = families.get(str(i.code), 0) + 1
    pending = load(w, ref)
    value = {"world": w.decl.world, "reference_branch": ref, "head": state.seq,
             "branches": [{"id": b, "status": w.store.branch_status(b), "head": w.store.head_seq(b)}
                          for b in w.store.branches()]}
    indicators = {
        "entities": len(state.entities), "facts": len(state.facts), "facts_by_visibility": by_visibility,
        "claims": len(state.claims), "pending_proposals": len(pending),
        "pending_edits": len(w.store.edits(ref, EditStatus.PENDING)) - len(pending),
        "nature_questions": len(open_questions(w, ref)),
        "open_replays": sum(1 for r in R.replays(w) if r.status == R.OPEN),
        "signals": families,
    }
    return Output(value, [], indicators)


@operation("branch.list", "read", NoParams, "branches : parente, divergence, tête, statut", ("R-HIS-03", "R-MON-02"))
def branch_list(ctx: Context, p: NoParams) -> Output:
    w = ctx.world
    assert w is not None
    out = []
    for b in w.store.branches():
        parent, fork = w.store.branch_info(b)
        out.append({"id": b, "parent": parent, "fork_seq": fork if parent else None, "head": w.store.head_seq(b),
                    "status": w.store.branch_status(b), "reference": b == w.reference_branch,
                    "points": w.store.named_points(b)})
    history = [{"rank": r, "branch": b, "replay": rp} for r, b, rp in w.store.reference_history()]
    return Output({"branches": out, "reference_history": history}, [], {"branches": len(out)})


class JournalParams(Params):
    branch: str | None = None
    after: int = 0
    limit: int | None = None


@operation("journal.list", "read", JournalParams, "journal d'une branche (lignée comprise)", ("R-HIS-02",))
def journal_list(ctx: Context, p: JournalParams) -> Output:
    w = ctx.world
    assert w is not None
    b = _branch(ctx, p.branch)
    rows = []
    for seq, edit_id in w.store.journal_ids(b, after=p.after):
        rec = w.store.edit(edit_id)
        e = rec.edit
        rows.append({"seq": seq, "edit": edit_id, "branch": e.branch, "origin": e.origin, "redefinition": e.redefinition,
                     "tags": e.tags, "title": e.title, "changes": len(e.changes), "reads": len(rec.reads),
                     "writes": len(rec.writes), "transposed_from": e.transposed_from, "derived_from": e.derived_from})
    if p.limit:
        rows = rows[-p.limit:]
    return Output({"branch": b, "entries": rows}, [], {"entries": len(rows)})


class EditId(Params):
    id: str


@operation("edit.show", "read", EditId, "une édition : changements, statut, base, lectures, écritures", ("R-EDI-03",))
def edit_show(ctx: Context, p: EditId) -> Output:
    w = ctx.world
    assert w is not None
    rec = w.store.edit(p.id)
    return Output({"edit": rec.edit, "status": rec.status, "base": rec.base, "reads": rec.reads,
                   "writes": rec.writes, "needs_recheck": rec.needs_recheck, "located": w.store.locate(p.id)})


class PageParams(Where):
    entity: str
    filter: FilterName = "author"


@operation("wiki.page", "read", PageParams, "page de wiki d'une entité (auteur ou joueur), rendue et structurée",
           ("R-VUE-01", "R-VUE-02", "R-VUE-03", "R-NOT-03"))
def wiki_page(ctx: Context, p: PageParams) -> Output:
    from worldkit.core.views import render_page
    view, state = _view(ctx, p.filter, p.branch, p.point)
    page = view.page(p.entity)
    if page is None:
        return Output(None, [Issue(IssueCode.UNKNOWN_ENTITY, f"aucune page « {p.entity} » dans cette vue "
                                   f"({p.filter}, {state.branch}, rang {state.seq})", "R-VUE-01")])
    return Output({"branch": state.branch, "seq": state.seq, "page": page, "markdown": render_page(page, view)})


class IndexParams(Where):
    filter: FilterName = "author"


@operation("wiki.index", "read", IndexParams, "pages visibles dans une vue", ("R-VUE-01", "R-NOT-03"))
def wiki_index(ctx: Context, p: IndexParams) -> Output:
    view, state = _view(ctx, p.filter, p.branch, p.point)
    pages = [{"id": e, "title": view.title(e), "type": state.entities[e].type} for e in view.entity_ids()]
    return Output({"branch": state.branch, "seq": state.seq, "filter": p.filter, "pages": pages}, [],
                  {"pages": len(pages)})


@operation("state.check", "read", Where, "signalements d'un état : lignée, conformité, faits masqués, orphelins",
           ("R-CON-04", "R-MET-06", "R-NOT-07", "R-FAI-06", "R-RED-04"))
def state_check(ctx: Context, p: Where) -> Output:
    from worldkit.core.views import state_report
    from worldkit.core.workflows.replay import lineage_notices
    from worldkit.ingest.review import orphan_facts
    w = ctx.world
    assert w is not None
    b = _branch(ctx, p.branch)
    state = w.state(b, p.point)
    issues = lineage_notices(w, b) + state_report(state)
    if p.point in (None, "head"):
        issues += orphan_facts(w, b)
    return Output({"branch": b, "seq": state.seq}, issues, {"signals": len(issues)}, status="ok")


class ExportParams(Where):
    filter: FilterName = "player"


@operation("export.graph", "read", ExportParams, "graphe filtré (entités, relations, fiches, affirmations)",
           ("R-LLM-01", "R-NOT-03"))
def export_graph_op(ctx: Context, p: ExportParams) -> Output:
    from worldkit.core.views import Filter, export_graph
    w = ctx.world
    assert w is not None
    graph = export_graph(w.state(_branch(ctx, p.branch), p.point), Filter(p.filter))
    return Output(graph, [], {"entities": len(graph["entities"]), "relations": len(graph["relations"])})


class ReviewParams(Params):
    batch: str | None = None
    branch: str | None = None
    awaiting: bool = Field(False, description="montrer aussi les propositions bloquées par une question de nature")


@operation("review.list", "read", ReviewParams, "file de revue : propositions, questions de nature, passages signalés",
           ("T-ING-06", "R-DEC-02"))
def review_list(ctx: Context, p: ReviewParams) -> Output:
    from worldkit.ingest.meta import open_questions
    from worldkit.ingest.review import flagged_passages, proposals, supports
    w = ctx.world
    assert w is not None
    views = proposals(w, p.batch, branch=p.branch, awaiting=p.awaiting)
    items = [{"id": v.id, "batch": v.batch, "doc": v.doc, "passage": v.passage, "subject": v.subject, "kind": v.kind,
              "tags": v.tags, "needs_recheck": v.needs_recheck, "blocked": v.blocked, "depends_on": v.depends_on,
              "issues": v.issues,
              "changes": [{"text": c.text, "tags": c.tags, "state": c.state, "detail": c.detail} for c in v.changes]}
             for v in views]
    questions = [{"document": d, "passage": i, "subjects": s} for d, i, _, s in open_questions(w, p.branch)]
    flagged = [{"document": d, "passage": i, "flags": f} for d, i, f in flagged_passages(w, p.batch)]
    tags: dict[str, int] = {}
    for it in items:
        for t in it["tags"]:
            tags[t] = tags.get(t, 0) + 1
    return Output({"proposals": items, "nature_questions": questions, "flagged_passages": flagged}, [],
                  {"proposals": len(items), "by_tag": tags, "nature_questions": len(questions),
                   "supports": len(supports(w, p.batch))})


# ---------------------------------------------------------------------------
# Calcul : vérifier une édition sans l'appliquer
# ---------------------------------------------------------------------------

class EditParams(Params):
    edit: dict[str, Any] = Field(description="édition au format du corpus (id, origin, changes…)")
    point: str | int | None = Field(None, description="état contre lequel vérifier (défaut : tête)")


def _parse(ctx: Context, raw: dict[str, Any]) -> Any:
    assert ctx.world is not None
    return parse_edit({"branch": ctx.world.reference_branch, **raw})


def _diff(before: Any, after: Any) -> dict[str, list[Any]]:
    """Faits ajoutés, retirés, modifiés entre deux états (pour montrer l'effet d'une édition)."""
    added = [f for fid, f in after.facts.items() if fid not in before.facts]
    removed = [f for fid, f in before.facts.items() if fid not in after.facts]
    changed = [{"before": before.facts[fid], "after": f} for fid, f in after.facts.items()
               if fid in before.facts and (before.facts[fid].value, before.facts[fid].visibility)
               != (f.value, f.visibility)]
    return {"added": sorted(added, key=lambda f: repr(f.id)), "removed": sorted(removed, key=lambda f: repr(f.id)),
            "changed": changed}


@operation("edit.check", "compute", EditParams, "vérifier une édition contre un état, sans rien écrire",
           ("R-FAI-05", "R-EDI-03", "R-SCH-06"))
def edit_check(ctx: Context, p: EditParams) -> Output:
    from worldkit.core.conflicts import check_application
    from worldkit.core.journal.models import edit_rule_issues
    from worldkit.core.schema import fact_keys
    from worldkit.core.schema.keys import UnknownRelation
    w = ctx.world
    assert w is not None
    edit = _parse(ctx, p.edit)
    state = w.state(edit.branch, p.point)
    app = check_application(edit.changes, state, edit.id)
    ctxs = state.context()
    keys = []
    for i, c in enumerate(edit.changes):
        try:
            keys.append({"index": i, "op": c.op, "keys": fact_keys(c, ctxs)})
        except UnknownRelation:
            keys.append({"index": i, "op": c.op, "keys": []})
    value = {"edit": edit.id, "branch": edit.branch, "seq": state.seq, "applicable": app.applicable,
             "keys": keys, "reads": app.effects.reads, "writes": app.effects.writes,
             "diff": _diff(state, app.state) if app.state is not None else None}
    return Output(value, edit_rule_issues(edit) + app.issues,
                  {"changes": len(edit.changes), "reads": len(app.effects.reads), "writes": len(app.effects.writes)})


# ---------------------------------------------------------------------------
# Écritures
# ---------------------------------------------------------------------------

@operation("edit.apply", "write", EditParams, "appliquer une édition (vérifiée contre la tête)", ("R-FAI-05", "R-EDI-05"))
def edit_apply(ctx: Context, p: EditParams) -> Output:
    assert ctx.world is not None
    outcome = ctx.world.apply(_parse(ctx, p.edit))
    return Output({"edit": outcome.edit_id, "status": outcome.status, "seq": outcome.seq}, outcome.issues)


@operation("edit.submit", "write", EditParams, "mettre une édition en attente, écrite contre un point",
           ("T-ING-01", "R-SCH-06"))
def edit_submit(ctx: Context, p: EditParams) -> Output:
    assert ctx.world is not None
    outcome = ctx.world.submit(_parse(ctx, p.edit), p.point)
    return Output({"edit": outcome.edit_id, "status": outcome.status}, outcome.issues,
                  status="pending" if outcome.status is EditStatus.PENDING else None)


class IngestParams(Params):
    batch_id: str
    documents: list[str] = Field(default_factory=list, description="fichiers ; sinon ceux du lot dans `batches`")
    batches: str | None = Field(None, description="batches.yaml")
    batch: str | None = Field(None, description="lot déclaré dans batches.yaml (défaut : batch_id)")
    oracle: str = Field(description="dossier gold/ de l'extracteur oracle (le LLM arrive avec I4, I-LLM-01)")
    branch: str | None = None


@operation("ingest.batch", "write", IngestParams, "ingérer un lot (propositions en attente)",
           ("R-DOC-01", "T-ING-01", "T-ING-07", "T-ING-20"))
def ingest_batch(ctx: Context, p: IngestParams) -> Output:
    from pathlib import Path
    from worldkit.ingest.batch import batch_documents, ingest
    from worldkit.periphery.extraction import OracleExtractor
    assert ctx.world is not None
    paths = list(p.documents) or (batch_documents(p.batches, p.batch or p.batch_id) if p.batches else [])
    if not paths:
        raise ValueError("aucun document : donner `documents`, ou `batches` et `batch`")
    r = ingest(ctx.world, p.batch_id, paths, OracleExtractor(Path(p.oracle)), p.branch)
    value = {"batch": r.batch_id, "base": r.base, "documents": r.documents,
             "proposals": [q.id for q in r.proposals], "new_entities": r.new_entities, "flagged": r.flagged,
             "obsolete": r.obsolete, "errors": r.errors}
    indicators = {"passages_extracted": r.extracted, "passages_cached": r.cached, "passages_unchanged": r.unchanged,
                  "passages_removed": r.removed, "proposals": len(r.proposals), "supports": len(r.supports),
                  "new_entities": len(r.new_entities), "remembered": r.remembered, "errors": len(r.errors),
                  "flags": {f: sum(1 for fl in r.flagged.values() if f in fl)
                            for f in sorted({f for fl in r.flagged.values() for f in fl})}}
    return Output(value, [], indicators)


class AcceptParams(Params):
    proposals: list[str]
    keep: list[int] | None = None
    drop_optional: bool = False
    reason: str | None = None


def _decided(results: list[Any]) -> Output:
    issues = [i for d in results for i in d.issues]
    return Output([{"proposal": d.proposal, "action": d.action, "edit": d.edit_id, "seq": d.seq, "ok": d.ok}
                   for d in results], issues)


@operation("review.accept", "write", AcceptParams, "accepter des propositions (entièrement, ou --keep)",
           ("R-EDI-08", "R-PRI-04", "T-ING-04"))
def review_accept(ctx: Context, p: AcceptParams) -> Output:
    from worldkit.ingest import decide
    assert ctx.world is not None
    return _decided([decide.accept(ctx.world, pid, p.keep, p.drop_optional, p.reason) for pid in p.proposals])


class RefuseParams(Params):
    proposals: list[str]
    changes: list[int] | None = None
    reason: str | None = None


@operation("review.refuse", "write", RefuseParams, "refuser des propositions (entièrement, ou certains changements)",
           ("R-PRI-04", "R-CYC-02"))
def review_refuse(ctx: Context, p: RefuseParams) -> Output:
    from worldkit.ingest import decide
    assert ctx.world is not None
    return _decided([decide.refuse(ctx.world, pid, p.changes, p.reason) for pid in p.proposals])


class NatureParams(Params):
    document: str
    passage: int
    decision: Literal["accept", "refuse"]
    reason: str | None = None


@operation("review.nature", "write", NatureParams, "trancher une nature méta détectée", ("R-DEC-02", "R-DEC-04"))
def review_nature(ctx: Context, p: NatureParams) -> Output:
    from worldkit.ingest.meta import decide_nature
    assert ctx.world is not None
    ids = decide_nature(ctx.world, p.document, p.passage, p.decision == "accept", p.reason)
    return Output({"document": p.document, "passage": p.passage, "decision": p.decision, "proposals": ids})


# ---------------------------------------------------------------------------
# Session : bacs à sable, exécutions, opérations
# ---------------------------------------------------------------------------

class SandboxCreate(Params):
    origin: str = Field("world", description="world, ou le numéro d'un bac à dupliquer")
    note: str | None = None


@operation("sandbox.create", "admin", SandboxCreate, "créer un bac à sable (copie du monde ou d'un bac)",
           ("I-SBX-01",), needs_world=False)
def sandbox_create(ctx: Context, p: SandboxCreate) -> Output:
    return Output(ctx.session.create_sandbox(p.origin, p.note))


class SandboxList(Params):
    all: bool = Field(False, description="inclure les bacs jetés")


@operation("sandbox.list", "read", SandboxList, "bacs à sable du monde", ("I-SBX-01",), needs_world=False)
def sandbox_list(ctx: Context, p: SandboxList) -> Output:
    boxes = ctx.session.runs.sandboxes(include_dropped=p.all)
    return Output(boxes, [], {"sandboxes": len(boxes)})


class SandboxId(Params):
    id: int


@operation("sandbox.drop", "admin", SandboxId, "jeter un bac à sable (ses exécutions restent)", ("I-SBX-01",),
           needs_world=False)
def sandbox_drop(ctx: Context, p: SandboxId) -> Output:
    return Output(ctx.session.drop_sandbox(p.id))


class RunsList(Params):
    limit: int | None = 20
    target: str | None = None
    operation: str | None = None


@operation("runs.list", "read", RunsList, "exécutions enregistrées, les plus récentes d'abord", ("I-RUN-01",),
           needs_world=False)
def runs_list(ctx: Context, p: RunsList) -> Output:
    from .session import parse_target
    target = parse_target(p.target) if p.target else None
    rows = ctx.session.runs.runs(p.limit, target, p.operation)
    return Output(rows, [], {"runs": len(rows)})


class RunId(Params):
    id: int


@operation("runs.show", "read", RunId, "le résultat complet d'une exécution enregistrée", ("I-RUN-01",),
           needs_world=False)
def runs_show(ctx: Context, p: RunId) -> Output:
    return Output(ctx.session.runs.result(p.id))


class RunsPurge(Params):
    ids: list[int] = Field(default_factory=list)
    before: int | None = None
    all: bool = False


@operation("runs.purge", "admin", RunsPurge, "purger des exécutions (sans effet sur le monde)", ("I-RUN-01",),
           needs_world=False)
def runs_purge(ctx: Context, p: RunsPurge) -> Output:
    if not (p.ids or p.before is not None or p.all):
        raise ValueError("purge : donner ids, before ou all")
    n = ctx.session.runs.purge(p.ids, p.before, p.all)
    return Output({"purged": n}, [], {"purged": n})


@operation("ops.list", "read", NoParams, "opérations du service : sorte, résumé, règles, paramètres", ("I-CLI-01",),
           needs_world=False)
def ops_list(ctx: Context, p: NoParams) -> Output:
    return Output([describe(op) for _, op in sorted(REGISTRY.items())], [], {"operations": len(REGISTRY)})


# ---------------------------------------------------------------------------
# Comparaison de deux lectures (décision I2 : deux colonnes, différences calculées par le service)
# ---------------------------------------------------------------------------

class Side(Params):
    target: str | int | None = Field(None, description="world, ou le numéro d'un bac")
    branch: str | None = None
    point: str | int | None = None
    filter: FilterName = "author"


class CompareParams(Params):
    entity: str
    left: Side = Field(default_factory=Side)
    right: Side = Field(default_factory=Side)


def _page_in(ctx: Context, entity: str, side: Side) -> tuple[Any, dict[str, Any]]:
    from .session import parse_target
    target = parse_target(side.target)
    world = ctx.session.open(target)
    try:
        inner = Context(ctx.session, target, world)
        view, state = _view(inner, side.filter, side.branch, side.point)
        where = {"target": target, "branch": state.branch, "seq": state.seq, "filter": side.filter}
        return view.page(entity), where
    finally:
        world.close()


def _lines(page: Any) -> dict[tuple[str, str], Any]:
    """Lignes d'une page indexées par (section, identité) : le fait affiché, ou l'affirmation, ou l'identité."""
    import json as _json
    from .result import jsonable
    out: dict[tuple[str, str], Any] = {}
    if page is None:
        return out
    for a in page.attributes:
        out[("attributes", _json.dumps(jsonable(a.fact)))] = a
    for r in page.relations:
        out[("relations", _json.dumps(jsonable(r.fact)))] = r
    for s in page.sheets:
        for a in s.attributes:
            out[("sheets", _json.dumps(jsonable(a.fact)))] = a
        out[("sheet_bindings", s.sheet)] = (s.system, s.category)
    for c in page.claims:
        out[("claims", c.claim)] = c
    for i in page.identities:
        out[("identities", f"{i.other}|{i.kind}")] = i
    return out


def _signature(line: Any) -> Any:
    """Ce qui, dans une ligne, fait qu'elle a « changé » : valeur, notoriété, qualification, cible."""
    for fields in (("value", "visibility"), ("other", "visibility"), ("qualification", "qualification_visibility"),
                   ("visibility",)):
        if all(hasattr(line, f) for f in fields):
            return tuple(str(getattr(line, f)) for f in fields)
    return line


@operation("wiki.compare", "read", CompareParams,
           "deux lectures d'une page côte à côte, avec leurs différences au niveau des faits",
           ("R-VUE-01", "R-VUE-03", "R-NOT-03"), needs_world=False)
def wiki_compare(ctx: Context, p: CompareParams) -> Output:
    left, where_l = _page_in(ctx, p.entity, p.left)
    right, where_r = _page_in(ctx, p.entity, p.right)
    issues = [Issue(IssueCode.UNKNOWN_ENTITY, f"aucune page « {p.entity} » à {side} ({w['target']}, {w['branch']}, "
                    f"rang {w['seq']}, {w['filter']})", "R-VUE-01")
              for side, page, w in (("gauche", left, where_l), ("droite", right, where_r)) if page is None]
    a, b = _lines(left), _lines(right)
    diff = []
    for key in sorted(set(a) | set(b)):
        section, ident = key
        if key not in b:
            diff.append({"section": section, "key": ident, "status": "removed", "left": a[key], "right": None})
        elif key not in a:
            diff.append({"section": section, "key": ident, "status": "added", "left": None, "right": b[key]})
        elif _signature(a[key]) != _signature(b[key]):
            diff.append({"section": section, "key": ident, "status": "changed", "left": a[key], "right": b[key]})
    counts = {s: sum(1 for d in diff if d["status"] == s) for s in ("added", "removed", "changed")}
    return Output({"entity": p.entity, "left": {"where": where_l, "page": left},
                   "right": {"where": where_r, "page": right}, "diff": diff}, issues, counts,
                  status="ok" if left is not None or right is not None else None)
