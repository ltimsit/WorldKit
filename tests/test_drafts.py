"""I10 — les pistes d'auteur à l'écran : service (lister, créer, adopter, écarter), geste « en faire une piste » dans
l'atelier, page /pistes (R-SCN-09 ; décisions de la fiche I10)."""

from __future__ import annotations

import pytest

from support import base_world
from test_service import make_world
from worldkit.atelier import gestures, layers, store
from worldkit.service import Session

ODON_MERVIN = [{"op": "add_relation", "from": "odon", "relation": "sibling_of", "to": "mervin"}]


@pytest.fixture
def db(tmp_path):
    return make_world(tmp_path / "valmont.db")


def call(db, op, **params):
    with Session(db) as s:
        return s.call(op, params, record=False)


def test_create_checks_then_writes_a_pending_draft_R_SCN_09(db):
    params = {"title": "Et si Odon était le frère de Mervin ?", "concerns": ["odon", "mervin"], "changes": ODON_MERVIN}
    preview = call(db, "drafts.create", **params)
    assert preview.status == "pending" and call(db, "drafts.list").output["drafts"] == []
    done = call(db, "drafts.create", **params, confirm=True)
    assert done.ok and done.output["status"] == "pending"
    [d] = call(db, "drafts.list").output["drafts"]
    assert d["title"] == params["title"] and [c["name"] for c in d["concerns"]] == ["Odon de Brume", "Mervin"]
    assert d["changes"][0]["in_french"] == "Odon de Brume — frère ou sœur de — Mervin"


def test_a_draft_needs_a_change_existing_entities_and_a_valid_schema_I10_decisions(db):
    assert "au moins un changement" in call(db, "drafts.create", title="X", concerns=["odon"]).issues[0].message
    assert not call(db, "drafts.create", title="X", concerns=["personne"], changes=ODON_MERVIN).ok
    bad = [{"op": "set_attribute", "entity": "odon", "attribute": "titre", "value": "x"}]
    assert not call(db, "drafts.create", title="X", concerns=["odon"], changes=bad).ok
    yaml_changes = "- {op: set_attribute, entity: odon, attribute: title, value: régent}"
    assert call(db, "drafts.create", title="Odon régent ?", concerns=["odon"], changes_yaml=yaml_changes,
                confirm=True).ok  # une collision avec l'état n'empêche rien : c'est une hypothèse


def test_adopt_applies_and_discard_abandons(db):
    a = call(db, "drafts.create", title="A", concerns=["odon", "mervin"], changes=ODON_MERVIN, confirm=True).output["id"]
    b = call(db, "drafts.create", title="B", concerns=["odon"], confirm=True,
             changes=[{"op": "set_attribute", "entity": "odon", "attribute": "title", "value": "régent"}]).output["id"]
    assert call(db, "drafts.adopt", id=a).output["status"] == "applied"
    assert call(db, "drafts.discard", id=b).output["status"] == "abandoned"
    assert call(db, "drafts.list").output["drafts"] == []
    assert {d["status"] for d in call(db, "drafts.list", status="all").output["drafts"]} == {"applied", "abandoned"}


# --- Le geste dans l'atelier (I-ATL-11) ---

NOTES = "# Notes\n\nOdon de Brume est un homme massif.\n"


def atelier():
    from test_notes import FakeAdapter, NoteFinder, Profile
    w = base_world()
    doc = store.import_source(w, NOTES)
    layers.run_mentions(w, "reference", doc.doc_id)
    found = [{"subjects": ["odon"], "mentions": [], "facet": "appearance", "text": "un homme massif", "short": []}]
    layers.run_notes(w, "reference", doc.doc_id, NoteFinder(FakeAdapter(found), Profile()))
    return w, doc


def test_a_note_put_in_a_draft_is_drafted_not_proposed_and_not_reproposed_I_ATL_11():
    from test_notes import FakeAdapter, NoteFinder, Profile
    from worldkit.atelier import propose
    w, doc = atelier()
    note = next(a for a in layers.effective(w, "reference", doc) if a.kind == "note")
    outcome, written = gestures.to_draft(w, "reference", doc.doc_id, "note", note.ann_id, "Odon est-il massif ?")
    assert outcome.ok and written
    drafted = next(a for a in layers.effective(w, "reference", doc) if a.kind == "note")
    assert drafted.status == "drafted" and drafted.value["draft_id"] == outcome.edit_id
    rec = w.store.edit(outcome.edit_id)
    assert "draft" in rec.edit.tags and rec.edit.concerns == ["odon"] and "passage 1" in rec.edit.note
    assert rec.edit.changes[0].op == "add_note" and rec.edit.changes[0].document == doc.doc_id
    assert propose.note_drafts(w, "reference", doc) == {}  # ne part pas avec « Proposer »
    found = [{"subjects": ["odon"], "mentions": [], "facet": "appearance", "text": "un homme massif", "short": []}]
    assert layers.run_notes(w, "reference", doc.doc_id, NoteFinder(FakeAdapter(found), Profile())).skipped_by_author == 1


def test_a_draft_on_an_entity_not_yet_created_is_refused_I10_decision_2():
    from test_atelier_faits import source_with_ostrel, FakeFinder, facts_of
    w, doc = source_with_ostrel()
    member = ({"op": "add_relation", "from": "odon", "relation": "member_of", "to": "new:bertrand-ostrel"},
              "Il siège au conseil de Bertrand Ostrel.")
    layers.run_facts(w, "reference", doc.doc_id, FakeFinder([member]))
    fact = facts_of(w, doc)[0]
    with pytest.raises(ValueError, match="pas encore créées"):
        gestures.to_draft(w, "reference", doc.doc_id, "fact", fact.ann_id, "Odon membre ?")
