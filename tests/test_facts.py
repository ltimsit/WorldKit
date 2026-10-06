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


def test_silent_sentences_are_found_without_a_model_E_007():
    """Une phrase qui cite deux entités confirmées sans produire de fait reçoit la question ciblée ; une phrase
    qui a produit un fait, ou qui ne cite qu'une entité, ne la reçoit pas."""
    from worldkit.periphery.facts import Fact, gold_forms, silent_sentences
    context, _ = setup()
    w = next(w for w in windows() if w.doc_id == "notes-baron")
    entities = gold_entities(w, VALMONT / "gold", context)
    facts = [Fact({"op": "set_attribute", "entity": "odon", "attribute": "title", "value": "baron"},
                  "Odon de Brume est le baron de Brume.", 1)]
    silent = silent_sentences(w, facts, gold_forms(w, VALMONT / "gold", entities))
    texts = [s.sentence for s in silent]
    assert any(t.startswith("Odon est le vassal du roi Mervin") for t in texts)
    assert not any(t.startswith("Odon de Brume est le baron") for t in texts)


def test_relation_probe_asks_without_the_list_of_relations():
    from worldkit.periphery.facts import RelationProbe, Silent

    class Probe(FakeAdapter):
        def complete(self, system, prompt, schema):
            self.calls.append((system, prompt, schema))
            return {"relations": [{"subject": "odon", "relation": "vassal_of", "object": "mervin",
                                   "phrase": "est le vassal de"},
                                  {"subject": "odon", "relation": "knows", "object": "inconnu", "phrase": "x"}]}
    context, _ = setup()
    w = next(w for w in windows() if w.doc_id == "notes-baron")
    adapter = Probe()
    silent = Silent(2, "Odon est le vassal du roi Mervin, à qui il a prêté serment à Hautval.", ["hautval", "mervin", "odon"])
    facts = RelationProbe(adapter, PROFILE).ask(silent, gold_entities(w, VALMONT / "gold", context))
    _, prompt, _ = adapter.calls[0]
    assert "Relations possibles" not in prompt and "member_of" not in prompt  # aucune liste : le hors schéma est libre
    assert [f.draft["relation"] for f in facts] == ["vassal_of"]  # objet hors de la phrase : écarté


def test_pair_signal_works_at_passage_scope_and_sees_a_sentence_with_a_fact_X_008():
    """« elle deteste les bateliers » : Ysolde n'est nommée que dans la phrase d'avant, qui a produit un fait."""
    from test_corpus_corbelle import CORBELLE, corbelle_world
    from test_corpus_corbelle import documents as corbelle_documents
    from worldkit.periphery.facts import Fact, gold_forms, silent_sentences
    world = corbelle_world()
    context = extraction_context(world, world.state())
    w = next(document_window(p) for p in corbelle_documents() if "brouillon" in str(p))
    entities = gold_entities(w, CORBELLE / "gold", context)
    facts = [Fact({"op": "add_relation", "from": "ysolde-marcastel", "relation": "lives_in", "to": "pont-aux-anes"},
                  "Ysolde (la soeur) elle tient l'apothicairerie pres du pont-aux-anes.", 4)]
    forms = gold_forms(w, CORBELLE / "gold", entities)
    by_sentence = [s for s in silent_sentences(w, facts, forms) if s.passage == 4]
    by_pair = [s for s in silent_sentences(w, facts, forms, by_pair=True) if s.passage == 4]
    assert not by_sentence and by_pair and "bateliers" in by_pair[0].entities


def test_probe_can_be_given_known_relations_as_a_preference_X_008():
    from worldkit.periphery.facts import RelationProbe, Silent
    context, _ = setup()
    w = next(w for w in windows() if w.doc_id == "notes-baron")
    silent = Silent(2, "Odon est le vassal du roi Mervin.", ["mervin", "odon"])
    plain = RelationProbe(None, PROFILE).prompt(silent, gold_entities(w, VALMONT / "gold", context), context.schema)
    listed = RelationProbe(None, PROFILE, with_relations=True).prompt(silent, gold_entities(w, VALMONT / "gold", context),
                                                                      context.schema)
    assert "Relations connues" not in plain[1] and "sibling_of" in listed[1] and "haunts" not in listed[1]
    assert listed[0].startswith(plain[0])


def test_critic_judges_only_what_raises_a_question_and_sets_aside_without_deciding_X_009():
    """Choix 2 : un fait non soutenu est mis de côté (visible) ; un support n'est jamais jugé."""
    from worldkit.periphery.facts import Critic

    class Judge(FakeAdapter):
        def complete(self, system, prompt, schema):
            self.calls.append((system, prompt, schema))
            return {"verdict": "not_supported" if "membre de" in prompt else "supported", "reason": "test"}
    context, state = setup()
    entities = {w.doc_id: gold_entities(w, VALMONT / "gold", context) for w in windows()}
    critic_adapter = Judge()
    report = evaluate_facts(FactFinder(FakeAdapter(), PROFILE), windows(), entities, VALMONT / "gold", context, state,
                            "gold", critic=Critic(critic_adapter, PROFILE))
    assert report.summary()["critic"]["not_supported"] == 1  # member_of mis de côté
    p4 = next(p for p in report.passages if p.doc == "notes-baron" and p.index == 4)
    assert not any(dict(k).get("relation") == "member_of" for k in p4.found)  # mis de côté : absent des faits
    assert all("titre : baron" not in p for _, p, _ in critic_adapter.calls)  # « odon title baron » : support, pas jugé
    assert "Un fait secret" in critic_adapter.calls[0][0]


