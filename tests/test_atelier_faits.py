"""I9 — atelier, deuxième incrément : les faits. Couche « faits » (chaîne du chantier entre les entités de la source),
gestes sur un fait, « Proposer » avec les faits (Q1), second lot de faits après les entités (Q2), écran (Q3, Q4).
Aucun appel à un vrai modèle."""

from __future__ import annotations

import pytest

from support import base_world
from worldkit.atelier import gestures, layers, store
from worldkit.atelier import propose as proposing
from worldkit.periphery.facts import Fact

NOTES = """# Notes du baron

Odon de Brume est le baron de Brume. Il siège au conseil de Bertrand Ostrel.

On dit que le Loup de cendre hante Hautval.
"""


class FakeFinder:
    """C5 simulé : des faits fixes, preuve recopiée du texte."""

    meter = None

    def __init__(self, facts):
        self.facts, self.rejected, self.calls = facts, [], 0

    def find(self, window, entities, schema, state=None):
        self.calls += 1
        ids = {e.id for e in entities}
        return [Fact(dict(d), ev, window.passage_at(window.text.find(ev)) if ev in window.text else None)
                for d, ev in self.facts if {d.get("from", d.get("entity")), d.get("to", "x")} - {"x"} <= ids | {"x"}]


class FakeCritic:
    meter = None

    def __init__(self, verdicts):
        self.verdicts = verdicts

    def judge(self, fact, passage, entities, schema, other_names=None):
        return {"verdict": self.verdicts.get(fact.draft.get("relation") or fact.draft.get("attribute"), "supported"),
                "reason": "simulé"}


MEMBER = ({"op": "add_relation", "from": "odon", "relation": "member_of", "to": "new:bertrand-ostrel"},
          "Il siège au conseil de Bertrand Ostrel.")
TITLE = ({"op": "set_attribute", "entity": "odon", "attribute": "title", "value": "baron"},
         "Odon de Brume est le baron de Brume.")
HAUNTS = ({"op": "add_relation", "from": "loup-de-cendre", "relation": "haunts", "to": "hautval"},
          "On dit que le Loup de cendre hante Hautval.")


def source_with_ostrel():
    """Odon et le Loup reconnus par la couche « mentions » ; Bertrand Ostrel ajouté par l'auteur (nouvelle entité)."""
    world = base_world()
    doc = store.import_source(world, NOTES)
    layers.run_mentions(world, "reference", doc.doc_id)
    p = next(x for x in doc.passages if "Ostrel" in x.text)
    start = p.text.index("Bertrand Ostrel")
    gestures.gesture(world, "reference", doc.doc_id, "add", passage=p.index, start=start,
                     end=start + len("Bertrand Ostrel"), entity="new", type_="Character")
    return world, doc


def facts_of(world, doc):
    return [a for a in layers.effective(world, "reference", doc) if a.kind == "fact"]


def test_the_facts_layer_works_between_the_source_entities_and_writes_one_annotation_per_fact_I9():
    world, doc = source_with_ostrel()
    entities, forms = layers.confirmed_entities(world, "reference", doc)
    assert {"odon", "new:bertrand-ostrel", "loup-de-cendre", "hautval"} <= {e.id for e in entities}
    report = layers.run_facts(world, "reference", doc.doc_id, FakeFinder([MEMBER, TITLE, HAUNTS]))
    assert report.proposed == 3 and report.withheld == 1  # « On dit que » : une rumeur, retenue (C4)
    by_relation = {a.value["draft"].get("relation") or "title": a for a in facts_of(world, doc)}
    assert by_relation["haunts"].value["voice"] == "attribution" and layers.fact_excluded(by_relation["haunts"])
    assert by_relation["member_of"].start is not None  # la preuve est située dans le passage, pour la surligner


def test_an_unconfirmed_new_entity_does_not_feed_the_facts_layer_I9():
    world = base_world()
    doc = store.import_source(world, NOTES)

    class Found:
        version = "fake"

        def find(self, window, context):
            from worldkit.periphery.mentions import Mention
            i = window.text.find("Bertrand Ostrel")
            return [Mention("Bertrand Ostrel", i, window.passage_at(i), "Character", "model")]
    layers.run_mentions(world, "reference", doc.doc_id, Found())
    ids = {e.id for e in layers.confirmed_entities(world, "reference", doc)[0]}
    assert "odon" in ids and not any(i.startswith("new:") for i in ids)  # nouvelle mais non confirmée


def test_the_critic_sets_aside_and_the_author_takes_back_Q1():
    """Un support (« Odon — titre : baron », déjà dans l'état) n'est pas jugé ; un fait mis de côté se reprend."""
    world, doc = source_with_ostrel()
    layers.run_facts(world, "reference", doc.doc_id, FakeFinder([MEMBER, TITLE]),
                     critic=FakeCritic({"member_of": "not_supported"}))
    by = {a.value["draft"].get("relation") or a.value["draft"].get("attribute"): a for a in facts_of(world, doc)}
    assert by["title"].value["support"] and by["title"].value["verdict"] is None
    member = by["member_of"]
    assert member.value["verdict"] == "not_supported" and layers.fact_excluded(member)
    gestures.fact_gesture(world, "reference", doc.doc_id, "keep", member.ann_id)  # reprendre
    taken = next(a for a in facts_of(world, doc) if a.value["draft"].get("relation") == "member_of")
    assert taken.by_author and not layers.fact_excluded(taken)


