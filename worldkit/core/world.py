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
from worldkit.core.conflicts.transposition import Analysis, analyse, keep_changes
from worldkit.core.journal.models import BaseState, Edit, EditStatus, Origin, edit_rule_issues
from worldkit.core.journal.store import EditRecord, Store
from worldkit.core.projection.serialize import StaleFormat, state_from_json, state_to_json
from worldkit.core.projection.state import State, WorldDeclaration, apply_change, empty_schema, empty_state
from worldkit.core.schema import Issue, IssueCode, Schema, load_schema, read_yaml
from worldkit.core.schema.changes import SchemaSetRelation, SchemaSetType, WORLD_SCOPE

SCHEMA_EDIT_ID = "e000"
_STATUS_FR = {"archived": "archivée", "abandoned": "abandonnée"}


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
        """Branche de référence courante (R-MON-02) : la dernière de l'historique des références, sinon
        celle de la déclaration. Un rejeu rétroactif la fait basculer (§6.4)."""
        return self.store.current_reference() or self.decl.reference_branch

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

    # --- Branches (R-HIS-03, T-BRA-01) ---

    def create_branch(self, name: str, from_branch: str | None = None, point: int | str | None = None) -> int:
        """Nouvelle branche depuis un état de `from_branch` : elle en hérite schéma, systèmes et faits
        (R-MON-04), puis vit sa vie ; la parente n'est jamais modifiée."""
        from_branch = from_branch or self.reference_branch
        if name in self.store.branches():
            raise ValueError(f"branche déjà existante : {name}")
        seq = self.resolve_point(point, from_branch)
        with self.store.conn:
            self.store.create_branch(name, from_branch, seq)
        return seq

    def redefined_after(self, branch: str | None, seq: int) -> frozenset[Any]:
        """Clés réécrites par une redéfinition après `seq` sur la branche (R-VUE-03)."""
        branch = branch or self.reference_branch
        out: set[Any] = set()
        for _, edit_id in self.store.journal_ids(branch, after=seq):
            rec = self.store.edit(edit_id)
            if rec.edit.origin is Origin.REDEFINITION:
                out |= {k[1] if k[0] == "visibility" else k for k in rec.writes}
        return frozenset(out)

    # --- Transposition (R-HIS-05, §6.3) ---

    def analyse_transposition(self, edit_id: str, target: str) -> Analysis:
        located = self.store.locate(edit_id)
        if located is None:
            raise KeyError(f"édition non appliquée : {edit_id}")
        source, seq = located
        if target not in self.store.branches():
            raise KeyError(f"branche inconnue : {target}")
        rec = self.store.edit(edit_id)
        return analyse(edit_id, source, seq, self.state(source, seq - 1), self.state(source, seq), target,
                       self.state(target), rec.reads, rec.writes)

    def _trace_transposition(self, edit_id: str, target: str, action: str, result: str | None, detail: str) -> None:
        self.store.conn.execute(
            "CREATE TABLE IF NOT EXISTS transpositions (transposition_id INTEGER PRIMARY KEY AUTOINCREMENT,"
            " source_edit TEXT NOT NULL, target_branch TEXT NOT NULL, action TEXT NOT NULL, result_edit TEXT,"
            " detail TEXT NOT NULL)")
        with self.store.conn:
            self.store.conn.execute("INSERT INTO transpositions (source_edit, target_branch, action, result_edit,"
                                    " detail) VALUES (?, ?, ?, ?, ?)", (edit_id, target, action, result, detail))

    def transpose(self, edit_id: str, target: str, action: str = "auto", changes: list[Any] | None = None,
                  reason: str | None = None) -> tuple[Outcome, Analysis]:
        """`auto` : appliquer si l'édition est indépendante ; `keep` : garder malgré une contradiction ;
        `adapt` : appliquer d'autres changements ; `discard` : écarter. Toujours tracé."""
        analysis = self.analyse_transposition(edit_id, target)
        original = self.store.edit(edit_id).edit
        new_id = f"{edit_id}@{target}"
        detail = "; ".join(d.describe() for d in analysis.divergences) or "indépendante"
        if action == "discard":
            self._trace_transposition(edit_id, target, "discard", None, reason or detail)
            return Outcome(new_id, [], EditStatus.ABANDONED), analysis
        if action == "auto" and analysis.relation != "independent":
            issues = [Issue(IssueCode.STALE_EDIT, f"transposition non automatique ({analysis.relation}) : {d.describe()}",
                            "R-HIS-05") for d in analysis.divergences]
            return Outcome(new_id, issues), analysis
        if action == "keep" and analysis.missing:
            issues = [Issue(IssueCode.STALE_EDIT, f"dépendance absente de la branche cible : {d.describe()}",
                            "R-HIS-05") for d in analysis.missing]
            return Outcome(new_id, issues), analysis
        body = list(changes) if action == "adapt" and changes is not None else list(original.changes)
        if action == "keep":  # garder : les faits qui occupent les clés sont retirés explicitement (R-FAI-05)
            body, dropped = keep_changes(analysis, body, self.state(target))
            if dropped:
                detail += f" ; retraits sans objet abandonnés : {dropped}"
        edit = original.model_copy(update={"id": new_id, "branch": target, "transposed_from": edit_id,
                                           "derived_from": None, "tags": [*original.tags, "transposed"],
                                           "changes": body})
        outcome = self.apply(edit)
        if outcome.ok and outcome.seq is not None:
            self._trace_transposition(edit_id, target, action, new_id, reason or detail)
        return outcome, analysis

    def set_point(self, name: str, point: int | str | None = None, branch: str | None = None) -> int:
        branch = branch or self.reference_branch
        seq = self.resolve_point(point, branch)
        with self.store.conn:
            self.store.set_named_point(branch, point_name(name), seq)
        return seq

    # --- Écriture ---

    def _preflight(self, edit: Edit, applying: bool = True) -> list[Issue]:
        issues = edit_rule_issues(edit, applying)
        if self.store.has_edit(edit.id):
            issues.append(Issue(IssueCode.EDIT_RULE, f"identifiant d'édition déjà utilisé : {edit.id}", "R-CYC-01"))
        if edit.branch not in self.store.branches():
            issues.append(Issue(IssueCode.EDIT_RULE, f"branche inconnue : {edit.branch}", "T-BRA-01"))
        elif (status := self.store.branch_status(edit.branch)) != "active":
            issues.append(Issue(IssueCode.EDIT_RULE, f"branche {edit.branch} {_STATUS_FR.get(status, status)} : "
                                "consultable, plus modifiable", "R-HIS-04"))
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

    def submit(self, edit: Edit, point: int | str | None = None) -> Outcome:
        """Met une édition en attente, même non applicable en l'état (R-SCH-06 : signalée, mise en attente).
        `point` : l'état contre lequel elle est écrite (défaut : la tête), par exemple une piste écrite à @after-b4."""
        issues = self._preflight(edit, applying=False)
        if issues:
            return Outcome(edit.id, issues)
        head = self.state(edit.branch, point)
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
        rule_issues = edit_rule_issues(rec.edit)
        if rule_issues:
            return Outcome(edit_id, rule_issues, EditStatus.PENDING)
        stale =rec.needs_recheck or Effects(rec.reads, rec.writes).touches(
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
