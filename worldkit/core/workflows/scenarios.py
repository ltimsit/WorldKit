"""M5 : pistes, scénarios, déroulés (cadre de fondation §6.5 ; R-SCN-01 à R-SCN-09, R-CYC-03, R-EDI-08).

- Un **scénario** est rattaché au monde et visible de toutes les branches (R-SCN-03). Il a son propre
  historique de **versions** (R-SCN-04) : une version enregistrée ne se modifie plus, une nouvelle s'ajoute.
- Une **piste de scénario** est un gabarit de changements écrit contre un état de la branche de
  référence (`written_against`). Elle reste disponible après avoir été jouée (R-EDI-08).
- Une **piste d'auteur** (R-SCN-09) est une édition en attente, avec un titre et les entités qu'elle
  concerne ; on l'adopte (origine `adopted_draft`) ou on l'abandonne.
- Un **déroulé** appartient à une branche et référence la version jouée (R-SCN-05). Chaque piste
  confirmée, éventuellement adaptée (l'adaptation appartient au déroulé), et chaque édition libre
  donnent une édition d'origine `scenario_consequence` (R-SCN-06).

Jouer une piste, c'est la confronter, comme une transposition (§6.3), à la tête de la branche :
indépendante, elle s'applique ; dépendante ou contradictoire, elle est signalée et attend une décision
(garder, adapter, écarter). « X suppose Y » et la confirmation de deux alternatives sont signalées,
jamais imposées (R-SCN-07, R-SCN-08).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from worldkit.core.conflicts import check_application
from worldkit.core.conflicts.transposition import Analysis, analyse, keep_changes
from worldkit.core.journal.models import Edit, EditStatus, Origin
from worldkit.core.schema import Change, Issue, IssueCode, Severity, parse_change, read_yaml
from worldkit.core.world import Outcome, World

_DDL = """
CREATE TABLE IF NOT EXISTS scenarios (
    scenario_id TEXT PRIMARY KEY, name TEXT NOT NULL, depends_on TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS scenario_versions (
    scenario_id TEXT NOT NULL, version INTEGER NOT NULL, written_against TEXT NOT NULL,
    changelog TEXT, drafts TEXT NOT NULL, PRIMARY KEY (scenario_id, version));
CREATE TRIGGER IF NOT EXISTS scenario_versions_frozen_u BEFORE UPDATE ON scenario_versions
  BEGIN SELECT RAISE(ABORT, 'R-SCN-04 : une version de scénario ne se modifie pas'); END;
CREATE TRIGGER IF NOT EXISTS scenario_versions_frozen_d BEFORE DELETE ON scenario_versions
  BEGIN SELECT RAISE(ABORT, 'R-SCN-04 : une version de scénario ne se retire pas'); END;
CREATE TABLE IF NOT EXISTS playthroughs (
    playthrough_id TEXT PRIMARY KEY, branch_id TEXT NOT NULL, scenario_id TEXT NOT NULL,
    version INTEGER NOT NULL, opened INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS playthrough_items (
    playthrough_id TEXT NOT NULL, idx INTEGER NOT NULL, kind TEXT NOT NULL, draft_id TEXT,
    adapted INTEGER NOT NULL, edit_id TEXT, outcome TEXT NOT NULL, detail TEXT NOT NULL,
    PRIMARY KEY (playthrough_id, idx));
"""


def ensure_tables(world: World) -> None:
    world.store.conn.executescript(_DDL)


def _warn(code: IssueCode, msg: str, rule: str) -> Issue:
    return Issue(code, msg, rule, Severity.WARNING)


# ---------------------------------------------------------------------------
# Scénarios et versions
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ScenarioDraft:
    id: str
    title: str
    concerns: tuple[str, ...]
    alternatives: tuple[str, ...]
    changes: tuple[Any, ...]


@dataclass(frozen=True)
class ScenarioVersion:
    scenario: str
    name: str
    version: int
    written_against: str
    depends_on: tuple[str, ...]
    drafts: dict[str, ScenarioDraft]


def _drafts_payload(raw: list[dict[str, Any]]) -> str:
    return json.dumps(raw, ensure_ascii=False, sort_keys=True)


def load_scenario(world: World, path: str | Path) -> list[str]:
    """Enregistre les versions d'un scénario ; rend les versions ajoutées. Une version déjà enregistrée
    doit être identique : on ne la réécrit pas, on en ajoute une nouvelle (R-SCN-04)."""
    ensure_tables(world)
    raw = read_yaml(path)
    sid, conn = raw["scenario"], world.store.conn
    added = []
    with conn:
        conn.execute("INSERT INTO scenarios VALUES (?, ?, ?) ON CONFLICT(scenario_id) DO UPDATE SET"
                     " name = excluded.name, depends_on = excluded.depends_on",
                     (sid, raw.get("name", sid), json.dumps(raw.get("depends_on") or [])))
        for v in raw["versions"]:
            for d in v["drafts"]:
                for c in d["changes"]:
                    parse_change(c)  # catalogue fermé (R-EDI-06)
            payload = _drafts_payload(v["drafts"])
            row = conn.execute("SELECT drafts FROM scenario_versions WHERE scenario_id = ? AND version = ?",
                               (sid, v["version"])).fetchone()
            if row is not None:
                if row[0] != payload:
                    raise ValueError(f"{sid} v{v['version']} est déjà enregistrée et diffère : "
                                     "ajouter une nouvelle version (R-SCN-04)")
                continue
            conn.execute("INSERT INTO scenario_versions VALUES (?, ?, ?, ?, ?)",
                         (sid, v["version"], v["written_against"], v.get("changelog"), payload))
            added.append(f"{sid} v{v['version']}")
    return added


def scenario_version(world: World, scenario: str, version: int | None = None) -> ScenarioVersion:
    ensure_tables(world)
    conn = world.store.conn
    head = conn.execute("SELECT name, depends_on FROM scenarios WHERE scenario_id = ?", (scenario,)).fetchone()
    if head is None:
        raise KeyError(f"scénario inconnu : {scenario}")
    row = conn.execute("SELECT version, written_against, drafts FROM scenario_versions WHERE scenario_id = ?"
                       + (" AND version = ?" if version is not None else "") + " ORDER BY version DESC LIMIT 1",
                       (scenario, version) if version is not None else (scenario,)).fetchone()
    if row is None:
        raise KeyError(f"version inconnue : {scenario} v{version}")
    drafts = {}
    for d in json.loads(row[2]):
        drafts[d["id"]] = ScenarioDraft(d["id"], d.get("title", d["id"]), tuple(d.get("concerns") or ()),
                                        tuple(d.get("alternatives") or ()),
                                        tuple(parse_change(c) for c in d["changes"]))
    return ScenarioVersion(scenario, head[0], row[0], row[1], tuple(json.loads(head[1])), drafts)


def scenarios(world: World) -> list[tuple[str, str, list[int], list[str]]]:
    ensure_tables(world)
    out = []
    for sid, name, deps in world.store.conn.execute("SELECT scenario_id, name, depends_on FROM scenarios ORDER BY 1"):
        versions = [v for (v,) in world.store.conn.execute(
            "SELECT version FROM scenario_versions WHERE scenario_id = ? ORDER BY version", (sid,))]
        out.append((sid, name, versions, json.loads(deps)))
    return out


# ---------------------------------------------------------------------------
# Pistes d'auteur (R-SCN-09)
# ---------------------------------------------------------------------------

def load_author_drafts(world: World, path: str | Path, branch: str | None = None) -> list[Outcome]:
    """Chaque piste devient une édition en attente, écrite contre son point (`written_against`)."""
    raw = read_yaml(path)
    out = []
    for d in raw["drafts"]:
        edit = Edit(id=d["id"], branch=branch or world.reference_branch, title=d.get("title"),
                    concerns=list(d.get("concerns") or []), tags=["draft"], note=d.get("note"),
                    changes=[parse_change(c) for c in d["changes"]])
        out.append(world.submit(edit, d.get("written_against")))
    return out


def adopt(world: World, draft_id: str) -> Outcome:
    """Adopter une piste d'auteur : elle est appliquée, d'origine `adopted_draft` (§6.1)."""
    rec = world.store.edit(draft_id)
    if "draft" not in rec.edit.tags:
        return Outcome(draft_id, [Issue(IssueCode.EDIT_RULE, "ce n'est pas une piste d'auteur", "R-SCN-09")])
    moved = f"{draft_id}@{world.reference_branch}"
    if rec.status is EditStatus.ABANDONED and world.store.has_edit(moved):
        return Outcome(draft_id, [Issue(IssueCode.EDIT_RULE, f"piste déplacée par un rejeu : adopter {moved}",
                                        "R-RED-03")])
    if rec.status is EditStatus.PENDING:
        with world.store.conn:
            world.store.set_origin(draft_id, Origin.ADOPTED_DRAFT.value)
    outcome = world.confirm(draft_id)
    if outcome.status is EditStatus.PENDING and any(i.code == IssueCode.STALE_EDIT for i in outcome.issues):
        world.rebase(draft_id)  # T-ING-06 : requalifiée contre la tête, puis confirmée si elle s'applique
        outcome = world.confirm(draft_id)
    return outcome


# ---------------------------------------------------------------------------
# Déroulés
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Confirmation:
    draft: str
    changes: tuple[Any, ...] | None = None   # adaptation propre au déroulé (R-EDI-08)
    decision: str = "auto"                   # auto | keep | skip, en cas de conflit


@dataclass
class PlayItem:
    kind: str                 # "draft" | "free"
    draft: str | None
    title: str
    adapted: bool
    outcome: str              # applied | conflict | skipped | refused
    edit_id: str | None = None
    analysis: Analysis | None = None
    issues: list[Issue] = field(default_factory=list)


@dataclass
class PlayReport:
    playthrough: str
    branch: str
    scenario: str
    version: int
    warnings: list[Issue] = field(default_factory=list)
    items: list[PlayItem] = field(default_factory=list)


def played_on(world: World, branch: str) -> set[str]:
    """Scénarios dont un déroulé a appliqué au moins une édition dans la lignée de la branche."""
    ensure_tables(world)
    lineage = {edit_id for _, edit_id in world.store.journal_ids(branch)}
    out = set()
    for pid, sid in world.store.conn.execute("SELECT playthrough_id, scenario_id FROM playthroughs"):
        edits = {e for (e,) in world.store.conn.execute(
            "SELECT edit_id FROM playthrough_items WHERE playthrough_id = ? AND outcome = 'applied'", (pid,))}
        if edits & lineage:
            out.add(sid)
    return out


def play(world: World, playthrough: str, scenario: str, version: int, confirmations: list[Confirmation],
         free_edits: list[tuple[str, list[Any]]] | None = None, branch: str | None = None) -> PlayReport:
    """Joue un déroulé sur une branche (R-SCN-05, R-SCN-06, R-SCN-08)."""
    ensure_tables(world)
    branch = branch or world.reference_branch
    sv = scenario_version(world, scenario, version)
    conn = world.store.conn
    if conn.execute("SELECT 1 FROM playthroughs WHERE playthrough_id = ?", (playthrough,)).fetchone():
        raise ValueError(f"déroulé déjà joué : {playthrough}")
    report = PlayReport(playthrough, branch, scenario, sv.version)

    already = played_on(world, branch)
    for dep in sv.depends_on:
        if dep not in already:
            report.warnings.append(_warn(IssueCode.SCENARIO_DEPENDENCY,
                                         f"« {scenario} suppose {dep} » : aucun déroulé de {dep} dans l'histoire de "
                                         f"la branche {branch} (signalé, non imposé)", "R-SCN-07"))
    chosen = [c.draft for c in confirmations]
    for c in chosen:
        for alt in sv.drafts[c].alternatives if c in sv.drafts else ():
            if alt in chosen and c < alt:
                report.warnings.append(_warn(IssueCode.SCENARIO_DEPENDENCY,
                                             f"{c} et {alt} sont des alternatives, confirmées dans le même déroulé",
                                             "R-CYC-03"))

    with conn:
        conn.execute("INSERT INTO playthroughs VALUES (?, ?, ?, ?, ?)",
                     (playthrough, branch, scenario, sv.version, world.store.head_seq(branch)))
    written = world.resolve_point(sv.written_against, world.reference_branch)
    before = world.state(world.reference_branch, written)
    for conf in confirmations:
        draft = sv.drafts.get(conf.draft)
        if draft is None:
            report.items.append(PlayItem("draft", conf.draft, conf.draft, False, "refused",
                                         issues=[Issue(IssueCode.EDIT_RULE, f"piste inconnue : {conf.draft}", "R-SCN-01")]))
            continue
        report.items.append(_play_draft(world, report, sv, draft, conf, before))
    for n, (title, changes) in enumerate(free_edits or [], start=1):
        edit = Edit(id=f"{playthrough}.libre{n}", branch=branch, origin=Origin.SCENARIO_CONSEQUENCE, title=title,
                    tags=["scenario", scenario, playthrough, "free"], changes=list(changes))
        outcome = world.apply(edit)
        report.items.append(PlayItem("free", None, title, False, "applied" if outcome.status else "refused",
                                     edit.id if outcome.status else None, None, outcome.issues))
    with conn:
        for i, item in enumerate(report.items):
            detail = "; ".join(d.describe() for d in item.analysis.divergences) if item.analysis else ""
            detail = detail or "; ".join(str(x) for x in item.issues)
            conn.execute("INSERT INTO playthrough_items VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                         (playthrough, i, item.kind, item.draft, int(item.adapted), item.edit_id, item.outcome, detail))
    return report


def _play_draft(world: World, report: PlayReport, sv: ScenarioVersion, draft: ScenarioDraft, conf: Confirmation,
                before: Any) -> PlayItem:
    changes = list(conf.changes) if conf.changes is not None else list(draft.changes)
    adapted = conf.changes is not None
    item = PlayItem("draft", draft.id, draft.title, adapted, "skipped")
    if conf.decision == "skip":
        return item
    supposed = check_application(changes, before, draft.id)  # ce que la piste suppose, à son point d'écriture
    if not supposed.applicable or supposed.state is None:
        item.outcome, item.issues = "refused", supposed.issues
        return item
    head = world.state(report.branch)
    analysis = analyse(draft.id, world.reference_branch, before.seq + 1, before, supposed.state, report.branch, head,
                       supposed.effects.reads, supposed.effects.writes)
    item.analysis = analysis
    if analysis.relation != "independent":
        if conf.decision != "keep" or analysis.missing:
            item.outcome = "conflict"
            return item
        changes, _ = keep_changes(analysis, changes, head)
    edit = Edit(id=f"{report.playthrough}.{draft.id}", branch=report.branch, origin=Origin.SCENARIO_CONSEQUENCE,
                title=draft.title, concerns=list(draft.concerns),
                tags=["scenario", sv.scenario, f"v{sv.version}", report.playthrough] + (["adapted"] if adapted else []),
                changes=changes)
    outcome = world.apply(edit)
    item.issues = outcome.issues
    if outcome.status is EditStatus.APPLIED:
        item.outcome, item.edit_id = "applied", edit.id
    else:
        item.outcome = "refused"
    return item


def load_playthrough(path: str | Path, playthrough: str) -> tuple[str, int, str | None, list[Confirmation],
                                                               list[tuple[str, list[Any]]]]:
    """Lit un déroulé au format du corpus (`playthroughs.yaml`)."""
    raw = read_yaml(path)
    spec = next((p for p in raw["playthroughs"] if p["id"] == playthrough), None)
    if spec is None:
        raise KeyError(f"déroulé inconnu dans {path} : {playthrough}")
    confirmations = [Confirmation(c["draft"], tuple(parse_change(x) for x in c["changes"])
                                  if c.get("adapted") and c.get("changes") else None)
                     for c in spec.get("confirmed") or []]
    free = [(f.get("title", "édition libre"), [parse_change(x) for x in f["changes"]])
            for f in spec.get("free_edits") or []]
    return spec["scenario"], spec["version"], spec.get("branch"), confirmations, free


# ---------------------------------------------------------------------------
# Pistes ouvertes, pour les pages (R-VUE-02)
# ---------------------------------------------------------------------------

def open_drafts(world: World, branch: str | None = None) -> dict[str, list[str]]:
    """Entité → pistes qui la concernent : pistes d'auteur en attente sur la branche, et pistes des
    scénarios (dernière version), qui restent disponibles après avoir été jouées."""
    branch = branch or world.reference_branch
    out: dict[str, list[str]] = {}
    for rec in world.store.edits(branch, EditStatus.PENDING):
        if "draft" in rec.edit.tags:
            for e in rec.edit.concerns:
                out.setdefault(e, []).append(f"{rec.edit.id} — {rec.edit.title or ''} (piste d'auteur)")
    for sid, _, versions, _ in scenarios(world):
        if not versions:
            continue
        sv = scenario_version(world, sid)
        for d in sv.drafts.values():
            for e in d.concerns:
                out.setdefault(e, []).append(f"{d.id} — {d.title} ({sv.name} v{sv.version})")
    return {e: sorted(v) for e, v in out.items()}
