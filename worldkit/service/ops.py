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
    status, progress = ctx.session.runs.progress(p.id)
    if status in ("running", "interrupted"):  # tâche de fond : pas encore de résultat (décision I4)
        return Output({"run": p.id, "status": status, "progress": progress,
                       "stages": ctx.session.runs.artifact_stages(p.id)}, status="pending")
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
    n = ctx.session.runs.purge(p.ids, p.before, p.all, keep=ctx.run_id)
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


# ---------------------------------------------------------------------------
# Mécanismes du catalogue (cadre d'interface §3 ; banc de mécanismes, décision I3)
# ---------------------------------------------------------------------------

class SchemaParams(Params):
    schema_: dict[str, Any] | None = Field(None, alias="schema", description="schéma en YAML (monde ou système)")
    file: str | None = Field(None, description="ou un fichier de schéma")


@operation("schema.validate", "compute", SchemaParams, "valider un schéma de monde ou de système (validateur unique)",
           ("R-SCH-01", "R-SCH-02", "T-SCH-01"), needs_world=False,
           example={"file": "corpus/valmont-v1/valmont/systems/system-a.yaml"})
def schema_validate(ctx: Context, p: SchemaParams) -> Output:
    from worldkit.core.schema import read_yaml, validate_schema
    doc = p.schema_ if p.schema_ is not None else read_yaml(p.file) if p.file else None
    if doc is None:
        raise ValueError("donner `schema` (YAML) ou `file`")
    issues = validate_schema(doc)
    return Output({"schema": doc.get("schema") if isinstance(doc, dict) else None, "valid": not issues}, issues,
                  {"issues": len(issues)})


class ChangeParams(Where):
    change: dict[str, Any] = Field(description="un changement au format du corpus")


@operation("change.keys", "compute", ChangeParams, "clés de fait d'un changement et sa vérification contre un état",
           ("R-FAI-05", "T-FAI-01", "R-SCH-06"),
           example={"change": {"op": "add_relation", "from": "odon", "relation": "rules", "to": "brume"}})
def change_keys(ctx: Context, p: ChangeParams) -> Output:
    from worldkit.core.schema import fact_keys, format_key, parse_change
    from worldkit.core.schema.check import check_fact_change
    from worldkit.core.schema.keys import UnknownRelation
    w = ctx.world
    assert w is not None
    state = w.state(_branch(ctx, p.branch), p.point)
    change = parse_change(p.change)
    sctx = state.context()
    try:
        keys = fact_keys(change, sctx)
    except UnknownRelation as e:
        return Output({"keys": []}, [Issue(IssueCode.OUT_OF_SCHEMA, str(e), "R-SCH-06")])
    occupied = {format_key(k): state.occupancy.get(k) for k in keys}
    return Output({"keys": keys, "readable": [format_key(k) for k in keys], "occupied_by": occupied},
                  check_fact_change(change, sctx),
                  {"keys": len(keys), "occupied": sum(1 for v in occupied.values() if v)})


class TransposeParams(Params):
    edit: str
    to: str = Field(description="branche cible")


@operation("transpose.analyse", "compute", TransposeParams,
           "une édition confrontée à une autre branche : indépendante, dépendante ou contradictoire",
           ("R-HIS-05", "§6.3"), example={"edit": "e201", "to": "reference"})
def transpose_analyse(ctx: Context, p: TransposeParams) -> Output:
    assert ctx.world is not None
    a = ctx.world.analyse_transposition(p.edit, p.to)
    return Output({"edit": a.edit_id, "source": a.source, "source_seq": a.source_seq, "target": a.target,
                   "relation": a.relation,
                   "divergences": [{"key": d.key, "kind": d.kind, "written": d.written, "text": d.describe()}
                                   for d in a.divergences]},
                  [], {"divergences": len(a.divergences), "relation": a.relation})


class RedefineParams(Params):
    changes: list[dict[str, Any]]
    anchor: str | int = Field(description="édition (e003), rang ou point nommé")
    source: str | None = None


