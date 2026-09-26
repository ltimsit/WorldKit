"""Un monde : journal (M2), projection (M3) et contrôles d'application (M4, cœur).

Deux voies d'écriture pour une édition structurée (R-ALI-01, voie 2) :
- `apply` : vérifiée contre la tête, appliquée aussitôt ;
- `submit` puis `confirm` : mise en attente avec son état de base (T-ING-01), confirmée plus
  tard après contrôle de péremption (T-ING-06) et revalidation contre la tête (T-ING-14).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from worldkit.core.conflicts import Effects, check_application
from worldkit.core.journal.models import BaseState, Edit, EditStatus, Origin, edit_rule_issues
from worldkit.core.journal.store import EditRecord, Store
from worldkit.core.projection.serialize import StaleFormat, state_from_json, state_to_json
from worldkit.core.projection.state import State, WorldDeclaration, apply_change, empty_schema, empty_state
from worldkit.core.schema import Issue, IssueCode, Schema, load_schema, read_yaml
from worldkit.core.schema.changes import SchemaSetRelation, SchemaSetType, WORLD_SCOPE

SCHEMA_EDIT_ID = "e000"


def point_name(name: str) -> str:
    """Les points nommés s'écrivent `@base` ; le `@` est facultatif à la saisie
    (en PowerShell, `@base` non entre guillemets est avalé par l'opérateur de splatting)."""
    return name if name.startswith("@") else f"@{name}"


@dataclass(frozen=True)
class Outcome:
    edit_id: str
    issues: list[Issue] = field(default_factory=list)
    status: EditStatus | None = None
    seq: int | None = None

    @property
    def ok(self) -> bool:
        return not any(i.severity == "error" for i in self.issues)


# ---------------------------------------------------------------------------
# Déclaration du monde et édition e000
# ---------------------------------------------------------------------------

def schema_edit(scope: str, schema: Schema) -> list[Any]:
    """Changements qui construisent `schema` à partir d'un schéma vide (R-SCH-03)."""
    changes: list[Any] = [SchemaSetType(op="schema_set_type", scope=scope, type=name, definition=t)
                          for name, t in schema.types.items()]
    changes += [SchemaSetRelation(op="schema_set_relation", scope=scope, relation=name, definition=r)
                for name, r in schema.relations.items()]
    return changes


def load_declaration(world_yaml: str | Path) -> tuple[WorldDeclaration, Edit]:
    """Lit `world.yaml` : déclaration du monde, et édition e000 qui charge schéma et systèmes."""
    path = Path(world_yaml)
    raw = read_yaml(path)
    world = load_schema(path.parent / raw["schema"])
    systems: dict[str, Schema] = {}
    requirements: dict[str, dict[str, str]] = {}
    for declared in raw.get("rule_systems", []):
        system = load_schema(path.parent / declared["schema"])
        systems[system.id] = system
        requirements[system.id] = dict(declared.get("sheets", {}))
    reference = raw.get("reference_branch", "reference")
    decl = WorldDeclaration(raw["world"], reference, empty_schema(world),
                            {k: empty_schema(v) for k, v in systems.items()}, requirements)
    changes = schema_edit(WORLD_SCOPE, world)
    for sid, system in systems.items():
        changes += schema_edit(sid, system)
    e000 = Edit(id=SCHEMA_EDIT_ID, branch=reference, origin=Origin.ENRICHMENT, tags=["schema"], changes=changes)
    return decl, e000


# ---------------------------------------------------------------------------
# Monde
# ---------------------------------------------------------------------------

class World:
    def __init__(self, store: Store) -> None:
        self.store = store
        self.decl = store.declaration()

    @classmethod
    def create(cls, db: str | Path, world_yaml: str | Path) -> World:
        decl, e000 = load_declaration(world_yaml)
        world = cls(Store.create(db, decl))
        outcome = world.apply(e000)
        if not outcome.ok:  # pragma: no cover — les schémas ont déjà été validés au chargement
            raise ValueError("chargement du schéma refusé :\n" + "\n".join(map(str, outcome.issues)))
        return world

    @classmethod
    def open(cls, db: str | Path) -> World:
        return cls(Store.open(db))

    def close(self) -> None:
        self.store.close()

    @property
    def reference_branch(self) -> str:
        return self.decl.reference_branch

    # --- États ---

    def resolve_point(self, point: int | str | None, branch: str | None = None) -> int:
        branch = branch or self.reference_branch
        head = self.store.head_seq(branch)
        if point is None or point == "head":
            return head
        if isinstance(point, int) or (isinstance(point, str) and point.isdigit()):
            seq = int(point)
        else:
            found = self.store.named_point(branch, point_name(point))
            if found is None:
                raise KeyError(f"point inconnu sur la branche {branch} : {point}")
            seq = found
        if not 0 <= seq <= head:
            raise KeyError(f"point hors du journal de {branch} : {seq} (tête : {head})")
        return seq

    def replay(self, branch: str | None = None, upto: int | None = None) -> State:
        """État = état de départ + éditions appliquées, dans l'ordre, jusqu'au point (R-HIS-02)."""
        branch = branch or self.reference_branch
        state = empty_state(self.decl, branch)
        for seq, edit in self.store.journal(branch, upto):
            state.seq = seq
            for change in edit.changes:
                apply_change(state, change, edit.id)
        return state

    def state(self, branch: str | None = None, point: int | str | None = None) -> State:
        branch = branch or self.reference_branch
        seq = self.resolve_point(point, branch)
        if seq == self.store.head_seq(branch):
            cached = self.store.cached_head(branch)
            if cached is not None and cached[0] == seq:
                try:
                    return state_from_json(cached[1])
                except StaleFormat:
                    pass
        return self.replay(branch, seq)

    def set_point(self, name: str, point: int | str | None = None, branch: str | None = None) -> int:
        branch = branch or self.reference_branch
        seq = self.resolve_point(point, branch)
        with self.store.conn:
            self.store.set_named_point(branch, point_name(name), seq)
        return seq

    # --- Écriture ---

    def _preflight(self, edit: Edit) -> list[Issue]:
        issues = edit_rule_issues(edit)
        if self.store.has_edit(edit.id):
            issues.append(Issue(IssueCode.EDIT_RULE, f"identifiant d'édition déjà utilisé : {edit.id}", "R-CYC-01"))
        if edit.branch not in self.store.branches():
            issues.append(Issue(IssueCode.EDIT_RULE, f"branche inconnue : {edit.branch}", "T-BRA-01"))
        return issues

    def _commit(self, edit: Edit, state: State, effects: Effects, pending: EditRecord | None) -> int:
        """Ajoute au journal, met en cache la tête, marque « à revérifier » les éditions touchées."""
        with self.store.conn:
            if pending is None:
                self.store.record_edit(edit, EditStatus.APPLIED, None, effects.reads, effects.writes)
            else:
                self.store.update_pending(edit.id, status=EditStatus.APPLIED, reads=effects.reads,
                                          writes=effects.writes, needs_recheck=False)
            seq = self.store.append_journal(edit.branch, edit.id)
            state.seq = seq
            self.store.save_head(edit.branch, seq, state_to_json(state))
            for other in self.store.edits(edit.branch, EditStatus.PENDING):
                if not other.needs_recheck and Effects(other.reads, other.writes).touches(effects.writes):
                    self.store.update_pending(other.edit.id, needs_recheck=True)
        return seq

    def apply(self, edit: Edit) -> Outcome:
        issues = self._preflight(edit)
        if issues:
            return Outcome(edit.id, issues)
        app = check_application(edit.changes, self.state(edit.branch), edit.id)
        if not app.applicable or app.state is None:
            return Outcome(edit.id, app.issues)
        seq = self._commit(edit, app.state, app.effects, None)
        return Outcome(edit.id, app.issues, EditStatus.APPLIED, seq)

    def submit(self, edit: Edit) -> Outcome:
        """Met une édition en attente, même non applicable en l'état (R-SCH-06 : signalée, mise en attente)."""
        issues = self._preflight(edit)
        if issues:
            return Outcome(edit.id, issues)
        head = self.state(edit.branch)
        app = check_application(edit.changes, head, edit.id)
        with self.store.conn:
            self.store.record_edit(edit, EditStatus.PENDING, BaseState(branch=edit.branch, seq=head.seq,
                                   schema_rev=head.schema_rev), app.effects.reads, app.effects.writes)
        return Outcome(edit.id, app.issues, EditStatus.PENDING)

    def _pending(self, edit_id: str) -> EditRecord | Outcome:
        try:
            rec = self.store.edit(edit_id)
        except KeyError as e:
            return Outcome(edit_id, [Issue(IssueCode.EDIT_RULE, str(e.args[0]), "R-CYC-04")])
        if rec.status is not EditStatus.PENDING:
            return Outcome(edit_id, [Issue(IssueCode.EDIT_RULE, f"édition {rec.status}, pas en attente", "R-CYC-01")],
                           rec.status)
        return rec

    def confirm(self, edit_id: str) -> Outcome:
        rec = self._pending(edit_id)
        if isinstance(rec, Outcome):
            return rec
        assert rec.base is not None
        stale = rec.needs_recheck or Effects(rec.reads, rec.writes).touches(
            self.store.writes_since(rec.edit.branch, rec.base.seq))
        if stale:
            with self.store.conn:
                self.store.update_pending(edit_id, needs_recheck=True)
            return Outcome(edit_id, [Issue(
                IssueCode.STALE_EDIT,
                "à revérifier : la branche a changé sur les clés lues ou écrites depuis la base de l'édition ; "
                "la requalifier contre la tête (rebase) avant de la confirmer", "T-ING-06")], EditStatus.PENDING)
        app = check_application(rec.edit.changes, self.state(rec.edit.branch), edit_id)  # T-ING-14
        if not app.applicable or app.state is None:
            return Outcome(edit_id, app.issues, EditStatus.PENDING)
        seq = self._commit(rec.edit, app.state, app.effects, rec)
        return Outcome(edit_id, app.issues, EditStatus.APPLIED, seq)

    def rebase(self, edit_id: str) -> Outcome:
        """Requalifie une édition en attente contre la tête et avance sa base (T-ING-06)."""
        rec = self._pending(edit_id)
        if isinstance(rec, Outcome):
            return rec
        head = self.state(rec.edit.branch)
        app = check_application(rec.edit.changes, head, edit_id)
        with self.store.conn:
            self.store.update_pending(edit_id, base=BaseState(branch=head.branch, seq=head.seq,
                                                              schema_rev=head.schema_rev),
                                      reads=app.effects.reads, writes=app.effects.writes,
                                      needs_recheck=False)
        return Outcome(edit_id, app.issues, EditStatus.PENDING)

    def abandon(self, edit_id: str) -> Outcome:
        rec = self._pending(edit_id)
        if isinstance(rec, Outcome):
            return rec
        with self.store.conn:
            self.store.update_pending(edit_id, status=EditStatus.ABANDONED)
        return Outcome(edit_id, [], EditStatus.ABANDONED)
