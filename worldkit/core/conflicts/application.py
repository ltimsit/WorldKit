"""Cœur de M4 : lectures, écritures, collisions, péremption (R-EDI-03, R-FAI-05, T-ING-02, T-ING-06).

`check_application` simule une édition sur une copie de l'état, changement par changement :

- **collision** (`key_collision`, R-FAI-05) : un ajout vise une clé occupée par un autre fait.
  Remplacer exige de retirer l'ancien fait dans la même édition (invariant 4 : rien ne change
  silencieusement) ; seul `set_attribute` remplace une valeur, puisque l'opération signifie
  « modifier » ;
- **contradiction interne** (`internal_contradiction`) : l'édition écrit deux fois la même clé
  avec des valeurs différentes ;
- **fait absent** (`missing_fact`, R-EDI-04) : un retrait ou un changement de notoriété vise un
  fait que l'état ne contient pas.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field

from worldkit.core.projection.state import State, apply_change, fact_id_of, target_fact_id
from worldkit.core.schema import Change, FactKey, Issue, IssueCode, check_edit, fact_keys, qualify
from worldkit.core.schema.changes import (
    AddRelation, AddValue, CloseEntity, CreateEntity, DeleteEntity, QualifyClaim, RemoveRelation, RemoveValue,
    SCHEMA_OPS, SetAttribute, SetVisibility, UnsetAttribute, parse_change,
)
from worldkit.core.schema.issues import Severity
from worldkit.core.schema.keys import format_key, target_keys


@dataclass(frozen=True)
class Effects:
    """Clés lues et écrites par une édition (R-EDI-03, T-ING-02)."""

    reads: frozenset[FactKey] = frozenset()
    writes: frozenset[FactKey] = frozenset()

    def touches(self, writes: Iterable[FactKey]) -> bool:
        """Péremption (T-ING-06) : une écriture appliquée depuis la base croise-t-elle ces clés ?"""
        other = set(writes)
        return bool(other & self.reads) or bool(other & self.writes)


@dataclass(frozen=True)
class Application:
    issues: list[Issue]
    effects: Effects
    state: State | None = None  # état après l'édition, si elle est applicable

    @property
    def applicable(self) -> bool:
        return not any(i.severity is Severity.ERROR for i in self.issues)


@dataclass
class _Tracker:
    reads: set[FactKey] = field(default_factory=set)
    writes: set[FactKey] = field(default_factory=set)
    issues: list[Issue] = field(default_factory=list)
    written: dict[FactKey, object] = field(default_factory=dict)  # valeurs écrites par l'édition


def _cited_entities(change: Change) -> list[str]:
    sc = change.scope
    match change:
        case CreateEntity():
            return [change.sheet.of] if change.sheet else []
        case AddRelation() | RemoveRelation():
            return [qualify(change.from_, sc), qualify(change.to, sc)]
        case SetVisibility():
            t = change.target
            ends = [t.from_, t.to] if t.relation else [t.entity]
            return [qualify(e, sc) for e in ends if e]
    entity = getattr(change, "entity", None)
    return [qualify(entity, sc)] if entity else []


def check_application(changes: list[Change], state: State, edit_id: str) -> Application:
    """Vérifie une édition contre un état (M1 puis collisions) et calcule ses effets."""
    m1 = check_edit(changes, state.context())
    if not m1.applicable:
        return Application(list(m1.issues), Effects())
    t = _Tracker(issues=list(m1.issues))
    sim = state.copy()
    sim.seq = state.seq + 1
    existing = set(state.entities)
    for index, change in enumerate(changes):
        path = f"changes[{index}]"
        _check_one(change, sim, t, path)
        for entity in _cited_entities(change):
            if entity in existing:
                t.reads.add(("entity", entity))  # T-ING-02 : existence de chaque entité citée
        if not any(i.severity is Severity.ERROR and i.path == path for i in t.issues):
            apply_change(sim, change, edit_id)
    effects = Effects(frozenset(t.reads), frozenset(t.writes))
    ok = not any(i.severity is Severity.ERROR for i in t.issues)
    return Application(t.issues, effects, sim if ok else None)


def _err(t: _Tracker, code: IssueCode, msg: str, rule: str, path: str) -> None:
    t.issues.append(Issue(code, msg, rule, path=path))


def _check_one(change: Change, sim: State, t: _Tracker, path: str) -> None:
    ctx = sim.context()
    keys = fact_keys(change, ctx)
    if isinstance(change, SCHEMA_OPS):
        t.writes.update(keys)
        return
    if change.visibility is not None and not isinstance(change, SetVisibility):
        t.writes.update(("visibility", k) for k in keys)

    match change:
        case CreateEntity():
            if keys[0] in sim.occupancy:
                _err(t, IssueCode.KEY_COLLISION, f"l'entité « {keys[0][1]} » existe déjà", "R-FAI-05", path)
            elif len(keys) > 1 and keys[1] in sim.occupancy:  # une fiche par système (R-MET-02)
                other = sim.occupancy[keys[1]][1]
                _err(t, IssueCode.KEY_COLLISION, f"« {keys[1][1]} » a déjà une fiche dans {keys[1][2]} ({other}) ; "
                     "la clore dans la même édition pour la remplacer", "R-FAI-05", path)
            t.writes.update(keys)
        case CloseEntity() | DeleteEntity():
            t.reads.update(keys)
            t.writes.update(keys)
        case SetAttribute():
            if keys[0] in sim.occupancy:
                t.reads.update(keys)  # ancienne valeur supposée
            _write(t, keys, change.value, path)
        case AddValue() | AddRelation():
            fid = fact_id_of(change, ctx)
            for k in keys:
                occupant = sim.occupancy.get(k)
                if occupant is not None and occupant != fid:
                    other = sim.facts[occupant]
                    _err(t, IssueCode.KEY_COLLISION,
                         f"la clé {format_key(k)} est occupée par {other.name}({other.subject}, {other.target}) ; "
                         "retirer ce fait dans la même édition pour le remplacer", "R-FAI-05", path)
            t.writes.update(keys)
        case UnsetAttribute() | RemoveValue() | RemoveRelation():
            fid = fact_id_of(change, ctx)
            if fid not in sim.facts:
                _err(t, IssueCode.MISSING_FACT, f"fait absent de l'état visé : {format_key(keys[0])}", "R-EDI-04", path)
            t.reads.update(keys)
            t.writes.update(keys)
            for k in keys:
                t.written.pop(k, None)
        case SetVisibility():
            fid = target_fact_id(change.target, change.scope, ctx)
            target = target_keys(change.target, change.scope, ctx)
            if fid is not None and fid not in sim.facts:
                _err(t, IssueCode.MISSING_FACT, f"fait absent de l'état visé : {format_key(target[0])}",
                     "R-EDI-04", path)
            t.reads.update(target)
            t.writes.update(keys)
        case QualifyClaim():
            t.reads.update(_claimed_keys(change.claim, sim))
            t.writes.update(keys)
        case _:
            t.writes.update(keys)


def _claimed_keys(claim: str, sim: State) -> list[FactKey]:
    """Une qualification juge l'affirmation contre le monde : elle lit les clés du changement revendiqué
    (T-ING-12, décision J7). L'affirmation elle-même ne lit rien : le document dit ce qu'il dit."""
    record = sim.claims.get(claim)
    claimed = record.get("claimed") if record else None
    if not claimed:
        return []
    try:
        return list(fact_keys(parse_change(claimed), sim.context()))
    except Exception:  # changement revendiqué hors schéma : rien à lire (R-SCH-06)
        return []


def _write(t: _Tracker, keys: list[FactKey], value: object, path: str) -> None:
    for k in keys:
        if k in t.written and t.written[k] != value:
            _err(t, IssueCode.INTERNAL_CONTRADICTION,
                 f"l'édition écrit deux fois la clé {format_key(k)} avec des valeurs différentes", "R-FAI-05", path)
        t.written[k] = value
    t.writes.update(keys)