@operation("redefine.preview", "compute", RedefineParams,
           "aperçu d'impact d'une redéfinition rétroactive, sans rien écrire", ("R-RED-01",),
           example={"anchor": "e003", "changes": [
               {"op": "set_attribute", "entity": "aldren-ii", "attribute": "death_cause", "value": "fièvre",
                "visibility": "secret"},
               {"op": "remove_relation", "from": "mervin", "relation": "killed", "to": "aldren-ii"}]})
def redefine_preview(ctx: Context, p: RedefineParams) -> Output:
    from worldkit.core.schema import format_key, parse_change
    from worldkit.core.workflows import replay as R
    assert ctx.world is not None
    impact = R.preview(ctx.world, [parse_change(c) for c in p.changes], p.anchor, p.source)

    def touch(t: Any) -> dict[str, Any]:
        return {"edit": t.edit_id, "seq": t.seq, "title": t.title, "keys": [format_key(k) for k in t.keys]}
    return Output({"source": impact.source, "anchor_seq": impact.anchor_seq,
                   "writes": sorted(format_key(k) for k in impact.writes), "later": impact.later,
                   "edits": [touch(t) for t in impact.edits], "pending": [touch(t) for t in impact.pending]},
                  impact.issues, {"later": impact.later, "edits": len(impact.edits), "pending": len(impact.pending)})


class DocumentParams(Params):
    file: str | None = None
    text: str | None = Field(None, description="ou le texte du document, en-tête compris")


@operation("document.declare", "compute", DocumentParams,
           "déclaration d'un document : axes, passages, segments, empreintes, nature déclarée",
           ("R-DOC-02", "R-ING-01", "R-DEC-01", "R-DEC-04", "T-ING-10"), needs_world=False,
           example={"file": "corpus/valmont-v1/valmont/docs/b4/bestiaire-loup-de-cendre.md"})
def document_declare(ctx: Context, p: DocumentParams) -> Output:
    from worldkit.ingest.declaration import DeclarationError, parse_document, read_document
    from worldkit.ingest.meta import passage_nature
    try:
        doc = read_document(p.file) if p.file else parse_document(p.text or "", "(texte)")
    except DeclarationError as e:
        return Output(None, [Issue(IssueCode.EDIT_RULE, str(e), "R-DOC-02")])
    passages = [{"index": q.index, "fingerprint": q.fingerprint, "nature": passage_nature(doc, q), "text": q.text,
                 "segments": [{"text": s.text, "voice": s.voice, "speaker": s.speaker, "nature": s.nature,
                               "declared_by": s.declared_by} for s in q.segments]} for q in doc.passages]
    natures: dict[str, int] = {}
    for q in passages:
        natures[q["nature"]] = natures.get(q["nature"], 0) + 1
    return Output({"document": doc.doc_id, "title": doc.title, "fingerprint": doc.fingerprint, "axes": doc.axes,
                   "passages": passages}, [], {"passages": len(passages), "natures": natures})


class PromoteParams(Params):
    id: int
    confirm: bool = Field(False, description="appliquer au monde de travail si rien ne diverge")


@operation("sandbox.promote", "admin", PromoteParams,
           "rendre réel un bac : répétition à blanc, puis application en tout ou rien", ("I-SBX-01", "R-HIS-01"),
           needs_world=False)
def sandbox_promote(ctx: Context, p: PromoteParams) -> Output:
    report = ctx.session.promote(p.id, p.confirm)
    if report["divergences"]:
        status = "refused"
    elif report["applied"] or not report["steps"]:
        status = "ok"
    else:
        status = "pending"  # répétition réussie, en attente de confirmation
    issues = [Issue(IssueCode.STALE_EDIT, f"exécution #{s['run']} {s['operation']} : {s['detail']}", "I-SBX-01")
              for s in report["steps"] if s["verdict"] == "divergence"]
    verdicts: dict[str, int] = {}
    for s in report["steps"]:
        verdicts[s["verdict"]] = verdicts.get(s["verdict"], 0) + 1
    return Output(report, issues, {"steps": len(report["steps"]), **verdicts, "applied": len(report["applied"])},
                  status=status)