def test_correcting_adding_and_removing_facts_and_a_relaunch_respects_them_R_HIS_01():
    world, doc = source_with_ostrel()
    finder = FakeFinder([MEMBER, TITLE])
    layers.run_facts(world, "reference", doc.doc_id, finder)
    member = next(a for a in facts_of(world, doc) if a.value["draft"].get("relation") == "member_of")
    title = next(a for a in facts_of(world, doc) if a.value["draft"].get("attribute") == "title")
    gestures.fact_gesture(world, "reference", doc.doc_id, "correct", member.ann_id,
                          draft={"op": "add_relation", "from": "new:bertrand-ostrel", "relation": "member_of",
                                 "to": "odon"})
    gestures.fact_gesture(world, "reference", doc.doc_id, "remove", title.ann_id)
    gestures.fact_gesture(world, "reference", doc.doc_id, "add", passage=member.passage,
                          draft={"op": "add_relation", "from": "odon", "relation": "rules", "to": "brume"})
    with pytest.raises(ValueError, match="il manque"):
        gestures.fact_gesture(world, "reference", doc.doc_id, "add", passage=member.passage,
                              draft={"op": "add_relation", "from": "odon", "relation": "rules", "to": ""})
    report = layers.run_facts(world, "reference", doc.doc_id, finder)  # relance : ne refait pas ce que l'auteur a décidé
    assert report.skipped_by_author == 2 and report.proposed == 0
    drafts = [d for ds in proposing.fact_drafts(world, "reference", doc).values() for d in ds]
    assert {"op": "add_relation", "from": "new:bertrand-ostrel", "relation": "member_of", "to": "odon"} in drafts
    assert {"op": "add_relation", "from": "odon", "relation": "rules", "to": "brume"} in drafts
    assert not any(d.get("attribute") == "title" for d in drafts)  # retiré


def test_first_propose_sends_entities_and_facts_together_Q1():
    world, doc = source_with_ostrel()
    layers.run_facts(world, "reference", doc.doc_id, FakeFinder([MEMBER, HAUNTS]))
    report = proposing.propose(world, "reference", doc.doc_id)
    from worldkit.ingest.queue import load
    changes = [c.change for p in load(world) for c in p.changes]
    created = next(c.entity for c in changes if c.op == "create_entity")
    assert any(c.op == "add_relation" and c.relation == "member_of" and c.to == created for c in changes)
    assert not any(c.op == "add_relation" and c.relation == "haunts" for c in changes)  # rumeur retenue : ne part pas
    assert report.batch_id == proposing.batch_id_of(doc)


def test_facts_after_the_entities_go_in_a_second_lot_and_refer_to_the_pending_entity_Q2():
    world, doc = source_with_ostrel()
    proposing.propose(world, "reference", doc.doc_id)  # les entités partent d'abord
    layers.run_facts(world, "reference", doc.doc_id, FakeFinder([MEMBER, TITLE]))
    report = proposing.propose(world, "reference", doc.doc_id)
    assert report.batch_id == proposing.facts_batch_id_of(doc) and report.proposals
    from worldkit.ingest.queue import load
    facts_lot = [p for p in load(world) if p.batch == report.batch_id]
    changes = [c.change for p in facts_lot for c in p.changes]
    assert not any(c.op == "create_entity" for c in changes)
    member = next(c for c in changes if c.op == "add_relation")
    assert member.to == "bertrand-ostrel"  # l'entité en attente, désignée par son identifiant (T-ING-07)
    from worldkit.ingest.batch import BatchError
    with pytest.raises(BatchError, match="déjà proposée"):
        proposing.propose(world, "reference", doc.doc_id)


def test_atelier_facts_by_the_service_and_the_screen(tmp_path):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    from test_service import make_world
    from worldkit.service.session import Session
    from worldkit.web import create_app
    db = tmp_path / "valmont.db"
    make_world(db)
    s = Session(db)
    doc_id = s.call("atelier.import", {"text": NOTES}).output["doc_id"]
    s.call("atelier.run", {"doc_id": doc_id})
    pending = s.call("atelier.run", {"doc_id": doc_id, "layer": "facts"})
    assert pending.status == "pending" and pending.output["estimate"]["calls"] >= 1  # I-LLM-01 : rien sans confirmation
    from worldkit.core.world import World
    world = World.open(db)
    doc = store.source(world, doc_id)
    layers.run_facts(world, "reference", doc_id, FakeFinder([TITLE, HAUNTS]))
    world.close()
    view = s.call("atelier.view", {"doc_id": doc_id}).output
    assert all(a["kind"] == "mention" for p in view["passages"] for a in p["annotations"])
    facts = [f for p in view["passages"] for f in p["facts"]]
    assert {f["label"] for f in facts} >= {"Odon de Brume — titre : baron"}
    added = s.call("atelier.annotate", {"doc_id": doc_id, "kind": "fact", "action": "add", "passage": 1,
                                        "subject": "odon", "relation": "rules", "object": "brume"})
    assert added.status == "ok"
    c = TestClient(create_app(db))
    page = c.get(f"/atelier/{doc_id}").text
    assert "Couche « faits »" in page and "rumeur" in page and "fact-off" in page  # écarté, grisé (Q3)
    assert "Ajouter un fait" in page
    assert doc.doc_id == doc_id
