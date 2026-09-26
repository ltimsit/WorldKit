"""Signalements recalculables sur un état (famille `conformity`, R-CON-04) et faits masqués (R-NOT-07)."""

from __future__ import annotations

from worldkit.core.projection.state import State
from worldkit.core.schema import Issue, StateSnapshot, check_conformity

from .model import masked_public_facts


def snapshot(state: State) -> StateSnapshot:
    attributes = {(f.subject, f.name): f.value for f in state.facts.values() if f.kind == "attr"}
    values = frozenset((f.subject, f.name, f.value) for f in state.facts.values() if f.kind == "value")
    relations = frozenset((f.subject, f.name, f.target or "", f.scope) for f in state.facts.values() if f.kind == "rel")
    return StateSnapshot(state.entities, attributes, values, relations)


def state_report(state: State) -> list[Issue]:
    return check_conformity(snapshot(state), state.context()) + masked_public_facts(state)