# Exemples Valmont des opérations existantes, pour le banc de mécanismes (décision I3).
_EXAMPLES: dict[str, dict[str, Any]] = {
    "wiki.page": {"entity": "aldren-ii", "filter": "player"},
    "wiki.compare": {"entity": "aldren-ii", "left": {"filter": "author"}, "right": {"filter": "player"}},
    "edit.check": {"edit": {"id": "essai-1", "origin": "enrichment", "changes": [
        {"op": "add_relation", "from": "mervin", "relation": "rules", "to": "brume"}]}},
    "edit.apply": {"edit": {"id": "essai-1", "origin": "enrichment", "changes": [
        {"op": "set_attribute", "entity": "odon", "attribute": "condition", "value": "las"}]}},
    "edit.show": {"id": "e003"},
    "journal.list": {"limit": 10},
    "ingest.batch": {"batch_id": "b4", "batches": "corpus/valmont-v1/valmont/docs/batches.yaml",
                     "oracle": "corpus/valmont-v1/valmont/gold"},
    "review.nature": {"document": "bestiaire-loup-de-cendre", "passage": 6, "decision": "accept"},
}


def _add_examples() -> None:
    import dataclasses
    for name, example in _EXAMPLES.items():
        REGISTRY[name] = dataclasses.replace(REGISTRY[name], example=example)


_add_examples()


# ---------------------------------------------------------------------------
# Redéfinition rétroactive et rejeu (§6.4, T-RED-01) : écritures rejouables, donc promouvables (I3)
# ---------------------------------------------------------------------------

def _replay_report(report: Any) -> Output:
    r = report.replay
    value = {"replay": r, "replayed": report.replayed, "current": report.current, "carried": report.carried,
             "conflict": None if report.conflict is None else {
                 "edit": report.conflict.edit_id, "relation": report.conflict.relation,
                 "divergences": [{"key": d.key, "kind": d.kind, "written": d.written, "text": d.describe()}
                                 for d in report.conflict.divergences]}}
    status = None
    if r is not None and r.status == "open" and report.conflict is not None and not report.issues:
        status = "pending"  # suspendu sur un conflit : décision humaine attendue (R-RED-02)
    return Output(value, report.issues, {"replayed": len(report.replayed), "carried": len(report.carried)}, status)


class ReplayStart(Params):
    changes: list[dict[str, Any]]
    anchor: str | int = Field(description="édition (e003), rang ou point nommé")
    source: str | None = None
    branch: str | None = Field(None, description="nom de la nouvelle branche (défaut : <source>-<rejeu>)")
    id: str | None = Field(None, description="identifiant du rejeu (défaut : r1, r2…)")
    title: str | None = None
    limit: int | None = Field(None, description="suspendre après N éditions rejouées")


@operation("replay.start", "write", ReplayStart,
           "redéfinition rétroactive : nouvelle branche, redéfinition, rejeu ordonné", ("R-RED-01", "R-RED-02"),
           example={"anchor": "e003", "changes": [
               {"op": "set_attribute", "entity": "aldren-ii", "attribute": "death_cause", "value": "fièvre",
                "visibility": "secret"},
               {"op": "remove_relation", "from": "mervin", "relation": "killed", "to": "aldren-ii"}]})
def replay_start(ctx: Context, p: ReplayStart) -> Output:
    from worldkit.core.schema import parse_change
    from worldkit.core.workflows import replay as R
    assert ctx.world is not None
    return _replay_report(R.start(ctx.world, [parse_change(c) for c in p.changes], p.anchor, source=p.source,
                                  branch=p.branch, replay_id=p.id, title=p.title, limit=p.limit))


class ReplayDecide(Params):
    id: str
    action: Literal["keep", "adapt", "discard"]
    changes: list[dict[str, Any]] | None = None
    reason: str | None = None
    limit: int | None = None


