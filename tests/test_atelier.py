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
