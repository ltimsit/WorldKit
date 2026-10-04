"""X-007 : recoupement par score (E-008), texte barré (E-009), contrôles de C5 (E-011) — sans modèle."""

from __future__ import annotations

from support import base_world
from test_corpus_corbelle import CORBELLE, corbelle_world, documents

CORBELLE_GOLD = CORBELLE / "gold"
from worldkit.ingest.batch import extraction_context
from worldkit.periphery.facts import Confirmed, Fact, check_facts
from worldkit.periphery.matching import best_matches, decide, fold, similarity
from worldkit.periphery.mentions import Mention, Resolver, document_window, known_mentions


def test_fold_compares_without_rewriting():
    assert fold("le Pont-aux-Ânes") == fold("pont-aux-anes") == "pont aux anes"
    assert fold("st fiacre") == "saint fiacre"


def test_similarity_covers_typos_partial_names_acronyms_and_initials():
    assert similarity("Jehan Marcastell", "Jehan Marcastel") > 0.95       # faute
    assert similarity("st fiacre", "l'abbaye Saint-Fiacre") >= 0.9       # abréviation, nom partiel
    assert similarity("GdB", "la Guilde des Bateliers") >= 0.9           # sigle
    assert similarity("Jehan L.", "Jehan Leblond") > similarity("Jehan L.", "Jehan Marcastel")  # initiale
    assert similarity("Roi Gris", "Aldren II") < 0.8                     # aucun indice : pas de rattachement


def test_three_outcomes_link_doubt_new():
    candidates = {"jehan-marcastel": ["Jehan Marcastel"], "jehan-leblond": ["Jehan Leblond"]}
    assert decide(best_matches("Jehan Marcastell", candidates)) == ("jehan-marcastel", ())
    assert decide(best_matches("jehan", candidates)) == (None, ("jehan-leblond", "jehan-marcastel"))  # homonymes
    assert decide(best_matches("Bertrand Ostrel", candidates)) == (None, ())


def corbelle_resolver():
    world = corbelle_world()
    state = world.state()
    context = extraction_context(world, state)
    return Resolver.from_state(context, state), context


def test_variants_of_known_names_are_linked_not_created_E_008():
    r, _ = corbelle_resolver()
    for text, type_, expected in (("Jehan Marcastell", "Character", "jehan-marcastel"),
                                  ("pont-aux-anes", "Place", "pont-aux-anes"), ("st fiacre", "Place", "saint-fiacre"),
                                  ("GdB", "Faction", "bateliers"), ("Jehan L.", "Character", "jehan-leblond")):
        assert r.resolve(Mention(text, 0, 1, type_, "model")).entity == expected, text
    jehan = r.resolve(Mention("jehan", 0, 1, "Character", "model"))
    assert jehan.entity is None and jehan.rule == "doubt"  # deux Jehan : jamais au hasard


def test_new_entities_of_a_batch_are_grouped_whatever_the_order():
    """« Bertrand Ostrel », « Bertrand Ostrell », « Ostrel » : une seule entité nouvelle, dans tout ordre (R-PRI-03)."""
    for order in (["Bertrand Ostrel", "Bertrand Ostrell", "Ostrel"], ["Ostrel", "Bertrand Ostrell", "Bertrand Ostrel"]):
        r, _ = corbelle_resolver()
        mentions = [r.resolve(Mention(t, 0, 1, "Character", "model")) for t in order]
        r.cluster_new(mentions)
        assert {m.entity for m in mentions} == {"new:bertrand ostrel"}, order  # la forme centrale, pas la fautive


def test_struck_text_is_not_a_mention_E_009():
    _, context = corbelle_resolver()
    window = next(document_window(p) for p in documents() if "brouillon" in str(p))
    assert window.struck and "vouivre" in window.text[window.struck[0][0]:window.struck[0][1]]
    assert "vouivre" not in {m.entity for m in known_mentions(window, context.entities)}