@operation("replay.decide", "write", ReplayDecide, "décision sur l'édition en conflit, puis reprise du rejeu",
           ("R-RED-02", "R-HIS-05"), example={"id": "r1", "action": "keep"})
def replay_decide(ctx: Context, p: ReplayDecide) -> Output:
    from worldkit.core.schema import parse_change
    from worldkit.core.workflows import replay as R
    assert ctx.world is not None
    changes = [parse_change(c) for c in p.changes] if p.changes is not None else None
    return _replay_report(R.decide(ctx.world, p.id, p.action, changes, p.reason, p.limit))


class ReplayId(Params):
    id: str
    limit: int | None = None


@operation("replay.resume", "write", ReplayId, "reprendre un rejeu suspendu", ("R-RED-02",), example={"id": "r1"})
def replay_resume(ctx: Context, p: ReplayId) -> Output:
    from worldkit.core.workflows import replay as R
    assert ctx.world is not None
    return _replay_report(R.advance(ctx.world, p.id, p.limit))


@operation("replay.abandon", "write", ReplayId, "abandonner un rejeu (tout reste tracé)", ("R-RED-02", "R-HIS-01"),
           example={"id": "r1"})
def replay_abandon(ctx: Context, p: ReplayId) -> Output:
    from worldkit.core.workflows import replay as R
    assert ctx.world is not None
    return _replay_report(R.abandon(ctx.world, p.id))


@operation("replay.status", "read", ReplayId, "où en est un rejeu : édition suivante, conflit, pas faits",
           ("R-RED-02",), example={"id": "r1"})
def replay_status(ctx: Context, p: ReplayId) -> Output:
    from worldkit.core.workflows import replay as R
    assert ctx.world is not None
    out = _replay_report(R.pending_conflict(ctx.world, p.id))
    out.value["steps"] = R.steps(ctx.world, p.id)
    return out


# ---------------------------------------------------------------------------
# Revue complète (I-VUE-05, jalon I5)
# ---------------------------------------------------------------------------

class ProposalId(Params):
    proposal: str


@operation("review.show", "read", ProposalId, "une proposition : changements, étiquettes, détail, dépendances",
           ("T-ING-02", "T-ING-05", "T-ING-18"), example={"proposal": "b1.notes-baron.p3.1"})
def review_show(ctx: Context, p: ProposalId) -> Output:
    from worldkit.ingest.meta import awaiting_nature
    from worldkit.ingest.queue import blocked, load_one
    from worldkit.ingest.review import describe as describe_change
    assert ctx.world is not None
    found = load_one(ctx.world, p.proposal)
    if found is None:
        raise KeyError(f"proposition inconnue : {p.proposal}")
    head = ctx.world.state(found.base.branch if found.base else None)
    return Output({"id": found.id, "batch": found.batch, "doc": found.doc, "passage": found.passage,
                   "subject": found.subject, "kind": found.kind, "status": found.status, "base": found.base,
                   "needs_recheck": found.needs_recheck, "depends_on": found.depends_on, "issues": found.issues,
                   "closed_reason": found.closed_reason, "blocked": blocked(head, found.doc),
                   "awaiting_nature": awaiting_nature(ctx.world, found),
                   "changes": [{"index": c.index, "text": describe_change(c.change), "change": c.change,
                                "tags": sorted(c.tags), "detail": c.detail, "state": c.state} for c in found.changes]})


class ChooseParams(Params):
    proposal: str
    reason: str | None = None


@operation("review.choose", "write", ChooseParams,
           "trancher un conflit : accepter cette proposition, refuser celles qui la contredisent",
           ("R-PRI-03", "R-PRI-07"))
def review_choose(ctx: Context, p: ChooseParams) -> Output:
    from worldkit.ingest import decide
    assert ctx.world is not None
    return _decided(decide.choose(ctx.world, p.proposal, p.reason))


