"""Redéfinition rétroactive et rejeu (cadre de fondation §6.4 ; R-RED-01 à R-RED-05, R-HIS-01, R-HIS-03,
R-HIS-04, R-MON-02, T-ING-16).

« Depuis toujours » : rien n'est réécrit, on bifurque. Une **nouvelle branche** part de l'état d'ancrage,
reçoit la redéfinition (origine `redefinition`, `retroactive`), puis chaque édition postérieure de la
branche source y est **rejouée dans l'ordre** : c'est une transposition (§6.3). Indépendante, elle passe
seule ; dépendante ou contradictoire, le rejeu s'arrête et attend une décision humaine (garder, adapter,
écarter).

- **Aperçu d'impact** (R-RED-01) : éditions postérieures et éditions en attente qui lisent ou écrivent une
  clé écrite par la redéfinition.
- **Session de rejeu** (R-RED-02) : tables `replays` et `replay_steps`. Le rejeu est suspendu entre deux
  commandes (ou après `limit` pas), repris par `advance` ou `decide`, abandonné par `abandon`. Les pas sont
  en ajout seul ; seul le statut d'une session ouverte évolue.
- **Finalisation** (§6.4, décisions J7) : la nouvelle branche remplace la source, archivée (consultable,
  plus modifiable) ; si la source était la référence, la nouvelle branche le devient (historique des
  références en ajout seul, R-MON-02). Sont reportés par la correspondance du rejeu : les points nommés, les
  éditions en attente (déplacées comme T-ING-16 ; à revérifier si elles touchent une clé redéfinie ou
  décidée pendant le rejeu, R-RED-03) et les déroulés. Les variantes de la source ne sont pas modifiées
  (R-RED-04) : `lineage_notices` les signale.
- R-RED-05 : une modification de schéma ou de système est une édition comme une autre ; le même rejeu
  s'applique.

Le report des propositions d'ingestion appartient à l'ingestion : elle s'enregistre dans `CARRIERS`
(le noyau n'importe pas la périphérie).
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from worldkit.core.conflicts import Effects, check_application
from worldkit.core.conflicts.transposition import Analysis
from worldkit.core.journal.models import BaseState, Edit, EditStatus, Origin, RedefinitionKind
from worldkit.core.schema import Change, FactKey, Issue, IssueCode, Severity
from worldkit.core.world import World

_DDL = """
CREATE TABLE IF NOT EXISTS replays (
    replay_id TEXT PRIMARY KEY, source TEXT NOT NULL, anchor_seq INTEGER NOT NULL, branch_id TEXT NOT NULL,
    redefinition TEXT NOT NULL, status TEXT NOT NULL);
CREATE TRIGGER IF NOT EXISTS replays_frozen BEFORE UPDATE ON replays WHEN OLD.status <> 'open'
  BEGIN SELECT RAISE(ABORT, 'R-RED-02 : un rejeu terminé ou abandonné ne se modifie pas'); END;
CREATE TRIGGER IF NOT EXISTS replays_no_delete BEFORE DELETE ON replays
  BEGIN SELECT RAISE(ABORT, 'R-HIS-01 : un rejeu reste tracé'); END;
CREATE TABLE IF NOT EXISTS replay_steps (
    replay_id TEXT NOT NULL, source_seq INTEGER NOT NULL, source_edit TEXT NOT NULL, action TEXT NOT NULL,
    result_edit TEXT, writes TEXT NOT NULL, detail TEXT NOT NULL, PRIMARY KEY (replay_id, source_seq));
CREATE TRIGGER IF NOT EXISTS replay_steps_u BEFORE UPDATE ON replay_steps
  BEGIN SELECT RAISE(ABORT, 'R-HIS-01 : un pas de rejeu ne se modifie pas'); END;
CREATE TRIGGER IF NOT EXISTS replay_steps_d BEFORE DELETE ON replay_steps
  BEGIN SELECT RAISE(ABORT, 'R-HIS-01 : un pas de rejeu ne se retire pas'); END;