def test_controls_after_c5_E_011():
    world = corbelle_world()
    state = world.state()
    entities = [Confirmed("new:bertrand-ostrel", "Character", "Bertrand Ostrel"), Confirmed("bateliers", "Faction",
                "la Guilde des Bateliers"), Confirmed("la-sorgue", "Place", "la Sorgue"),
                Confirmed("jehan-marcastel", "Character", "Jehan Marcastel")]
    facts = [Fact({"op": "add_relation", "from": "new:bertrand-ostrel", "relation": "rules", "to": "bateliers"}, "", 6),
             Fact({"op": "add_value", "entity": "la-sorgue", "attribute": "aliases", "value": "la sorgue"}, "", 1),
             Fact({"op": "set_attribute", "entity": "jehan-marcastel", "attribute": "title", "value": "bourgmèstre"}, "", 1),
             Fact({"op": "add_relation", "from": "new:bertrand-ostrel", "relation": "member_of", "to": "bateliers"}, "", 6)]
    rejected = []
    kept = check_facts(facts, entities, state.world, state, rejected)
    assert [r for _, r in rejected][0].startswith("types") and len(rejected) == 2
    assert [f.draft["relation"] for f in kept if f.draft["op"] == "add_relation"] == ["member_of"]
    assert next(f for f in kept if f.draft["op"] == "set_attribute").draft["value"] == "bourgmestre"


def test_valmont_resolution_does_not_regress():
    world = base_world()
    state = world.state()
    r = Resolver.from_state(extraction_context(world, state), state)
    assert r.resolve(Mention("roi Mervin", 0, 1, "Character", "model")).entity == "mervin"
    assert r.resolve(Mention("Odon", 0, 1, "Character", "model")).entity == "odon"
    assert r.resolve(Mention("Brume-sur-Mer", 0, 1, "Place", "model")).entity == "brume"
    assert r.resolve(Mention("Le Roi Gris", 0, 1, "Character", "model")).rule == "new"


def test_enunciation_without_a_model_X_010():
    """Rumeur ou paroles rapportées : attribution, sans fait (R-DEC-03 ; rumeurs hors périmètre, §1.4). Note de
    travail de l'auteur : silence (AX-E1, AX-E5)."""
    from worldkit.periphery.facts import enunciation
    assert enunciation("les vieux disent que c'est la vouivre qui la fait deborder") == "attribution"
    assert enunciation("« Le baron est un traître », murmure-t-on sur les quais.") == "attribution"
    assert enunciation("TODO : trouver un nom pour la taverne du port.") == "note"
    assert enunciation("idée : et si le passeur trahissait la guilde ?") == "note"
    assert enunciation("Jehan Marcastel : bourgmèstre, marié à Clémence (à créer)") is None
    assert enunciation("Secret (les joueurs le savent pas) : mère agathe c la mère d'Ostrel.") is None  # un secret est un fait


def test_a_working_note_creates_no_entity_X_010():
    """« et si le passeur trahissait la guilde pendant la fête des lanternes ? » : pas d'entité « fête des lanternes »."""
    from worldkit.periphery.mentions import MentionFinder, evaluate_mentions

    class Fake:
        def __init__(self):
            from worldkit.periphery.llm import UsageMeter
            self.meter = UsageMeter()

        def complete(self, system, prompt, schema):
            return {"mentions": [{"text": "fête des lanternes", "type": "Event", "confidence": "sure", "reason": ""}]}
    from worldkit.periphery.llm import Profile
    world = corbelle_world()
    state = world.state()
    context = extraction_context(world, state)
    finder = MentionFinder(Fake(), Profile("fake", "anthropic-api", "m"))
    plain = evaluate_mentions(finder, documents(), CORBELLE_GOLD, context, state).summary()["c2"]
    silent = evaluate_mentions(finder, documents(), CORBELLE_GOLD, context, state, with_enunciation=True).summary()["c2"]
    assert "fête des lanternes" in plain["false_new"] and "fête des lanternes" not in silent["false_new"]