class AdaptParams(Params):
    proposal: str
    changes: list[dict[str, Any]]
    replace: bool = Field(False, description="remplacer les changements (sinon : les ajouter avant)")
    reason: str | None = None


@operation("review.adapt", "write", AdaptParams, "confirmer en adaptant : édition dérivée", ("R-EDI-08", "T-ING-04"))
def review_adapt(ctx: Context, p: AdaptParams) -> Output:
    from worldkit.core.schema import parse_change
    from worldkit.ingest import decide
    assert ctx.world is not None
    return _decided([decide.adapt(ctx.world, p.proposal, [parse_change(c) for c in p.changes], p.replace, p.reason)])


class QualifyParams(Params):
    target: str = Field(description="proposition d'affirmation, ou affirmation déjà dans l'état")
    value: Literal["true", "false", "undetermined"]
    visibility: str | None = None
    reason: str | None = None


@operation("review.qualify", "write", QualifyParams, "qualifier une affirmation", ("R-DOC-07", "T-ING-12"))
def review_qualify(ctx: Context, p: QualifyParams) -> Output:
    from worldkit.ingest import decide
    assert ctx.world is not None
    return _decided([decide.qualify(ctx.world, p.target, p.value, p.visibility, p.reason)])


class PromoteClaimParams(Params):
    proposal: str
    visibility: str | None = None
    reason: str | None = None


@operation("review.promote", "write", PromoteClaimParams, "promouvoir une affirmation en fait", ("R-DOC-07",))
def review_promote(ctx: Context, p: PromoteClaimParams) -> Output:
    from worldkit.ingest import decide
    assert ctx.world is not None
    return _decided([decide.promote(ctx.world, p.proposal, p.visibility, p.reason)])


class AbandonParams(Params):
    proposals: list[str]
    reason: str | None = None


@operation("review.abandon", "write", AbandonParams, "abandonner des propositions (tracé)", ("R-CYC-02",))
def review_abandon(ctx: Context, p: AbandonParams) -> Output:
    from worldkit.ingest import decide
    assert ctx.world is not None
    return _decided([decide.abandon(ctx.world, pid, p.reason) for pid in p.proposals])


class DismissParams(Params):
    document: str
    passage: int
    reason: str | None = None


@operation("review.dismiss", "write", DismissParams, "écarter un passage signalé (attribution)", ("R-DEC-03",))
def review_dismiss(ctx: Context, p: DismissParams) -> Output:
    from worldkit.ingest import decide
    assert ctx.world is not None
    decide.dismiss(ctx.world, p.document, p.passage, p.reason)
    return Output({"document": p.document, "passage": p.passage, "dismissed": True})


# ---------------------------------------------------------------------------
# Points, branches, scénarios, pistes, déroulés (parcours exécutables, I5)
# ---------------------------------------------------------------------------

class PointParams(Params):
    name: str
    point: str | int | None = Field(None, description="rang ou point (défaut : tête)")
    branch: str | None = None


@operation("point.set", "write", PointParams, "nommer un rang du journal (@base)", ("T-STO-01",),
           example={"name": "@essai"})
def point_set(ctx: Context, p: PointParams) -> Output:
    assert ctx.world is not None
    seq = ctx.world.set_point(p.name, p.point, p.branch)
    return Output({"name": p.name, "seq": seq, "branch": _branch(ctx, p.branch)})


class BranchCreate(Params):
    name: str
    from_: str | None = Field(None, alias="from", description="branche d'origine (défaut : référence)")
    point: str | int | None = Field(None, description="point de divergence (défaut : tête)")


@operation("branch.create", "write", BranchCreate, "créer une branche depuis un état", ("R-HIS-03", "T-BRA-01"),
           example={"name": "variante-essai", "point": "@base"})
def branch_create(ctx: Context, p: BranchCreate) -> Output:
    assert ctx.world is not None
    seq = ctx.world.create_branch(p.name, p.from_, p.point)
    return Output({"branch": p.name, "from": p.from_ or ctx.world.reference_branch, "fork_seq": seq})