"""

OPEN, FINISHED, ABANDONED = "open", "finished", "abandoned"


def ensure_tables(world: World) -> None:
    world.store.conn.executescript(_DDL)


def _unwrap(keys: frozenset[FactKey] | set[FactKey]) -> set[FactKey]:
    """Sous-clé de notoriété → sa clé (même convention que la transposition)."""
    return {k[1] if k[0] == "visibility" else k for k in keys}


def _dumps(keys: set[FactKey]) -> str:
    return json.dumps(sorted((list(k) for k in keys), key=repr), ensure_ascii=False)


def _loads(text: str) -> set[FactKey]:
    def tup(x: Any) -> Any:
        return tuple(tup(i) for i in x) if isinstance(x, list) else x
    return {tup(k) for k in json.loads(text)}


# ---------------------------------------------------------------------------
# Aperçu d'impact (R-RED-01)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Touch:
    edit_id: str
    seq: int | None          # rang sur la source ; None pour une édition en attente
    keys: tuple[FactKey, ...]
    title: str | None = None


@dataclass
class Impact:
    source: str
    anchor_seq: int
    writes: set[FactKey] = field(default_factory=set)
    later: int = 0                                         # éditions postérieures à l'ancrage
    edits: list[Touch] = field(default_factory=list)       # … dont celles qui touchent une clé redéfinie
    pending: list[Touch] = field(default_factory=list)     # éditions en attente touchées (pistes, propositions)
    issues: list[Issue] = field(default_factory=list)

    @property
    def applicable(self) -> bool:
        return not any(i.severity is Severity.ERROR for i in self.issues)


def anchor_seq(world: World, anchor: int | str, source: str) -> int:
    """L'ancrage : un rang, un point nommé, ou une édition de la lignée de la source (« après e003 »)."""
    if isinstance(anchor, str) and not anchor.isdigit() and not anchor.startswith("@") and anchor != "head":
        rows = dict((eid, seq) for seq, eid in world.store.journal_ids(source))
        if anchor in rows:
            return rows[anchor]
    return world.resolve_point(anchor, source)


def preview(world: World, changes: list[Change], anchor: int | str, source: str | None = None) -> Impact:
    """Ce qu'une redéfinition rétroactive toucherait, sans rien écrire."""
    source = source or world.reference_branch
    seq = anchor_seq(world, anchor, source)
    impact = Impact(source, seq)
    app = check_application(changes, world.state(source, seq), "redefinition")
    impact.issues = list(app.issues)
    if not app.applicable:
        return impact
    impact.writes = _unwrap(app.effects.writes)
    for s, edit_id in world.store.journal_ids(source, after=seq):
        impact.later += 1
        rec = world.store.edit(edit_id)
        hit = _unwrap(rec.reads | rec.writes) & impact.writes
        if hit:
            impact.edits.append(Touch(edit_id, s, tuple(sorted(hit, key=repr)), rec.edit.title))
    for rec in world.store.edits(source, EditStatus.PENDING):
        hit = _unwrap(rec.reads | rec.writes) & impact.writes
        if hit:
            impact.pending.append(Touch(rec.edit.id, None, tuple(sorted(hit, key=repr)), rec.edit.title))
    return impact


# ---------------------------------------------------------------------------
# Session de rejeu (R-RED-02)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Replay:
    id: str
    source: str
    anchor_seq: int
    branch: str
    redefinition: str
    status: str


@dataclass(frozen=True)
class Step:
    source_seq: int
    source_edit: str
    action: str              # auto | keep | adapt | discard
    result_edit: str | None
    detail: str


@dataclass
class Report:
    replay: Replay | None
    replayed: list[Step] = field(default_factory=list)   # pas faits par cet appel
    conflict: Analysis | None = None                     # édition en attente de décision
    current: str | None = None                           # son identifiant
    issues: list[Issue] = field(default_factory=list)
    carried: list[str] = field(default_factory=list)     # éléments reportés à la finalisation

    @property
    def ok(self) -> bool:
        return not any(i.severity is Severity.ERROR for i in self.issues)


def get(world: World, replay_id: str) -> Replay:
    ensure_tables(world)
    row = world.store.conn.execute("SELECT replay_id, source, anchor_seq, branch_id, redefinition, status"
                                   " FROM replays WHERE replay_id = ?", (replay_id,)).fetchone()
    if row is None:
        raise KeyError(f"rejeu inconnu : {replay_id}")
    return Replay(*row)


def replays(world: World) -> list[Replay]:
    ensure_tables(world)
    return [Replay(*r) for r in world.store.conn.execute(
        "SELECT replay_id, source, anchor_seq, branch_id, redefinition, status FROM replays ORDER BY rowid")]


def steps(world: World, replay_id: str) -> list[Step]:
    ensure_tables(world)
    return [Step(*r) for r in world.store.conn.execute(
        "SELECT source_seq, source_edit, action, result_edit, detail FROM replay_steps WHERE replay_id = ?"
        " ORDER BY source_seq", (replay_id,))]


def _cursor(world: World, r: Replay) -> int:
    row = world.store.conn.execute("SELECT MAX(source_seq) FROM replay_steps WHERE replay_id = ?",
                                   (r.id,)).fetchone()
    return row[0] if row[0] is not None else r.anchor_seq


