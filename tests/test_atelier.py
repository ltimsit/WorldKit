"""I8 — atelier d'ingestion : magasin d'atelier (T1), lecture par lignée (T2), couches, gestes, « Proposer »."""

from __future__ import annotations

from support import base_world
from worldkit.atelier import store

NOTES = """# Notes sur le baron

Odon de Brume est le baron de Brume.

Le conseil des marchands gouverne Brume dans les faits.
"""


def test_import_creates_a_document_version_kept_whole_Q2():
    world = base_world()
    doc = store.import_source(world, NOTES)
    assert doc.doc_id == "notes-sur-le-baron" and len(doc.passages) == 2
    again = store.source(world, doc.doc_id)
    assert again.fingerprint == doc.fingerprint and [p.text for p in again.passages] == [p.text for p in doc.passages]
    assert store.import_source(world, NOTES).fingerprint == doc.fingerprint  # même texte : rien de plus
    assert store.sources(world) == [(doc.doc_id, doc.fingerprint)]
    rows = world.store.conn.execute("SELECT COUNT(*) FROM passages WHERE doc_id = ?", (doc.doc_id,)).fetchone()[0]
    assert rows == 2  # les passages vont dans la table de l'ingestion : un seul modèle de document


def test_annotations_are_append_only_and_replaced_not_modified_T1():
    world = base_world()
    doc = store.import_source(world, NOTES)
    a = store.add_annotation(world, "reference", doc, "mention", {"entity": "odon"}, "c1", 1, 0, 13)
    b = store.add_annotation(world, "reference", doc, "mention", {"entity": "brume"}, replaces=a, passage=1,
                             start=0, end=13, status="corrected")
    current = store.current(world, "reference", doc)
    assert [x.ann_id for x in current] == [b] and current[0].value == {"entity": "brume"}
    assert [x.ann_id for x in store.history(world, "reference", doc)] == [a, b]  # rien n'est effacé


def test_a_branch_sees_its_ancestors_annotations_up_to_its_start_only_T2():
    world = base_world()
    doc = store.import_source(world, NOTES)
    before = store.add_annotation(world, "reference", doc, "mention", {"entity": "odon"}, passage=1, start=0, end=13)
    world.create_branch("retcon")
    on_branch = store.add_annotation(world, "retcon", doc, "mention", {"entity": "new"}, passage=2, start=3, end=24)
    correction = store.add_annotation(world, "retcon", doc, "mention", {"entity": "brume"}, replaces=before,
                                      passage=1, start=0, end=13, status="corrected")
    assert {a.ann_id for a in store.current(world, "retcon", doc)} == {on_branch, correction}
    assert {a.ann_id for a in store.current(world, "reference", doc)} == {before}  # la parente n'est pas touchée


def test_atelier_rules_follow_the_lineage_Q4():
    world = base_world()
    store.add_rule(world, "reference", "les veilleurs de nuit", "not_entity_of", "veilleurs")
    world.create_branch("retcon")
    store.add_rule(world, "retcon", "vallée", "not_entity")
    assert [r.form for r in store.rules(world, "retcon")] == ["veilleurs de nuit", "vallee"]
    assert [r.form for r in store.rules(world, "reference")] == ["veilleurs de nuit"]


# --- Étape 2 : la couche « mentions » écrit des annotations ; relance ---

from worldkit.atelier import layers  # noqa: E402


class FakeFinder:
    """C1b simulé : rend des mentions fixes (texte, type)."""

    def __init__(self, mentions):
        self.items = mentions
        self.version = "fake"

    def find(self, window, context):
        from worldkit.periphery.mentions import Mention, _occurrences
        out = []
        for text, type_ in self.items:
            for start in _occurrences(window.text, text):
                out.append(Mention(window.text[start:start + len(text)], start, window.passage_at(start), type_,
                                   "model"))
        return out


def mention_values(world, doc):
    return sorted((a.passage, a.value["text"], a.value["entity"]) for a in layers.effective(world, "reference", doc)
                  if a.kind == "mention")


def test_layer_writes_mentions_known_without_model_and_new_with_it():
    world = base_world()
    doc = store.import_source(world, NOTES)
    layers.run_mentions(world, "reference", doc.doc_id)
    assert ("1", "Odon de Brume", "odon") in [(str(p), t, e) for p, t, e in mention_values(world, doc)]
    report = layers.run_mentions(world, "reference", doc.doc_id, FakeFinder([("conseil des marchands", "Faction")]))
    assert report.run == 2 and report.new == 1
    values = mention_values(world, doc)
    assert (2, "conseil des marchands", "new:conseil des marchands") in values
    assert len([v for v in values if v[1] == "Odon de Brume"]) == 1  # le premier lancement n'est plus courant


def test_relaunch_respects_the_author_and_the_atelier_rules_T3():
    world = base_world()
    doc = store.import_source(world, NOTES)
    layers.run_mentions(world, "reference", doc.doc_id, FakeFinder([("conseil des marchands", "Faction")]))
    conseil = next(a for a in layers.effective(world, "reference", doc) if a.value["text"] == "conseil des marchands")
    store.add_annotation(world, "reference", doc, "mention", {**conseil.value, "entity": None}, "author",
                         conseil.passage, conseil.start, conseil.end, status="ignored", replaces=conseil.ann_id)
    store.add_rule(world, "reference", "Brume", "not_entity")  # pour l'essai : « Brume » n'est jamais une entité
    report = layers.run_mentions(world, "reference", doc.doc_id, FakeFinder([("conseil des marchands", "Faction")]))
    assert report.skipped_by_author == 1 and report.skipped_by_rules >= 1
    values = mention_values(world, doc)
    assert (2, "conseil des marchands", None) in values  # la décision de l'auteur reste, la couche ne la refait pas
    assert not any(t == "Brume" for _, t, _ in values)


