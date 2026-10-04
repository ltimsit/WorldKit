"""X-004 : C5, les faits entre entités confirmées, mesurés contre les changements du gold de b1 — sans vrai modèle
(chantier ingestion §6.5)."""

from __future__ import annotations

from support import VALMONT, base_world
from worldkit.ingest.batch import batch_documents, extraction_context
from worldkit.periphery.facts import FactFinder, chain_entities, evaluate_facts, gold_entities, output_schema
from worldkit.periphery.llm import Profile, UsageMeter
from worldkit.periphery.mentions import Mention, document_window

B1 = batch_documents(VALMONT / "docs" / "batches.yaml", "b1")
PROFILE = Profile("fake", "anthropic-api", "fake-model")


def fact(kind, subject, predicate, evidence, obj="", value=""):
    return {"kind": kind, "subject": subject, "predicate": predicate, "object": obj, "value": value,
            "evidence": evidence}


NOTES = [
    fact("attribute", "odon", "title", "Odon de Brume est le baron de Brume.", value="baron"),
    fact("relation", "new:conseil-marchands", "rules", "c'est le conseil des marchands qui gouverne Brume",
         obj="brume"),
    fact("relation", "odon", "member_of", "Odon siège lui-même au conseil des marchands", obj="new:conseil-marchands"),
    fact("relation", "odon", "involved_in", "une phrase qui n'est pas dans le texte", obj="la-chute"),
]


class FakeAdapter:
    def __init__(self):
        self.meter, self.calls = UsageMeter(), []

    def complete(self, system, prompt, schema):
        self.calls.append((system, prompt, schema))
        return {"facts": NOTES if "Texte :\n# Notes" in prompt else []}


def setup():
    world = base_world()
    state = world.state()
    return extraction_context(world, state), state


def windows():
    return [document_window(p) for p in B1]


def test_gold_entities_include_a_new_entity_created_in_another_document():
    """Le conseil des marchands est créé dans notes-baron et cité dans lieux-de-valmont (T-ING-07)."""
    context, _ = setup()
    by_doc = {w.doc_id: {e.id for e in gold_entities(w, VALMONT / "gold", context)} for w in windows()}
    assert "new:conseil-marchands" in by_doc["lieux-de-valmont"] and "aldren-ii" in by_doc["lieux-de-valmont"]


def test_prompt_gives_entities_and_only_compatible_relations():
    context, _ = setup()
    w = next(w for w in windows() if w.doc_id == "notes-baron")
    _, prompt = FactFinder(None, PROFILE).prompt(w, gold_entities(w, VALMONT / "gold", context), context.schema)
    assert "- odon (Character) : Odon de Brume" in prompt and "member_of" in prompt
    assert "haunts" not in prompt  # aucune créature dans la fenêtre
    assert '"anyOf"' not in str(output_schema())


def test_facts_are_located_by_their_evidence_and_measured_against_the_gold():
    context, state = setup()
    entities = {w.doc_id: gold_entities(w, VALMONT / "gold", context) for w in windows()}
    report = evaluate_facts(FactFinder(FakeAdapter(), PROFILE), windows(), entities, VALMONT / "gold",
                            context, state, "gold")
    s = report.summary()
    assert s["unplaced"] == 1  # la preuve inventée n'est rattachée à aucun passage
    p3 = next(p for p in report.passages if p.doc == "notes-baron" and p.index == 3)
    assert p3.expected & p3.found  # « le conseil gouverne Brume », avec l'identifiant du gold
    assert s["facts"]["tp"] == 3 and s["facts"]["fp"] == 0


def test_chain_entities_leave_doubts_out():
    context, _ = setup()
    mentions = [Mention("Odon", 0, 1, "Character", entity="odon"),
                Mention("conseil des marchands", 10, 1, "Faction", "model", entity="new:conseil des marchands"),
                Mention("régent de Brume", 30, 1, "Character", "model", rule="doubt", candidates=("brume",))]
    assert [e.id for e in chain_entities(mentions, context)] == ["new:conseil des marchands", "odon"]