def _next(world: World, r: Replay) -> tuple[int, str] | None:
    rows = world.store.journal_ids(r.source, after=_cursor(world, r))
    return rows[0] if rows else None


def _record(world: World, r: Replay, seq: int, edit_id: str, action: str, result: str | None, detail: str) -> Step:
    writes = _unwrap(world.store.edit(edit_id).writes) if action != "auto" else set()
    with world.store.conn:
        world.store.conn.execute("INSERT INTO replay_steps VALUES (?, ?, ?, ?, ?, ?, ?)",
                                 (r.id, seq, edit_id, action, result, _dumps(writes), detail))
    return Step(seq, edit_id, action, result, detail)


def _fail(r: Replay | None, message: str, rule: str) -> Report:
    return Report(r, issues=[Issue(IssueCode.EDIT_RULE, message, rule)])


def start(world: World, changes: list[Change], anchor: int | str, *, source: str | None = None,
          branch: str | None = None, replay_id: str | None = None, title: str | None = None,
          note: str | None = None, limit: int | None = None) -> Report:
    """Crée la nouvelle branche à l'ancrage, y applique la redéfinition, puis rejoue (`advance`)."""
    ensure_tables(world)
    source = source or world.reference_branch
    if source not in world.store.branches():
        return _fail(None, f"branche inconnue : {source}", "T-BRA-01")
    if world.store.branch_status(source) != "active":
        return _fail(None, f"branche {source} non active : on ne redéfinit pas une branche archivée", "R-HIS-04")
    if any(r.source == source and r.status == OPEN for r in replays(world)):
        return _fail(None, f"un rejeu est déjà ouvert sur {source}", "R-RED-02")
    seq = anchor_seq(world, anchor, source)
    n = world.store.conn.execute("SELECT COUNT(*) FROM replays").fetchone()[0] + 1
    replay_id = replay_id or f"r{n}"
    branch = branch or f"{source}-{replay_id}"
    app = check_application(changes, world.state(source, seq), replay_id)
    if not app.applicable:
        return Report(None, issues=app.issues)
    world.create_branch(branch, source, seq)
    red = Edit(id=f"{replay_id}.redefinition", branch=branch, origin=Origin.REDEFINITION,
               redefinition=RedefinitionKind.RETROACTIVE, title=title, note=note, tags=["replay", replay_id],
               changes=list(changes))
    outcome = world.apply(red)
    if not outcome.ok:  # pragma: no cover — vérifiée ci-dessus contre le même état
        return Report(None, issues=outcome.issues)
    with world.store.conn:
        world.store.conn.execute("INSERT INTO replays VALUES (?, ?, ?, ?, ?, ?)",
                                 (replay_id, source, seq, branch, red.id, OPEN))
    return advance(world, replay_id, limit)


def advance(world: World, replay_id: str, limit: int | None = None) -> Report:
    """Rejoue dans l'ordre jusqu'au premier conflit, jusqu'à `limit` pas (suspension), ou jusqu'à la tête de
    la source, où le rejeu se termine (`finish`). Reprendre = rappeler `advance` (R-RED-02)."""
    r = get(world, replay_id)
    report = Report(r)
    if r.status != OPEN:
        return _fail(r, f"rejeu {r.status}", "R-RED-02")
    while (nxt := _next(world, r)) is not None:
        if limit is not None and len(report.replayed) >= limit:
            return report  # suspendu
        seq, edit_id = nxt
        analysis = world.analyse_transposition(edit_id, r.branch)
        if analysis.relation != "independent":
            report.conflict, report.current = analysis, edit_id
            return report
        outcome, _ = world.transpose(edit_id, r.branch, "auto", reason=f"rejeu {r.id}")
        if not outcome.ok:
            report.conflict, report.current, report.issues = analysis, edit_id, outcome.issues
            return report
        report.replayed.append(_record(world, r, seq, edit_id, "auto", outcome.edit_id, "indépendante"))
    report.carried = finish(world, r)
    report.replay = get(world, replay_id)
    return report


def pending_conflict(world: World, replay_id: str) -> Report:
    """Où en est le rejeu : l'édition suivante et son analyse, sans rien écrire."""
    r = get(world, replay_id)
    report = Report(r)
    nxt = _next(world, r) if r.status == OPEN else None
    if nxt is not None:
        analysis = world.analyse_transposition(nxt[1], r.branch)
        if analysis.relation != "independent":
            report.conflict = analysis
        report.current = nxt[1]
    return report