# --- X-014 : candidats classés, choix sans modèle ---

def corbelle_setup():
    from test_corpus_corbelle import CORBELLE, corbelle_world
    from test_corpus_corbelle import documents as corbelle_documents
    world = corbelle_world()
    context = extraction_context(world, world.state())
    w = next(document_window(p) for p in corbelle_documents() if "la-sorgue" in str(p))
    return context, gold_entities(w, CORBELLE / "gold", context)


def test_choice_takes_the_first_known_candidate_and_keeps_the_exact_form_X_014():
    """« la mère de » : mother_of (exact, hors schéma) puis parent_of (plus général, connu) → parent_of retenue."""
    from worldkit.periphery.facts import choose_candidate
    context, entities = corbelle_setup()
    types = {e.id: e.type for e in entities}
    chosen, exact = choose_candidate([
        {"subject": "agathe", "relation": "mother_of", "object": "new:bertrand-ostrel", "link": "same"},
        {"subject": "agathe", "relation": "parent_of", "object": "new:bertrand-ostrel", "link": "broader"}],
        types, context.schema)
    assert chosen["relation"] == "parent_of" and exact == "mother_of"
    alone, none = choose_candidate([{"subject": "agathe", "relation": "conspires_with",
                                     "object": "new:bertrand-ostrel", "link": "same"}], types, context.schema)
    assert alone["relation"] == "conspires_with" and none == ""  # rien de connu : hors schéma, l'auteur fixera


def test_a_known_relation_with_wrong_types_is_not_chosen_X_014():
    from worldkit.periphery.facts import choose_candidate
    context, entities = corbelle_setup()
    types = {e.id: e.type for e in entities}
    chosen, _ = choose_candidate([
        {"subject": "agathe", "relation": "parent_of", "object": "la-sorgue", "link": "same"},
        {"subject": "agathe", "relation": "knows_of", "object": "la-sorgue", "link": "same"}],
        {**types, "la-sorgue": "Place"}, context.schema)
    assert chosen["relation"] == "knows_of"  # parent_of va d'un personnage vers un personnage


def test_a_broader_candidate_alone_is_an_inference_and_is_dropped_X_014():
    """« tient l'apothicairerie près du pont » : lives_in marqué « plus général », sans sens exact → rien (E-010)."""
    from worldkit.periphery.facts import choose_candidate
    context, entities = corbelle_setup()
    chosen, exact = choose_candidate([{"subject": "agathe", "relation": "lives_in", "object": "saint-fiacre",
                                       "link": "broader"}], {e.id: e.type for e in entities}, context.schema)
    assert chosen is None and exact == ""


def test_ranked_probe_asks_for_candidates_and_the_critic_hears_the_exact_form_X_014():
    from worldkit.periphery.facts import Critic, RelationProbe, Silent

    class Probe(FakeAdapter):
        def complete(self, system, prompt, schema):
            self.calls.append((system, prompt, schema))
            return {"relations": [{"phrase": "est la mère de", "candidates": [
                {"subject": "agathe", "relation": "mother_of", "object": "new:bertrand-ostrel", "link": "same"},
                {"subject": "agathe", "relation": "parent_of", "object": "new:bertrand-ostrel", "link": "broader"}]}]}
    context, entities = corbelle_setup()
    adapter = Probe()
    silent = Silent(3, "mère agathe c la mère d'Ostrel.", ["agathe", "new:bertrand-ostrel"])
    probe = RelationProbe(adapter, PROFILE, ranked=True)
    facts = probe.ask(silent, entities, context.schema)
    system, prompt, schema = adapter.calls[0]
    assert "candidates" in system and "Relations connues" in prompt and "+ranked" in probe.version
    assert [(f.draft["relation"], f.exact) for f in facts] == [("parent_of", "mother_of")]
    assert silent.answer[0]["candidates"] == ["mother_of (same)", "parent_of (broader)"]
    _, critic_prompt = Critic(None, PROFILE).prompt(facts[0], silent.sentence, entities, context.schema)
    assert "plus précisément « est la mère de » (mother_of)" in critic_prompt


def test_critic_v3_adds_two_rules_without_dropping_the_proximity_motive_X_015():
    from worldkit.periphery.facts import CRITIC_SYSTEM, Critic, Fact
    context, entities = corbelle_setup()
    fact = Fact({"op": "add_relation", "from": "agathe", "relation": "parent_of", "to": "new:bertrand-ostrel"}, "x", 3)
    v2 = Critic(None, PROFILE).prompt(fact, "x", entities, context.schema)[0]
    v3 = Critic(None, PROFILE, v3=True).prompt(fact, "x", entities, context.schema)[0]
    assert v2 == CRITIC_SYSTEM and v3.startswith(CRITIC_SYSTEM) and "tisserands" in v3 and "près de" in v3
    assert Critic(None, PROFILE, v3=True).version.startswith("critic-3")
