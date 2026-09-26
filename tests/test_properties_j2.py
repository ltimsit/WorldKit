"""Propriétés T1 du noyau (J2, hypothesis) : cadre technique §6.

- deux éditions sans clé commune commutent (§6.3) ;
- un filtre public ne laisse passer aucun fait secret ou non qualifié (R-NOT-03, R-NOT-04) ;
- le journal ne fait que s'allonger, même quand des éditions sont refusées (R-HIS-01) ;
- la projection est déterministe (T-ARC-01).
"""

from __future__ import annotations

import json
from dataclasses import replace

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from support import attr, base_world, edit
from worldkit.core.conflicts import check_application
from worldkit.core.projection.serialize import state_to_dict, state_to_json
from worldkit.core.projection.state import mentioned_entities
from worldkit.core.schema import Visibility
from worldkit.core.views import Filter, View, export_graph

WORLD = base_world()
BASE = WORLD.state()
CHARACTERS = sorted(e for e, r in BASE.entities.items() if r.type == "Character")
PLACES = sorted(e for e, r in BASE.entities.items() if r.type == "Place")
SETTINGS = settings(max_examples=60, deadline=None, suppress_health_check=[HealthCheck.too_slow])

texts = st.text(alphabet="abcdefghij ", min_size=1, max_size=8)


@st.composite
def disjoint_edits(draw):
    """Deux éditions sur des entités disjointes : aucune clé commune."""
    chars = draw(st.lists(st.sampled_from(CHARACTERS), min_size=2, max_size=4, unique=True))
    split = draw(st.integers(1, len(chars) - 1))
    left, right = chars[:split], chars[split:]
    a = [attr(c, draw(st.sampled_from(["title", "condition"])), draw(texts)) for c in left]
    b = [attr(c, draw(st.sampled_from(["title", "condition"])), draw(texts)) for c in right]
    if draw(st.booleans()):
        a.append({"op": "add_value", "entity": "veilleurs", "attribute": "vows", "value": draw(texts)})
    return a, b


def run(state, *edits):
    for i, changes in enumerate(edits):
        app = check_application(changes, state, f"x{i}")
        assert app.applicable, [str(x) for x in app.issues]
        state = app.state
    return state


def without_provenance(state):
    d = state_to_dict(state)
    for f in d["facts"]:
        f["established_by"] = ""
    return json.dumps(d, sort_keys=True, default=str)


@SETTINGS
@given(disjoint_edits())
def test_independent_edits_commute(pair):
    a, b = (edit(*changes).changes for changes in pair)
    ea = check_application(a, BASE, "a").effects
    eb = check_application(b, BASE, "b").effects
    assert not (ea.writes & (eb.reads | eb.writes)) and not (eb.writes & ea.reads)
    assert without_provenance(run(BASE, a, b)) == without_provenance(run(BASE, b, a))


visibilities = st.sampled_from(list(Visibility))


@SETTINGS
@given(st.data())
def test_public_filter_never_leaks(data):
    """Notoriétés tirées au hasard, levées comprises : rien de non public n'apparaît en vue joueur."""
    state = BASE.copy()
    for eid in sorted(state.entities):
        state.entities[eid] = replace(state.entities[eid], visibility=data.draw(visibilities))
    for fid in sorted(state.facts, key=repr):
        state.facts[fid] = replace(state.facts[fid], visibility=data.draw(visibilities),
                                   propagation_lifted=data.draw(st.booleans()))
    public = {e for e, r in state.entities.items() if r.visibility is Visibility.PUBLIC}

    def shown_publicly(fact):
        hidden = [e for e in mentioned_entities(fact, state) if e not in public]
        return fact.visibility is Visibility.PUBLIC and (not hidden or fact.propagation_lifted)

    view = View(state, Filter.PLAYER)
    for eid in view.entity_ids():
        assert eid in public
        page = view.page(eid)
        for line in page.attributes + page.relations:
            assert shown_publicly(state.facts[line.fact])
        for r in page.relations:
            assert r.other is None or r.other in public
    exported = export_graph(state, Filter.PLAYER)
    assert {e["id"] for e in exported["entities"]} <= public
    for r in exported["relations"]:
        ends = {r["from"], r["to"]} - {None}
        assert ends <= public
        assert any(f.name == r["relation"] and ends <= {f.subject, f.target} and shown_publicly(f)
                   for f in state.facts.values())


@SETTINGS
@given(st.lists(st.tuples(st.sampled_from(CHARACTERS + PLACES), st.sampled_from(["title", "rules", "name"]),
                          texts), min_size=1, max_size=5))
def test_journal_only_grows(attempts):
    world = base_world()
    before = [(seq, e.id) for seq, e in world.store.journal(world.reference_branch)]
    for entity, what, value in attempts:
        changes = [attr(entity, what, value)] if what != "rules" else \
            [{"op": "add_relation", "from": entity, "relation": "rules", "to": "brume"}]
        world.apply(edit(*changes))  # certaines sont refusées (hors schéma, collision)
    after = [(seq, e.id) for seq, e in world.store.journal(world.reference_branch)]
    assert after[:len(before)] == before
    assert [s for s, _ in after] == list(range(1, len(after) + 1))
    world.close()


def test_projection_is_deterministic():
    assert state_to_json(WORLD.replay()) == state_to_json(base_world().replay())