def decide(world: World, replay_id: str, action: str, changes: list[Change] | None = None,
           reason: str | None = None, limit: int | None = None) -> Report:
    """Décision humaine sur l'édition en conflit — `keep`, `adapt` (avec `changes`) ou `discard` —, tracée,
    puis le rejeu continue."""
    r = get(world, replay_id)
    if r.status != OPEN:
        return _fail(r, f"rejeu {r.status}", "R-RED-02")
    if action not in ("keep", "adapt", "discard"):
        return _fail(r, f"décision inconnue : {action} (keep, adapt, discard)", "R-RED-02")
    if action == "adapt" and changes is None:
        return _fail(r, "adapter exige des changements", "R-RED-02")
    nxt = _next(world, r)
    if nxt is None:
        return _fail(r, "aucune édition en attente de décision", "R-RED-02")
    seq, edit_id = nxt
    outcome, analysis = world.transpose(edit_id, r.branch, action, changes, reason or f"rejeu {r.id}")
    if not outcome.ok and action != "discard":
        return Report(r, conflict=analysis, current=edit_id, issues=outcome.issues)
    detail = reason or ("; ".join(d.describe() for d in analysis.divergences) or "indépendante")
    step = _record(world, r, seq, edit_id, action, outcome.edit_id if action != "discard" else None, detail)
    report = advance(world, replay_id, limit)
    report.replayed.insert(0, step)
    return report


def abandon(world: World, replay_id: str) -> Report:
    """Abandonner : la session et la branche restent tracées (R-HIS-01), la branche n'est plus modifiable ;
    la source reste la branche de travail."""
    r = get(world, replay_id)
    if r.status != OPEN:
        return _fail(r, f"rejeu {r.status}", "R-RED-02")
    with world.store.conn:
        world.store.conn.execute("UPDATE replays SET status = ? WHERE replay_id = ?", (ABANDONED, r.id))
        world.store.set_branch_status(r.branch, "abandoned")
    return Report(get(world, replay_id))


# ---------------------------------------------------------------------------
# Finalisation (§6.4, R-MON-02, R-RED-03)
# ---------------------------------------------------------------------------

@dataclass
class Carry:
    """Ce que la finalisation transmet aux reporteurs."""

    replay: Replay
    seq_map: Callable[[int], int]           # rang source → rang sur la nouvelle branche
    edit_map: dict[str, str | None]         # édition source → édition rejouée (None : écartée)
    touched: set[FactKey]                   # clés redéfinies ou décidées pendant le rejeu


# Reporteurs enregistrés par la périphérie (propositions d'ingestion) : (world, carry) → identifiants
# d'éditions en attente pris en charge. Les autres éditions en attente sont reportées par le noyau.
CARRIERS: list[Callable[[World, Carry], list[str]]] = []


def _carry(world: World, r: Replay) -> Carry:
    done = steps(world, r.id)
    red_seq = r.anchor_seq + 1
    placed = [(s.source_seq, world.store.locate(s.result_edit)[1] if s.result_edit else None) for s in done]

    def seq_map(seq: int) -> int:
        if seq <= r.anchor_seq:
            return seq
        out = red_seq
        for src, new in placed:
            if src > seq:
                break
            if new is not None:
                out = new
        return out

    touched = _unwrap(world.store.edit(r.redefinition).writes)
    for (text,) in world.store.conn.execute("SELECT writes FROM replay_steps WHERE replay_id = ?", (r.id,)):
        touched |= _loads(text)
    return Carry(r, seq_map, {s.source_edit: s.result_edit for s in done}, touched)


def _carry_pending(world: World, c: Carry, handled: set[str]) -> list[str]:
    """Éditions en attente de la source (pistes d'auteur…) : copiées sur la nouvelle branche, base traduite,
    à revérifier si elles touchent une clé redéfinie (R-RED-03) ; l'originale est close (T-ING-16)."""
    out = []
    r = c.replay
    for rec in world.store.edits(r.source, EditStatus.PENDING):
        if rec.edit.id in handled:
            continue
        new_id = f"{rec.edit.id}@{r.branch}"
        base = rec.base
        assert base is not None  # une édition en attente a toujours son état de base (T-ING-01)
        new_base = BaseState(branch=r.branch, seq=c.seq_map(base.seq), schema_rev=base.schema_rev)
        copy = rec.edit.model_copy(update={"id": new_id, "branch": r.branch,
                                           "tags": [*rec.edit.tags, "moved"]})
        recheck = Effects(frozenset(_unwrap(rec.reads)), frozenset(_unwrap(rec.writes))).touches(c.touched)
        world.store.record_edit(copy, EditStatus.PENDING, new_base, rec.reads, rec.writes)
        if recheck:
            world.store.update_pending(new_id, needs_recheck=True)
        world.store.update_pending(rec.edit.id, status=EditStatus.ABANDONED)
        out.append(new_id)
    return out


