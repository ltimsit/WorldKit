"""Cohérence du corpus ciblé Corbelle (corpus/corbelle-v1) : le gold ne se contredit pas avec le monde.

Comme `tools/check_corpus.py` pour Valmont : ce test ne mesure aucune couche, il garantit que le corpus est utilisable
(passages annotés, identifiants existants, attributs et relations du schéma, hors schéma déclaré, silences vides).
"""

from __future__ import annotations

from pathlib import Path

import yaml

from support import ROOT
from worldkit.ingest.batch import batch_documents, extraction_context
from worldkit.ingest.declaration import read_document
from worldkit.periphery.evaluation import evaluate
from worldkit.periphery.extraction import OracleExtractor

CORBELLE = ROOT / "corpus" / "corbelle-v1" / "corbelle"
OUT_OF_SCHEMA = {"hates"}  # absent du schéma exprès : question ciblée (E-007)


def corbelle_world():
    from worldkit.core.journal.models import parse_edit
    from worldkit.core.world import World
    world = World.create(":memory:", CORBELLE / "world.yaml")
    for raw in yaml.safe_load((CORBELLE / "edits" / "base.yaml").read_text(encoding="utf-8"))["edits"]:
        outcome = world.apply(parse_edit(raw))
        assert outcome.status == "applied", [str(i) for i in outcome.issues]
    return world


def gold():
    return [yaml.safe_load(p.read_text(encoding="utf-8")) for p in sorted((CORBELLE / "gold").glob("*.yaml"))]


def documents():
    return batch_documents(CORBELLE / "docs" / "batches.yaml", "c1")


def test_every_passage_has_exactly_one_gold_entry():
    entries = {g["document"]: g["passages"] for g in gold()}
    for path in documents():
        doc = read_document(path)
        for p in doc.passages:
            matches = [e for e in entries[doc.doc_id] if p.text.startswith(e["starts_with"])]
            assert len(matches) == 1, (doc.doc_id, p.index, len(matches))
            assert matches[0]["index"] == p.index


def test_gold_refers_to_the_world_and_its_schema():
    world = corbelle_world()
    state = world.state()
    schema = state.world
    new_types = {c["entity"]: c["type"] for g in gold() for p in g["passages"] for c in p.get("changes") or []
                 if c["op"] == "create_entity"}

    def type_of(eid):
        if eid.startswith("new:"):
            assert eid in new_types, f"entité nouvelle sans création : {eid}"
            return new_types[eid]
        assert eid in state.entities, f"entité inconnue : {eid}"
        return state.entities[eid].type

    for g in gold():
        for p in g["passages"]:
            for eid in (p.get("mentions") or {}).values():
                type_of(eid)
            for c in p.get("changes") or []:
                if c["op"] in ("set_attribute", "add_value"):
                    assert c["attribute"] in schema.attributes_of(type_of(c["entity"])), c
                elif c["op"] == "add_relation":
                    type_of(c["from"]), type_of(c["to"])
                    assert c["relation"] in schema.relations or c["relation"] in OUT_OF_SCHEMA, c
            if p.get("silent"):
                assert not p.get("changes"), f"un passage silencieux n'attend aucun changement : {p['starts_with']}"


def test_mentions_appear_in_their_passage():
    texts = {}
    for path in documents():
        doc = read_document(path)
        texts.update({(doc.doc_id, p.index): p.text for p in doc.passages})
    for g in gold():
        for p in g["passages"]:
            for surface in p.get("mentions") or {}:
                assert surface.casefold() in texts[(g["document"], p["index"])].casefold(), (g["document"], surface)


def test_the_oracle_measured_against_itself_is_perfect():
    world = corbelle_world()
    state = world.state()
    oracle = OracleExtractor(CORBELLE / "gold")
    s = evaluate(oracle, oracle, CORBELLE / "gold", documents(), extraction_context(world, state), state=state).summary()
    assert (s["precision"], s["recall"]) == (1.0, 1.0)
