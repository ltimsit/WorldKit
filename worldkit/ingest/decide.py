"""M9 (décisions) : accepter, refuser, choisir, adapter une proposition (R-EDI-08, R-CYC-02, R-PRI-04, T-ING-04).

- Accepter entièrement applique la proposition elle-même ; accepter en partie, sans ses changements
  facultatifs, ou en l'adaptant applique une **édition dérivée** (`derived_from`) et clôt la proposition.
- Accepter une anomalie ou une intention sur une relation ajoute le **retrait explicite** du fait qui
  occupe la clé, montré dans l'édition (décision J3.2 ; R-FAI-05, invariant 4).
- Origine déduite (décision J3.2, R-EDI-05) : `enrichment` sans contradiction ; anomalie acceptée →
  `redefinition` ponctuelle ; intention acceptée → `evolution`.
- Chaque changement décidé laisse une décision tracée par empreinte et par passage (T-ING-08).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from worldkit.core.journal.models import Edit, EditStatus, Origin, RedefinitionKind
from worldkit.core.schema import Change, Issue, IssueCode, fact_keys
from worldkit.core.schema.changes import AddRelation, RemoveRelation
from worldkit.core.schema.keys import UnknownRelation
from worldkit.core.world import World

from .queue import StoredChange, StoredProposal, close, load, load_one, passage_fp, refresh, save_change
from .store import dumps, ensure_tables


@dataclass
class Decided:
    proposal: str
    action: str
    edit_id: str | None = None
    seq: int | None = None
    issues: list[Issue] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not any(i.severity == "error" for i in self.issues)


def _fail(pid: str, action: str, msg: str, rule: str) -> Decided:
    return Decided(pid, action, issues=[Issue(IssueCode.EDIT_RULE, msg, rule)])


def _pending(world: World, pid: str, action: str) -> StoredProposal | Decided:
    ensure_tables(world.store.conn)
    refresh(world)
    p = load_one(world, pid)
    if p is None:
        return _fail(pid, action, f"proposition inconnue : {pid}", "R-CYC-04")
    if p.status is not EditStatus.PENDING:
        return _fail(pid, action, f"proposition close ({p.status}, {p.closed_reason})", "R-EDI-08")
    return p


def _trace(world: World, p: StoredProposal, c: StoredChange, action: str, edit_id: str | None,
           reason: str | None) -> None:
    world.store.conn.execute(
        "INSERT INTO decisions (fingerprint, doc_id, passage_fp, branch_id, action, proposal, edit_id, reason)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (c.fingerprint, p.doc, passage_fp(world, p.doc, p.version_fp, p.passage), p.base.branch if p.base else "",
         action, p.id, edit_id, reason))


def origin_for(changes: list[StoredChange]) -> tuple[Origin, RedefinitionKind | None]:
    tags = set().union(*(c.tags for c in changes)) if changes else set()
    if "intention" in tags:
        return Origin.EVOLUTION, None
    if "anomaly" in tags:
        return Origin.REDEFINITION, RedefinitionKind.POINT
    return Origin.ENRICHMENT, None


def _with_removals(world: World, kept: list[StoredChange]) -> tuple[list[Change], list[Change]]:
    """Changements à appliquer, précédés du retrait des faits qui occupent les clés visées."""
    head = world.state()
    ctx = head.context()
    removals: list[Change] = []
    for c in kept:
        if not ({"anomaly", "intention"} & c.tags) or not isinstance(c.change, AddRelation):
            continue
        try:
            keys = fact_keys(c.change, ctx)
        except UnknownRelation:
            continue
        ch = c.change
        for occ in sorted({head.occupancy[k] for k in keys if k in head.occupancy}, key=repr):
            fact = head.facts[occ]
            if (fact.subject, fact.target) in ((ch.from_, ch.to), (ch.to, ch.from_)):
                continue
            removal = RemoveRelation(op="remove_relation", scope=fact.scope, **{"from": fact.subject},
                                     relation=fact.name, to=fact.target or "")
            if removal not in removals:
                removals.append(removal)
    return removals, [c.change for c in kept]


def _apply(world: World, p: StoredProposal, kept: list[StoredChange], extra: list[Change], action: str,
           refused: list[StoredChange], reason: str | None, prepend: bool = True) -> Decided:
    removals, changes = _with_removals(world, kept)
    changes = (extra + removals + changes) if prepend else (removals + extra)
    origin, redefinition = origin_for(kept)
    whole = not extra and not removals and len(kept) == len(p.changes)
    conn = world.store.conn
    if whole:
        with conn:
            world.store.set_origin(p.id, origin.value, redefinition.value if redefinition else None)
        outcome = world.confirm(p.id)
        edit_id = p.id
    else:
        edit_id = f"{p.id}.d"
        derived = Edit(id=edit_id, branch=p.base.branch if p.base else world.reference_branch, origin=origin,
                       redefinition=redefinition, tags=["ingestion", p.batch], derived_from=p.id, changes=changes)
        outcome = world.apply(derived)
    if not outcome.ok or outcome.seq is None:
        if whole:  # l'origine reste déduite à la prochaine tentative
            pass
        return Decided(p.id, action, None, None, outcome.issues)
    with conn:
        for c in kept:
            c.state = "accepted"
            save_change(world, p.id, c)
            _trace(world, p, c, action, edit_id, reason)
        for c in refused:
            c.state = "refused"
            save_change(world, p.id, c)
            _trace(world, p, c, "refuse", None, reason)
        if not whole:
            close(world, p, EditStatus.APPLIED, f"derived:{edit_id}")
        else:
            conn.execute("UPDATE proposals SET closed_reason = 'accepted' WHERE edit_id = ?", (p.id,))
    refresh(world)
    return Decided(p.id, action, edit_id, outcome.seq, outcome.issues)


def accept(world: World, pid: str, keep: list[int] | None = None, drop_optional: bool = False,
           reason: str | None = None) -> Decided:
    """Accepter tout, ou seulement les changements `keep` (les autres sont refusés et tracés, R-EDI-08)."""
    p = _pending(world, pid, "accept")
    if isinstance(p, Decided):
        return p
    open_ = p.open_changes()
    kept = [c for c in open_ if (keep is None or c.index in keep) and not (drop_optional and "optional" in c.tags)]
    refused = [c for c in open_ if c not in kept]
    if not kept:
        return refuse(world, pid, reason=reason)
    for dep in p.depends_on:
        other = load_one(world, dep)
        if other is not None and other.status is EditStatus.PENDING:
            return _fail(pid, "accept", f"dépend de {dep}, encore en attente : la décider d'abord", "T-ING-05")
    return _apply(world, p, kept, [], "accept", refused, reason)


def refuse(world: World, pid: str, changes: list[int] | None = None, reason: str | None = None,
           action: str = "refuse") -> Decided:
    """Refuser tout ou partie ; la proposition est close quand plus rien n'est ouvert (R-CYC-02)."""
    p = _pending(world, pid, action)
    if isinstance(p, Decided):
        return p
    targets = [c for c in p.open_changes() if changes is None or c.index in changes]
    with world.store.conn:
        for c in targets:
            c.state = "refused"
            save_change(world, p.id, c)
            _trace(world, p, c, action, None, reason)
        if not p.open_changes():
            close(world, p, EditStatus.ABANDONED, action)
    return Decided(p.id, action)


