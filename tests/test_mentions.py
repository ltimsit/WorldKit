"""X-002 : C1 (noms connus sans modèle, mentions par le modèle sur le document entier) et C2 (recoupement
déterministe), mesurés contre les mentions du gold de b1 — sans vrai modèle (chantier ingestion §6.5)."""

from __future__ import annotations

from support import VALMONT, base_world
from worldkit.ingest.batch import batch_documents, extraction_context
from worldkit.periphery.llm import Profile, UsageMeter
from worldkit.periphery.mentions import (
    Mention, MentionFinder, Resolver, document_window, evaluate_mentions, known_mentions, output_schema,
)

B1 = batch_documents(VALMONT / "docs" / "batches.yaml", "b1")
PROFILE = Profile("fake", "anthropic-api", "fake-model")


def mention(text, type_):
    return {"text": text, "type": type_, "confidence": "sure", "reason": ""}


ANSWERS = {
    "# Notes": [mention("Odon de Brume", "Character"), mention("Odon", "Character"), mention("le baron", "Character"),
                mention("conseil des marchands", "Faction"), mention("Cercle des Cendres", "Faction"),
                mention("Mervin", "Character"), mention("Hautval", "Place"), mention("Brume", "Place")],
    "# Lieux": [mention("Brume-sur-Mer", "Place"), mention("taverne du Héron", "Place"),
                mention("Le Roi Gris", "Character"), mention("conseil des marchands", "Faction"),
                mention("Loup des brumes", "Creature")],  # texte absent : introuvable
}


class FakeAdapter:
    def __init__(self):
        self.meter, self.calls = UsageMeter(), []

    def complete(self, system, prompt, schema):
        self.calls.append((system, prompt, schema))
        window = prompt.split("Texte :\n", 1)[1]
        return {"mentions": next(v for k, v in ANSWERS.items() if window.startswith(k))}


def setup():
    world = base_world()
    state = world.state()
    return extraction_context(world, state), state


def test_window_is_the_whole_document_and_passages_keep_their_place():
    window = next(document_window(p) for p in B1 if "lieux" in str(p))
    assert window.text.startswith("# Lieux de Valmont") and len(window.passages) == 5
    assert window.passage_at(window.text.index("Le Roi Gris")) == 4
    assert window.passage_at(window.text.index("Lieux")) is None  # le titre n'est dans aucun passage


def test_known_names_are_found_without_a_model():
    context, _ = setup()
    window = next(document_window(p) for p in B1 if "notes-baron" in str(p))
    found = {(m.text, m.entity) for m in known_mentions(window, context.entities)}
    assert ("Odon de Brume", "odon") in found and ("Hautval", "hautval") in found and ("Brume", "brume") in found
    starts = [m.start for m in known_mentions(window, context.entities)]
    assert len(starts) == len(set(starts))  # « Brume » dans « Odon de Brume » écarté


def test_resolution_cascade_is_deterministic():
    context, state = setup()
    r = Resolver.from_state(context, state)
    assert r.resolve(Mention("le baron", 0, 1, "Character")).entity == "odon"          # titre porté par une seule
    assert r.resolve(Mention("roi Mervin", 0, 1, "Character")).entity == "mervin"      # nom connu contenu
    assert r.resolve(Mention("Odon", 0, 1, "Character")).entity == "odon"              # partie d'un seul nom
    assert r.resolve(Mention("Le Roi Gris", 0, 1, "Character")).entity == "new:roi gris"
    roi = r.resolve(Mention("le roi", 0, 1, "Character"))
    assert roi.entity is None and set(roi.candidates) == {"aldren-ii", "mervin"}       # doute laissé à l'auteur


def test_mention_finder_asks_one_question_without_known_entities():
    context, _ = setup()
    adapter = FakeAdapter()
    MentionFinder(adapter, PROFILE).find(document_window(B1[0]), context)
    system, prompt, schema = adapter.calls[0]
    assert "Entités connues" not in prompt and "odon" not in prompt  # aucune liste des entités connues
    assert schema == output_schema(sorted(context.schema.types))
    assert '"anyOf"' not in str(schema)  # aucune union : sous la limite de l'API