# --- Étape 3 : gestes et portées (Q4) ---

from worldkit.atelier import gestures  # noqa: E402

ROI = """# Lieux

Le Roi Gris régnait autrefois depuis Hautval.

On chante encore le Roi Gris dans les tavernes de Brume.
"""


def test_correcting_one_occurrence_corrects_the_whole_source_by_default_Q4():
    world = base_world()
    doc = store.import_source(world, ROI)
    layers.run_mentions(world, "reference", doc.doc_id, FakeFinder([("Roi Gris", "Character")]))
    first = next(a for a in layers.effective(world, "reference", doc) if a.value["text"] == "Roi Gris")
    written = gestures.gesture(world, "reference", doc.doc_id, "correct", ann_id=first.ann_id, entity="aldren-ii")
    assert len(written) == 2  # les deux occurrences
    assert {e for _, t, e in mention_values(world, doc) if t == "Roi Gris"} == {"aldren-ii"}


def test_an_occurrence_scope_touches_only_that_annotation_Q4():
    world = base_world()
    doc = store.import_source(world, ROI)
    layers.run_mentions(world, "reference", doc.doc_id, FakeFinder([("Roi Gris", "Character")]))
    first = next(a for a in layers.effective(world, "reference", doc) if a.value["text"] == "Roi Gris")
    gestures.gesture(world, "reference", doc.doc_id, "correct", "occurrence", first.ann_id, entity="aldren-ii")
    assert sorted(e or "" for _, t, e in mention_values(world, doc) if t == "Roi Gris") == ["aldren-ii", "new:roi gris"]


def test_a_negative_world_gesture_becomes_an_atelier_rule_for_future_sources_Q4():
    """« les veilleurs de nuit ne sont pas les Veilleurs », retenu : la source suivante ne les rattache plus."""
    world = base_world()
    one = store.import_source(world, "# Une\n\nLes veilleurs de nuit de Hautval allument des feux.\n")
    layers.run_mentions(world, "reference", one.doc_id)
    wrong = next(a for a in layers.effective(world, "reference", one) if a.value["entity"] == "veilleurs")
    gestures.gesture(world, "reference", one.doc_id, "ignore", "world", wrong.ann_id)
    two = store.import_source(world, "# Deux\n\nLes veilleurs de nuit dorment le jour.\n")
    layers.run_mentions(world, "reference", two.doc_id)
    assert not any(e == "veilleurs" for _, _, e in mention_values(world, two))


def test_adding_a_mention_by_selection_covers_its_other_occurrences_Q4():
    world = base_world()
    doc = store.import_source(world, NOTES.replace("Brume dans les faits.", "Brume. Le conseil des marchands siège à Hautval."))
    passage = next(p for p in doc.passages if "conseil" in p.text)
    start = passage.text.index("conseil des marchands")
    written = gestures.gesture(world, "reference", doc.doc_id, "add", passage=passage.index, start=start,
                               end=start + len("conseil des marchands"), entity="new", type_="Faction")
    assert len(written) == 2
    added = [a for a in layers.effective(world, "reference", doc) if a.by_author]
    assert all(a.value["new"] and a.status == "kept" for a in added)


# --- Étape 4 : « Proposer » (Q3, T5) ---

from worldkit.atelier import propose as proposing  # noqa: E402


def test_propose_sends_confirmed_new_entities_and_retained_aliases_only_Q3():
    world = base_world()
    doc = store.import_source(world, NOTES + "\nLe Roi Gris régnait autrefois.\n")
    layers.run_mentions(world, "reference", doc.doc_id,
                        FakeFinder([("conseil des marchands", "Faction"), ("Roi Gris", "Character")]))
    current = {a.value["text"]: a for a in layers.effective(world, "reference", doc)}
    gestures.gesture(world, "reference", doc.doc_id, "keep", ann_id=current["conseil des marchands"].ann_id)
    gestures.gesture(world, "reference", doc.doc_id, "correct", "world", current["Roi Gris"].ann_id, entity="aldren-ii")
    by_passage = proposing.drafts_of(world, "reference", doc)
    flat = [d for ds in by_passage.values() for d in ds]
    assert {"op": "create_entity", "entity": "new:conseil-des-marchands", "type": "Faction"} in flat
    assert {"op": "add_value", "entity": "aldren-ii", "attribute": "aliases", "value": "Roi Gris"} in flat
    report = proposing.propose(world, "reference", doc.doc_id)
    assert report.proposals and report.batch_id.startswith("atelier-")
    from worldkit.ingest.queue import load
    pending = load(world)
    changes = [c.change.op for p in pending for c in p.changes]
    assert "create_entity" in changes and "add_value" in changes  # dans la file de revue, comme un lot ordinaire


def test_nothing_is_proposed_without_an_author_decision_Q3():
    import pytest
    from worldkit.ingest.batch import BatchError
    world = base_world()
    doc = store.import_source(world, NOTES)
    layers.run_mentions(world, "reference", doc.doc_id, FakeFinder([("conseil des marchands", "Faction")]))
    with pytest.raises(BatchError, match="rien à proposer"):
        proposing.propose(world, "reference", doc.doc_id)