class FilesParams(Params):
    files: list[str]


@operation("scenario.load", "write", FilesParams, "charger des scénarios (versions nouvelles seulement)",
           ("R-SCN-01", "R-SCN-04"))
def scenario_load(ctx: Context, p: FilesParams) -> Output:
    from worldkit.core.workflows import scenarios as S
    assert ctx.world is not None
    return Output({f: S.load_scenario(ctx.world, f) for f in p.files})


class DraftsParams(Params):
    file: str
    branch: str | None = None


@operation("drafts.load", "write", DraftsParams, "charger des pistes d'auteur (éditions en attente)", ("R-SCN-09",))
def drafts_load(ctx: Context, p: DraftsParams) -> Output:
    from worldkit.core.workflows import scenarios as S
    assert ctx.world is not None
    outcomes = S.load_author_drafts(ctx.world, p.file, p.branch)
    return Output([{"edit": o.edit_id, "status": o.status} for o in outcomes], [i for o in outcomes for i in o.issues])


class PlayParams(Params):
    playthrough: str = Field(description="déroulé du fichier (pt-1)")
    file: str = Field(description="fichier des déroulés (playthroughs.yaml)")
    id: str | None = Field(None, description="identifiant du déroulé joué (défaut : celui du fichier)")
    branch: str | None = None
    version: int | None = None
    confirmations: list[dict[str, Any]] | None = Field(None, description="remplace les pistes confirmées du fichier")
    free: list[dict[str, Any]] | None = Field(None, description="remplace les éditions libres du fichier")


@operation("scenario.play", "write", PlayParams, "jouer un déroulé sur une branche", ("R-SCN-05", "R-SCN-06"))
def scenario_play(ctx: Context, p: PlayParams) -> Output:
    from worldkit.core.schema import parse_change
    from worldkit.core.workflows import scenarios as S
    assert ctx.world is not None
    scenario, version, branch, confirmations, free = S.load_playthrough(p.file, p.playthrough)
    if p.confirmations is not None:
        confirmations = [S.Confirmation(c["draft"], tuple(parse_change(x) for x in c["changes"]) if c.get("changes")
                                        else None, c.get("decision", "auto")) for c in p.confirmations]
    if p.free is not None:
        free = [(f.get("title", "édition libre"), [parse_change(x) for x in f["changes"]]) for f in p.free]
    report = S.play(ctx.world, p.id or p.playthrough, scenario, p.version or version, confirmations, free,
                    p.branch or branch)
    items = [{"draft": i.draft, "title": i.title, "outcome": i.outcome, "edit": i.edit_id, "adapted": i.adapted,
              "divergences": [d.describe() for d in i.analysis.divergences] if i.analysis else []}
             for i in report.items]
    return Output({"playthrough": report.playthrough, "branch": report.branch, "scenario": report.scenario,
                   "version": report.version, "items": items}, report.warnings + [x for i in report.items for x in i.issues],
                  {"applied": sum(1 for i in report.items if i.outcome == "applied"),
                   "conflicts": sum(1 for i in report.items if i.outcome == "conflict")})


@operation("replay.list", "read", NoParams, "rejeux rétroactifs du monde : statut, source, nouvelle branche, conflit en cours",
           ("R-RED-02",))
def replay_list(ctx: Context, p: NoParams) -> Output:
    from worldkit.core.workflows import replay as R
    assert ctx.world is not None
    rows = []
    for r in R.replays(ctx.world):
        current = R.pending_conflict(ctx.world, r.id) if r.status == R.OPEN else None
        rows.append({"id": r.id, "source": r.source, "branch": r.branch, "anchor_seq": r.anchor_seq, "status": r.status,
                     "current": current.current if current else None,
                     "conflict": [d.describe() for d in current.conflict.divergences] if current and current.conflict else []})
    return Output(rows, [], {"replays": len(rows), "open": sum(1 for r in rows if r["status"] == R.OPEN)})