def adapt(world: World, pid: str, changes: list[Change], replace: bool = False, reason: str | None = None) -> Decided:
    """Confirmer en adaptant (R-EDI-08) : ajouter des changements en tête (ex. `schema_set_relation`, W09),
    ou remplacer ceux de la proposition. Applique une édition dérivée."""
    p = _pending(world, pid, "adapt")
    if isinstance(p, Decided):
        return p
    kept = p.open_changes()
    if replace:
        return _apply(world, p, [], changes, "adapt", kept, reason, prepend=False)
    return _apply(world, p, kept, changes, "adapt", [], reason)


def choose(world: World, pid: str, reason: str | None = None) -> list[Decided]:
    """Trancher un conflit de lot ou une concurrence : accepter `pid`, refuser les changements des autres
    propositions en attente qui visent les mêmes clés avec une autre valeur (R-PRI-03, R-PRI-07)."""
    p = _pending(world, pid, "choose")
    if isinstance(p, Decided):
        return [p]
    chosen = {(dumps(k), c.value) for c in p.open_changes() for k in c.keys}
    first = accept(world, pid, reason=reason)
    if not first.ok:
        return [first]
    out = [first]
    keys = {k for k, _ in chosen}
    for other in load(world):
        losing = [c.index for c in other.open_changes()
                  if any(dumps(k) in keys and (dumps(k), c.value) not in chosen for k in c.keys)]
        if losing:
            out.append(refuse(world, other.id, losing, reason or f"conflit tranché pour {pid}"))
    return out


def dismiss(world: World, doc: str, passage: int, reason: str | None = None) -> None:
    """Écarter un passage signalé (attribution, R-DEC-03) : décision tracée, rien d'autre."""
    ensure_tables(world.store.conn)
    row = world.store.conn.execute("SELECT version_fp, passage_fp FROM passages WHERE doc_id = ? AND idx = ?"
                                   " ORDER BY rowid DESC", (doc, passage)).fetchone()
    if row is None:
        raise KeyError(f"passage inconnu : {doc} p{passage}")
    with world.store.conn:
        world.store.conn.execute(
            "INSERT INTO decisions (fingerprint, doc_id, passage_fp, branch_id, action, reason)"
            " VALUES (?, ?, ?, ?, 'dismiss', ?)", (f"passage:{row[1]}", doc, row[1], world.reference_branch, reason))