def test_mentions_measured_against_the_gold_of_b1():
    context, state = setup()
    baseline = evaluate_mentions(None, B1, VALMONT / "gold", context, state).summary()
    assert (baseline["c1"]["tp"], baseline["c1"]["fn"], baseline["c2"]["accuracy"]) == (18, 10, 1.0)  # « le baron » par le titre
    report = evaluate_mentions(MentionFinder(FakeAdapter(), PROFILE), B1, VALMONT / "gold", context, state, repeat=2)
    s = report.summary()
    assert s["c1"]["fn"] == 0 and s["c1"]["recall"] == 1.0
    assert [m.text for m in report.unplaced] == ["Loup des brumes"]
    conseil = {m.entity for p in report.passages for s_, m in p.matched if s_ == "conseil des marchands"}
    assert conseil == {"new:conseil des marchands"}  # une seule entité nouvelle dans tout le lot (T-ING-07)
    roi_gris = next(m for p in report.passages for s_, m in p.matched if s_ == "Le Roi Gris")
    assert roi_gris.entity == "new:roi gris"  # savoir absent du texte : à l'auteur (E-002)
    assert s["c2"]["resolved_ok"] == s["c1"]["tp"] - 1 and s["stability"] == {"lieux-de-valmont": 1.0, "notes-baron": 1.0}


def test_nested_mentions_keep_the_known_name_inside_a_longer_designation():
    """« baron de Brume » (modèle) n'efface pas « Brume » (connu) : les mentions s'imbriquent."""
    from worldkit.periphery.mentions import merge
    known = [Mention("Brume", 20, 1, "Place", "known", entity="brume")]
    model = [Mention("baron de Brume", 11, 1, "Character", "model"), Mention("Brume", 20, 1, "Place", "model")]
    merged = merge(known, model)
    assert [(m.text, m.source) for m in merged] == [("baron de Brume", "model"), ("Brume", "known")]


def test_replay_answers_traced_prompts_without_calling(tmp_path, monkeypatch):
    """Rejouer les traces : mêmes prompts, mêmes réponses, aucun appel ; un prompt non tracé est une erreur."""
    import pytest
    from worldkit.periphery.llm.usage import ReplayAdapter
    context, state = setup()
    monkeypatch.setenv("WORLDKIT_LLM_LOG_DIR", str(tmp_path))
    live = FakeAdapter()
    for window in map(document_window, B1):  # le faux adaptateur ne trace pas : on trace à sa place
        system, prompt = MentionFinder(live, PROFILE).prompt(window, context)
        live.meter.trace("fake", "m", system, prompt, {}, {}, live.complete(system, prompt, {}))
    first = evaluate_mentions(MentionFinder(live, PROFILE), B1, VALMONT / "gold", context, state).summary()
    replayed = evaluate_mentions(MentionFinder(ReplayAdapter(tmp_path), PROFILE), B1, VALMONT / "gold",
                                 context, state).summary()
    assert (replayed["c1"], replayed["c2"]) == (first["c1"], first["c2"])
    with pytest.raises(ValueError, match="rejeu"):
        ReplayAdapter(tmp_path).complete("autre", "prompt", {})


def test_a_title_held_by_one_entity_is_searched_a_shared_title_is_not():
    """« le baron » (Odon seul) est cherché sans modèle ; « le roi » (Aldren II et Mervin) ne l'est pas."""
    context, state = setup()
    titles = Resolver.from_state(context, state).titles
    window = next(document_window(p) for p in B1 if "notes-baron" in str(p))
    found = [m for m in known_mentions(window, context.entities, titles) if m.rule == "title"]
    assert found and {m.entity for m in found} == {"odon"}
    assert "roi" in titles and len(titles["roi"]) == 2


def test_short_forms_variant_B_finds_first_names_without_a_model():
    """Variante B : « Odon » tiré d'« Odon de Brume » ; « Brume », nom connu d'un lieu, n'est jamais une forme courte."""
    from worldkit.periphery.mentions import short_forms
    context, state = setup()
    window = next(document_window(p) for p in B1 if "notes-baron" in str(p))
    mentions = known_mentions(window, context.entities, Resolver.from_state(context, state).titles)
    extra = short_forms(window, mentions, context.entities, context.schema)
    assert {m.text for m in extra} == {"Odon"} and {m.entity for m in extra} == {"odon"}
    assert len(extra) == 4  # passages 2, 4, 5 et 7


def test_prompt_variant_A_adds_one_rule_with_an_example_outside_the_corpus():
    context, _ = setup()
    plain, variant = (MentionFinder(None, PROFILE, flag) for flag in (False, True))
    system, _ = variant.prompt(document_window(B1[0]), context)
    assert system.startswith(plain.system) and "Marianne" in system and "Odon" not in system
    assert plain.version != variant.version  # deux variantes, deux versions (comparables, jamais mélangées)
