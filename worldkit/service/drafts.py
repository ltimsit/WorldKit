"""Pistes d'auteur à l'écran (jalon I10, R-SCN-09 ; I-VUE-13, I-ATL-11) : lister, créer, adopter, écarter.

Une piste est une édition **en attente**, étiquetée `draft`, avec un titre et les entités qu'elle concerne ; l'adopter
l'applique (origine `adopted_draft`), l'écarter l'abandonne (elle reste tracée, R-CYC-04). Elle porte toujours au moins
un changement et ne cite que des entités du monde (décisions de l'auteur, fiche I10).
"""

from __future__ import annotations

from typing import Any, Literal

import yaml
from pydantic import Field

from worldkit.core.schema import Issue, IssueCode, Severity

from .registry import Output, Params, operation
from .session import Context


class ListParams(Params):
    branch: str | None = None
    status: Literal["open", "all"] = Field("open", description="open : en attente (défaut) ; all : aussi adoptées et écartées")


def _name(state: Any, eid: str) -> str:
    f = state.facts.get(("attr", eid, "name"))
    return str(f.value) if f is not None else eid


@operation("drafts.list", "read", ListParams, "pistes d'auteur : titre, entités, changements, état, source",
           ("R-SCN-09", "R-RED-03"))
def drafts_list(ctx: Context, p: ListParams) -> Output:
    from worldkit.core.journal.models import EditStatus
    from worldkit.ingest.review import describe
    from .ops import in_french
    w = ctx.world
    assert w is not None
    branch = p.branch or w.reference_branch
    state = w.state(branch)
    out = []
    for rec in w.store.edits(branch):
        if "draft" not in rec.edit.tags or (p.status == "open" and rec.status is not EditStatus.PENDING):
            continue
        e = rec.edit
        out.append({"id": e.id, "title": e.title or e.id, "status": str(rec.status), "needs_recheck": rec.needs_recheck,
                    "concerns": [{"id": c, "name": _name(state, c)} for c in e.concerns], "note": e.note,
                    "written_against": rec.base.seq if rec.base else None,
                    "changes": [{"text": describe(c), "in_french": in_french(c, state)} for c in e.changes]})
    out.sort(key=lambda d: (d["status"] != "pending", d["id"]))
    return Output({"branch": branch, "drafts": out}, [],
                  {"open": sum(1 for d in out if d["status"] == "pending"), "shown": len(out)})


class CreateParams(Params):
    title: str
    concerns: list[str] = Field(default_factory=list, description="entités concernées (identifiants)")
    changes: list[dict[str, Any]] | None = Field(None, description="changements (ce que la piste ferait au monde)")
    changes_yaml: str | None = Field(None, description="ou les changements en YAML (liste), comme dans la Saisie")
    note: str | None = Field(None, description="remarque : la source (document, passage) quand elle vient de l'atelier")
    branch: str | None = None
    point: str | int | None = Field(None, description="état contre lequel elle est écrite (défaut : la tête)")
    confirm: bool = Field(False, description="créer la piste (sinon : vérifier, rien n'est écrit)")


def _changes(p: CreateParams) -> list[Any]:
    if p.changes is not None:
        return list(p.changes)
    if p.changes_yaml and p.changes_yaml.strip():
        raw = yaml.safe_load(p.changes_yaml)
        return raw if isinstance(raw, list) else (raw.get("changes", []) if isinstance(raw, dict) else [])
    return []


@operation("drafts.create", "write", CreateParams,
           "créer une piste d'auteur (vérifier, puis confirmer) : titre, entités, au moins un changement",
           ("R-SCN-09", "I-VUE-13"))
def drafts_create(ctx: Context, p: CreateParams) -> Output:
    from worldkit.core.workflows.scenarios import check_author_draft, create_author_draft
    w = ctx.world
    assert w is not None
    try:
        changes = _changes(p)
    except yaml.YAMLError as e:
        return Output(None, [Issue(IssueCode.EDIT_RULE, f"YAML illisible : {e}", "R-EDI-03")])
    edit, issues = check_author_draft(w, p.title, p.concerns, changes, p.branch, p.point)
    if edit is None:
        return Output(None, issues)
    summary = {"id": edit.id, "title": edit.title, "concerns": edit.concerns, "changes": len(edit.changes)}
    if not p.confirm:
        return Output(summary, issues + [Issue(IssueCode.EDIT_RULE, f"créera la piste {edit.id} (en attente) : "
                                               "confirmer", "R-SCN-09", Severity.WARNING)], status="pending")
    outcome = create_author_draft(w, p.title, p.concerns, changes, p.note, p.branch, p.point)
    return Output({**summary, "id": outcome.edit_id, "status": str(outcome.status)}, outcome.issues)


class DraftId(Params):
    id: str


@operation("drafts.adopt", "write", DraftId, "adopter une piste : elle s'applique (origine adopted_draft)",
           ("R-SCN-09", "R-RED-03"))
def drafts_adopt(ctx: Context, p: DraftId) -> Output:
    from worldkit.core.workflows.scenarios import adopt
    assert ctx.world is not None
    outcome = adopt(ctx.world, p.id)
    return Output({"id": outcome.edit_id, "status": str(outcome.status), "seq": outcome.seq}, outcome.issues)


@operation("drafts.discard", "write", DraftId, "écarter une piste : elle est abandonnée, et reste tracée",
           ("R-SCN-09", "R-CYC-04"))
def drafts_discard(ctx: Context, p: DraftId) -> Output:
    w = ctx.world
    assert w is not None
    if "draft" not in w.store.edit(p.id).edit.tags:
        return Output(None, [Issue(IssueCode.EDIT_RULE, "ce n'est pas une piste d'auteur", "R-SCN-09")])
    outcome = w.abandon(p.id)
    return Output({"id": outcome.edit_id, "status": str(outcome.status)}, outcome.issues)