def _carry_points(world: World, c: Carry) -> list[str]:
    r = c.replay
    names = {n for b, _, _ in world.store.segments(r.source) for n in world.store.named_points(b)}
    out = []
    for name in sorted(names):
        seq = world.store.named_point(r.source, name)
        if seq is not None and seq > r.anchor_seq:
            world.store.set_named_point(r.branch, name, c.seq_map(seq))
            out.append(name)
    return out


def _carry_playthroughs(world: World, c: Carry) -> list[str]:
    from worldkit.core.workflows.scenarios import ensure_tables as scenario_tables
    scenario_tables(world)
    conn = world.store.conn
    out = []
    for pid, sid, version, opened in conn.execute(
            "SELECT playthrough_id, scenario_id, version, opened FROM playthroughs WHERE branch_id = ?"
            " ORDER BY rowid", (c.replay.source,)).fetchall():
        items = conn.execute("SELECT idx, kind, draft_id, adapted, edit_id, outcome, detail FROM playthrough_items"
                             " WHERE playthrough_id = ? ORDER BY idx", (pid,)).fetchall()
        if not any(item[4] in c.edit_map for item in items):
            continue
        new_pid = f"{pid}@{c.replay.branch}"
        conn.execute("INSERT INTO playthroughs VALUES (?, ?, ?, ?, ?)",
                     (new_pid, c.replay.branch, sid, version, c.seq_map(opened)))
        for idx, kind, draft, adapted, edit_id, outcome, detail in items:
            if edit_id in c.edit_map:
                mapped = c.edit_map[edit_id]
                if mapped is None:
                    outcome, detail = "discarded", f"écartée au rejeu {c.replay.id}"
                edit_id = mapped
            conn.execute("INSERT INTO playthrough_items VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                         (new_pid, idx, kind, draft, adapted, edit_id, outcome, detail))
        out.append(new_pid)
    return out


def finish(world: World, r: Replay) -> list[str]:
    """La nouvelle branche remplace la source (archivée) et, si la source était la référence, le devient."""
    c = _carry(world, r)
    carried: list[str] = []
    handled: set[str] = set()
    for carrier in CARRIERS:
        ids = carrier(world, c)
        handled |= set(ids)
        carried += ids
    with world.store.conn:
        carried += _carry_pending(world, c, handled)
        carried += _carry_points(world, c)
        carried += _carry_playthroughs(world, c)
        if world.reference_branch == r.source:
            world.store.set_reference(r.branch, r.id)
        world.store.set_branch_status(r.source, "archived")
        world.store.conn.execute("UPDATE replays SET status = ? WHERE replay_id = ?", (FINISHED, r.id))
    return carried


# ---------------------------------------------------------------------------
# Notification des variantes (R-RED-04)
# ---------------------------------------------------------------------------

def replaced_by(world: World, branch: str) -> Replay | None:
    """Le rejeu terminé qui a archivé cette branche, s'il existe."""
    ensure_tables(world)
    for r in replays(world):
        if r.source == branch and r.status == FINISHED:
            return r
    return None


def lineage_notices(world: World, branch: str) -> list[Issue]:
    """Signalements recalculés, rien n'est stocké ni modifié : la branche est archivée, ou une de ses
    ancêtres l'est (variante dérivée de l'ancienne branche, R-RED-04)."""
    out = []
    r = replaced_by(world, branch)
    if r is not None:
        out.append(Issue(IssueCode.ARCHIVED_BRANCH, f"{branch} est archivée (rejeu {r.id}, redéfinition après le "
                         f"rang {r.anchor_seq}) ; elle est remplacée par {r.branch}", "R-HIS-04", Severity.WARNING))
    child, (parent, fork) = branch, world.store.branch_info(branch)
    while parent is not None:
        r = replaced_by(world, parent)
        if r is not None and r.branch != child:  # la remplaçante elle-même n'est pas une variante
            touched = "son histoire héritée contient l'état d'avant la redéfinition" if fork > r.anchor_seq \
                else "la redéfinition ne touche pas son passé hérité"
            out.append(Issue(IssueCode.ARCHIVED_BRANCH,
                             f"{branch} dérive de {parent}, archivée par le rejeu {r.id} (redéfinition après le "
                             f"rang {r.anchor_seq}, divergence de {child} au rang {fork}) : {touched} ; "
                             f"remplacée par {r.branch}. Rien n'a été modifié ; transposer si souhaité",
                             "R-RED-04", Severity.WARNING))
        child, (parent, fork) = parent, world.store.branch_info(parent)
    return out
