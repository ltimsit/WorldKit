"""J9 — les notes (descriptions), noyau et vues (R-NTE-01 à R-NTE-07, R-NOT-02, R-VUE-02). Tests T1, sans modèle."""

from __future__ import annotations

import json

from support import base_world, edit
from worldkit.core.projection.serialize import state_to_json
from worldkit.core.views import Filter, View, export_json, render_page


def note(nid="n1", subjects=("odon",), **extra):
    return {"op": "add_note", "note": nid, "subjects": list(subjects), "facet": "appearance",
            "text": "un homme massif aux mains baguées", **extra}


def test_a_note_is_a_world_element_with_its_source_and_voice_R_NTE_01():
    w = base_world()
    out = w.apply(edit(note(mentions=["brume"], short=[{"aspect": "corpulence", "value": "massif"}],
                            speaker="chronique-de-la-chute", document="chronique"), id="en1"))
    assert out.ok, [str(i) for i in out.issues]
    n = w.state().notes["n1"]
    assert n["subjects"] == ["odon"] and n["mentions"] == ["brume"] and n["facet"] == "appearance"
    assert n["short"] == [["corpulence", "massif"]] and n["speaker"] == "chronique-de-la-chute"
    assert n["document"] == "chronique" and n["established_by"] == "en1"


def test_a_note_writes_no_fact_key_and_two_notes_may_diverge_R_NTE_02():
    w = base_world()
    before = dict(w.state().occupancy)
    assert w.apply(edit(note("n1", short=[{"aspect": "cheveux", "value": "roux"}]), id="en1")).ok
    assert w.apply(edit(note("n2", short=[{"aspect": "cheveux", "value": "bruns"}]), id="en2")).ok  # aucune collision
    assert w.state().occupancy == before


def test_subjects_have_no_order_R_NTE_01_R_PRI_03():
    a, b = base_world(), base_world()
    assert a.apply(edit(note(subjects=["odon", "mervin"], facet="character"), id="e")).ok
    assert b.apply(edit(note(subjects=["mervin", "odon"], facet="character"), id="e")).ok
    assert state_to_json(a.state()) == state_to_json(b.state())


def test_visibility_is_declared_changed_and_capped_by_subjects_mentions_and_speaker_R_NTE_03():
    """Une note publique qui nomme le Cercle des Cendres (secret) n'est pas montrée aux joueurs (R-NOT-04)."""
    w = base_world()
    assert w.apply(edit(note("pub", visibility="public"), id="e1")).ok
    assert w.apply(edit(note("cap", mentions=["cercle-des-cendres"], visibility="public"), id="e2")).ok
    assert w.apply(edit(note("voix", speaker="cercle-des-cendres", visibility="public"), id="e3")).ok
    assert w.apply(edit({"op": "set_visibility", "target": {"note": "pub"}, "value": "secret"}, id="e4")).ok
    assert w.state().notes["pub"]["visibility"] == "secret"
    assert w.apply(edit({"op": "set_visibility", "target": {"note": "pub"}, "value": "public"}, id="e5")).ok
    state = w.state()
    assert [n.note for n in View(state, Filter.PLAYER).page("odon").notes] == ["pub"]
    assert {n.note for n in View(state, Filter.AUTHOR).page("odon").notes} == {"pub", "cap", "voix"}
    assert len(json.loads(export_json(state, Filter.PLAYER))["notes"]) == 1
    assert len(json.loads(export_json(state, Filter.AUTHOR))["notes"]) == 3


def test_a_facet_must_be_declared_for_every_subject_or_other_R_NTE_04():
    w = base_world()
    refused = w.apply(edit(note("n1", facet="atmosphere"), id="e1"))  # une facette de lieu, pas de personnage
    assert not refused.ok and refused.issues[0].rule == "R-NTE-04"
    assert w.apply(edit(note("n2", subjects=["odon", "brume"], facet="other"), id="e2")).ok
    assert not w.apply(edit(note("n3", subjects=["odon", "brume"], facet="appearance"), id="e3")).ok or \
        "appearance" in w.state().world.facets_of("Place")  # commune aux deux types, sinon refusée


def test_cited_entities_must_exist_and_are_read_T_ING_02():
    w = base_world()
    assert not w.apply(edit(note(subjects=["personne"]), id="e1")).ok
    assert not w.apply(edit(note(mentions=["personne"]), id="e2")).ok
    out = w.apply(edit(note(mentions=["brume"]), id="e3"))
    assert ("entity", "brume") in w.store.edit("e3").reads and ("entity", "odon") in w.store.edit("e3").reads
    assert out.ok


def test_remove_and_correct_keep_the_history_R_NTE_07_R_HIS_01():
    w = base_world()
    assert w.apply(edit(note("n1"), id="e1")).ok
    point = w.set_point("@avec-n1")
    assert not w.apply(edit(note("n1"), id="e2")).ok  # identifiant déjà pris
    fix = w.apply(edit({"op": "remove_note", "note": "n1"}, {**note("n1"), "text": "un homme massif"}, id="e3"))
    assert fix.ok and w.state().notes["n1"]["text"] == "un homme massif"  # corriger : retirer et poser
    assert w.apply(edit({"op": "remove_note", "note": "n1"}, id="e4")).ok and "n1" not in w.state().notes
    assert w.state(point=point).notes["n1"]["text"] == "un homme massif aux mains baguées"
    assert not w.apply(edit({"op": "remove_note", "note": "n1"}, id="e5")).ok


def test_a_note_lives_on_its_branch_and_transposes_R_MON_04():
    w = base_world()
    w.create_branch("variante")
    assert w.apply(edit(note("n1"), id="e1", branch="variante")).ok
    assert "n1" in w.state("variante").notes and "n1" not in w.state().notes
    outcome, _ = w.transpose("e1", w.reference_branch)
    assert outcome.ok and "n1" in w.state().notes


def test_the_page_shows_notes_by_facet_and_where_an_entity_is_mentioned_R_VUE_02():
    w = base_world()
    assert w.apply(edit(note("n1", mentions=["brume"], short=[{"aspect": "corpulence", "value": "massif"}]),
                        note("n2", subjects=["odon", "mervin"], facet="character", text="se disputent à chaque fête"),
                        id="e1")).ok
    state = w.state()
    view = View(state, Filter.AUTHOR)
    md = render_page(view.page("odon"), view)
    assert "### apparence (appearance)" in md and "« un homme massif aux mains baguées » — corpulence : massif" in md
    assert "« se disputent à chaque fête » · avec Mervin" in md
    brume = render_page(view.page("brume"), view)
    assert "## Mentions dans les notes" in brume and "· sur Odon de Brume" in brume
    assert [n.note for n in view.page("mervin").notes] == ["n2"]  # deux sujets : la note est sur les deux pages


# --- Ingestion (étape 4) : propositions, supports, orphelines, documents en jeu ---

from worldkit.atelier.propose import AtelierExtractor  # noqa: E402
from worldkit.ingest import decide  # noqa: E402
from worldkit.ingest.batch import ingest  # noqa: E402
from worldkit.ingest.queue import load  # noqa: E402

PORTRAIT = "Odon de Brume est un homme massif aux mains baguées."
DRAFT = {"op": "add_note", "subjects": ["odon"], "facet": "appearance", "text": "un homme massif aux mains baguées",
         "short": [{"aspect": "corpulence", "value": "massif"}]}


def write(tmp_path, name, body, header="mode: source\nnature: diegetic\nvoice: author\nvisibility: public"):
    path = tmp_path / f"{name}.md"
    path.write_text(f"---\nid: {name}\n{header}\n---\n# {name}\n\n{body}\n", encoding="utf-8")
    return path


def test_a_note_is_proposed_accepted_and_attached_to_its_source_R_NTE_06(tmp_path):
    w = base_world()
    ingest(w, "n1", [write(tmp_path, "portrait", PORTRAIT)], AtelierExtractor({PORTRAIT: [DRAFT]}))
    [p] = load(w)
    assert p.changes[0].change.op == "add_note" and "enrichment" in p.changes[0].tags
    assert decide.accept(w, p.id).ok
    [(nid, n)] = w.state().notes.items()
    assert n["document"] == "portrait" and n["visibility"] == "public"  # notoriété de l'en-tête (R-NTE-03)
    assert nid.startswith("portrait.p1.n-")
    from worldkit.ingest.review import orphan_facts
    assert orphan_facts(w) == []


def test_the_same_note_reingested_is_a_support_not_a_new_proposal_R_NTE_06(tmp_path):
    w = base_world()
    ingest(w, "n1", [write(tmp_path, "portrait", PORTRAIT)], AtelierExtractor({PORTRAIT: [DRAFT]}))
    assert decide.accept(w, load(w)[0].id).ok
    ingest(w, "n2", [write(tmp_path, "autre", PORTRAIT)], AtelierExtractor({PORTRAIT: [DRAFT]}))
    assert load(w) == [] and len(w.state().notes) == 1  # même sujet, même facette, même texte : un support


def test_a_note_whose_passage_disappears_is_flagged_orphan_never_removed_R_NTE_06(tmp_path):
    from worldkit.core.schema import IssueCode
    from worldkit.ingest.review import orphan_facts
    w = base_world()
    path = write(tmp_path, "portrait", PORTRAIT)
    ingest(w, "n1", [path], AtelierExtractor({PORTRAIT: [DRAFT]}))
    assert decide.accept(w, load(w)[0].id).ok
    write(tmp_path, "portrait", "Odon de Brume gouverne Brume.")
    ingest(w, "n2", [path], AtelierExtractor({}))
    issues = orphan_facts(w)
    assert [i.code for i in issues] == [IssueCode.ORPHAN_NOTE] and len(w.state().notes) == 1


def test_an_in_world_document_gives_attributed_notes_R_NTE_01(tmp_path):
    """La Chronique décrit Aldren : une note attribuée, alors qu'un fait n'y est jamais extrait (R-DOC-06)."""
    w = base_world()
    text = "Aldren était un roi pieux et juste."
    header = "mode: source\nnature: diegetic\nvoice: in_world\nspeaker: chronique-de-la-chute\nvisibility: public"
    note_draft = {"op": "add_note", "subjects": ["aldren-ii"], "facet": "character", "text": "un roi pieux et juste"}
    fact_draft = {"op": "set_attribute", "entity": "aldren-ii", "attribute": "title", "value": "pieux"}
    ingest(w, "n1", [write(tmp_path, "chronique", text, header)], AtelierExtractor({text: [note_draft, fact_draft]}))
    ops = [c.change.op for p in load(w) for c in p.changes]
    assert ops == ["add_note"]
    assert decide.accept(w, load(w)[0].id).ok
    [n] = w.state().notes.values()
    assert n["speaker"] == "chronique-de-la-chute"


# --- Couche « descriptions » (étape 5), modèle simulé ---

from worldkit.periphery.facts import Confirmed  # noqa: E402
from worldkit.periphery.mentions import window_of  # noqa: E402
from worldkit.periphery.notes import NoteFinder  # noqa: E402


class FakeAdapter:
    def __init__(self, notes):
        self.notes, self.calls = notes, []

    def complete(self, system, user, schema):
        self.calls.append(user)
        return {"notes": self.notes}


class Profile:
    signature = "fake"


def test_the_descriptions_layer_checks_what_the_model_returns_R_NTE_01_R_NTE_04_R_NTE_05():
    from worldkit.ingest.declaration import parse_document
    text = ("---\nid: notes\nmode: source\nnature: diegetic\nvoice: author\n---\n# Notes\n\n"
            "Odon, un homme massif aux mains baguées, est le baron de Brume.\n\n"
            "On dit que le baron est un traître.\n")
    doc = parse_document(text, "notes.md")
    window = window_of(doc)
    entities = [Confirmed("odon", "Character", "Odon de Brume"), Confirmed("brume", "Place", "Brume")]
    schema = base_world().state().world
    adapter = FakeAdapter([
        {"subjects": ["odon"], "mentions": ["brume", "odon"], "facet": "appearance", "text": "un homme massif aux mains baguées",
         "short": [{"aspect": "corpulence", "value": "massif"}, {"aspect": "", "value": "x"}]},
        {"subjects": ["odon"], "mentions": [], "facet": "atmosphere", "text": "un homme massif aux mains baguées", "short": []},
        {"subjects": ["odon"], "mentions": [], "facet": "character", "text": "un traître", "short": []},
        {"subjects": ["odon"], "mentions": [], "facet": "character", "text": "un homme inventé", "short": []},
        {"subjects": ["personne"], "mentions": [], "facet": "other", "text": "le baron de Brume", "short": []},
        {"subjects": ["odon"], "mentions": [], "facet": "other", "text": "baron", "short": []},
    ])
    finder = NoteFinder(adapter, Profile())
    found = finder.find(window, entities, schema, ["odon — titre : baron"], {"odon": {"baron"}})
    drafts = [n.draft for n in found]
    assert drafts[0] == {"op": "add_note", "subjects": ["odon"], "facet": "appearance", "mentions": ["brume"],
                         "text": "un homme massif aux mains baguées",
                         "short": [{"aspect": "corpulence", "value": "massif"}]}
    assert drafts[1]["facet"] == "other" and len(drafts) == 2  # facette de lieu pour un personnage : « autre »
    reasons = sorted(r for _, r in finder.rejected)
    assert reasons == ["aucun sujet parmi les entités confirmées", "citation introuvable dans le texte",
                       "déjà dit par un fait gardé", "rumeur ou paroles rapportées"]
    assert "facettes : appearance (apparence)" in adapter.calls[0] and "odon — titre : baron" in adapter.calls[0]


# --- Atelier (étape 6) : couche, gestes, « Proposer » ---

import pytest  # noqa: E402

from worldkit.atelier import gestures, layers, store  # noqa: E402
from worldkit.atelier import propose as proposing  # noqa: E402

SOURCE = """# Le baron

Odon de Brume, un homme massif aux mains baguées, gouverne Brume.

Odon de Brume ne sort jamais sans sa canne d'ébène.
"""
FOUND = [{"subjects": ["odon"], "mentions": [], "facet": "appearance", "text": "un homme massif aux mains baguées",
          "short": [{"aspect": "corpulence", "value": "massif"}]},
         {"subjects": ["odon"], "mentions": [], "facet": "habits", "text": "ne sort jamais sans sa canne d'ébène",
          "short": []}]


def atelier_source():
    w = base_world()
    doc = store.import_source(w, SOURCE)
    layers.run_mentions(w, "reference", doc.doc_id)
    return w, doc


def notes_of(w, doc):
    return [a for a in layers.effective(w, "reference", doc) if a.kind == "note"]


def test_the_layer_writes_one_annotation_per_note_and_respects_the_author_on_relaunch():
    w, doc = atelier_source()
    report = layers.run_notes(w, "reference", doc.doc_id, NoteFinder(FakeAdapter(FOUND), Profile()))
    assert report.proposed == 2 and report.entities >= 1
    first = next(a for a in notes_of(w, doc) if a.value["draft"]["facet"] == "habits")
    assert first.passage == 2 and first.start is not None
    gestures.note_gesture(w, "reference", doc.doc_id, "correct", first.ann_id, draft={"facet": "character"})
    again = layers.run_notes(w, "reference", doc.doc_id, NoteFinder(FakeAdapter(FOUND), Profile()))
    assert again.skipped_by_author == 1 and again.proposed == 1
    facets = sorted(a.value["draft"]["facet"] for a in notes_of(w, doc))
    assert facets == ["appearance", "character"]


def test_note_gestures_check_the_citation_subjects_and_facet_R_NTE_04():
    w, doc = atelier_source()
    layers.run_notes(w, "reference", doc.doc_id, NoteFinder(FakeAdapter(FOUND), Profile()))
    note = notes_of(w, doc)[0]
    with pytest.raises(ValueError, match="impossible pour ces sujets"):
        gestures.note_gesture(w, "reference", doc.doc_id, "correct", note.ann_id, draft={"facet": "atmosphere"})
    with pytest.raises(ValueError, match="recopiée du passage"):
        gestures.note_gesture(w, "reference", doc.doc_id, "add", passage=1,
                              draft={"subjects": ["odon"], "facet": "character", "text": "un homme inventé"})
    added = gestures.note_gesture(w, "reference", doc.doc_id, "add", passage=1,
                                  draft={"subjects": ["odon"], "facet": "character", "text": "gouverne Brume",
                                         "mentions": ["brume"]})
    assert added and any(a.value["draft"]["text"] == "gouverne Brume" for a in notes_of(w, doc))
    gestures.note_gesture(w, "reference", doc.doc_id, "remove", note.ann_id)
    assert all(a.ann_id != note.ann_id or a.status == "removed" for a in notes_of(w, doc))


def test_propose_sends_notes_with_the_facts_then_in_their_own_lot():
    from worldkit.ingest.batch import BatchError
    from worldkit.ingest.queue import load
    w, doc = atelier_source()
    # Pas d'entité nouvelle : « Proposer » envoie les notes dans le premier lot.
    layers.run_notes(w, "reference", doc.doc_id, NoteFinder(FakeAdapter(FOUND), Profile()))
    proposing.propose(w, "reference", doc.doc_id)
    ops = sorted(c.change.op for p in load(w) for c in p.changes)
    assert ops == ["add_note", "add_note"]
    for p in load(w):
        assert decide.accept(w, p.id).ok
    assert len(w.state().notes) == 2
    with pytest.raises(BatchError, match="aucun fait ni aucune note"):
        proposing.propose(w, "reference", doc.doc_id)  # les notes déjà parties ne repartent pas
    # Une bribe ajoutée ensuite part seule, au « Proposer » suivant.
    gestures.note_gesture(w, "reference", doc.doc_id, "add", passage=1,
                          draft={"subjects": ["odon"], "facet": "character", "text": "gouverne Brume"})
    proposing.propose(w, "reference", doc.doc_id)
    assert [c.change.text for p in load(w) for c in p.changes] == ["gouverne Brume"]


def test_the_atelier_screen_runs_shows_corrects_and_adds_notes(tmp_path):
    """Écran (étape 7) : la couche se lance (estimation, confirmation), les bribes s'affichent sous leur passage,
    le panneau corrige la facette, l'ajout passe par la sélection."""
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    from test_service import make_world
    from worldkit.core.world import World
    from worldkit.web import create_app
    db = make_world(tmp_path / "valmont.db")
    w = World.open(db)
    doc = store.import_source(w, SOURCE)
    layers.run_mentions(w, "reference", doc.doc_id)
    layers.run_notes(w, "reference", doc.doc_id, NoteFinder(FakeAdapter(FOUND), Profile()))
    note = next(a for a in notes_of(w, doc) if a.value["draft"]["facet"] == "habits")
    w.close()
    client = TestClient(create_app(db))
    page = client.get(f"/atelier/{doc.doc_id}").text
    assert "Couche « descriptions »" in page and "« ne sort jamais sans sa canne d&#39;ébène »" in page
    panel = client.get(f"/atelier/{doc.doc_id}?note={note.ann_id}").text
    assert 'name="facet"' in panel and "Partira avec « Proposer »." in panel
    done = client.post(f"/atelier/{doc.doc_id}/annotate", data={"kind": "note", "action": "correct", "ann_id": note.ann_id,
                                                                "facet": "character", "subjects": "odon", "short": ""},
                       follow_redirects=False)
    assert done.status_code == 303
    added = client.post(f"/atelier/{doc.doc_id}/annotate", data={"kind": "note", "action": "add", "passage": 1,
                                                                 "text": "gouverne Brume", "facet": "character",
                                                                 "subjects": "odon", "short": "rôle : souverain"},
                        follow_redirects=False)
    assert added.status_code == 303
    page = client.get(f"/atelier/{doc.doc_id}").text
    assert "corrigée" in page and "rôle : souverain" in page


def test_a_note_within_a_kept_fact_evidence_is_set_aside_unless_it_says_more_R_NTE_05():
    """« elle deteste les bateliers » : déjà dit par « Ysolde — déteste — la Guilde » (même passage, mêmes entités) ;
    « … avant la grande crue … » nomme une entité de plus : elle dit plus que le fait, elle reste (cas réel, X-017)."""
    from worldkit.ingest.declaration import parse_document
    from worldkit.periphery.notes import check_notes
    text = ("---\nid: n\nmode: source\nnature: diegetic\nvoice: author\n---\n# N\n\n"
            "Odon de Brume déteste Mervin, et le hait depuis la Chute.\n")
    window = window_of(parse_document(text, "n.md"))
    entities = [Confirmed("odon", "Character", "Odon de Brume"), Confirmed("mervin", "Character", "Mervin"),
                Confirmed("la-chute", "Event", "la Chute")]
    evidence = [(1, "Odon de Brume déteste Mervin, et le hait depuis la Chute.", {"odon", "mervin"})]
    raw = [{"subjects": ["odon"], "mentions": ["mervin"], "facet": "character", "text": "déteste Mervin", "short": []},
           {"subjects": ["odon"], "mentions": ["mervin", "la-chute"], "facet": "history",
            "text": "le hait depuis la Chute", "short": []}]
    rejected = []
    kept = check_notes(raw, window, entities, base_world().state().world, {}, rejected, evidence)
    assert [n.draft["text"] for n in kept] == ["le hait depuis la Chute"]
    assert [why for _, why in rejected] == ["déjà dit par un fait gardé"]


def test_a_relaunch_does_not_repropose_a_citation_the_author_decided_even_reworded():
    """Cas réel : la bribe gardée revenait, la nouvelle passe ayant formulé autrement sa forme courte
    (« activité antérieure » / « activité passée »). Une citation décidée (gardée, corrigée, retirée) ne revient pas."""
    w, doc = atelier_source()
    layers.run_notes(w, "reference", doc.doc_id, NoteFinder(FakeAdapter(FOUND), Profile()))
    first, second = sorted(notes_of(w, doc), key=lambda a: a.passage)
    gestures.note_gesture(w, "reference", doc.doc_id, "keep", first.ann_id)
    gestures.note_gesture(w, "reference", doc.doc_id, "remove", second.ann_id)
    reworded = [{**FOUND[0], "short": [{"aspect": "carrure", "value": "massive"}]},
                {**FOUND[1], "facet": "character"}]
    report = layers.run_notes(w, "reference", doc.doc_id, NoteFinder(FakeAdapter(reworded), Profile()))
    assert report.skipped_by_author == 2 and report.proposed == 0
    assert sorted(a.status for a in notes_of(w, doc)) == ["kept", "removed"]


def test_deciding_every_proposal_of_the_last_run_does_not_bring_back_an_older_run_I_ATL_02():
    """Cas réel (X-018) : après une relance, l'auteur garde toutes les bribes de la passe 2 ; celles de la passe 1
    réapparaissaient (la dernière passe était lue dans les seules annotations courantes)."""
    w, doc = atelier_source()
    layers.run_notes(w, "reference", doc.doc_id, NoteFinder(FakeAdapter(FOUND), Profile()))
    second = [{**FOUND[0], "text": "un homme massif"}]
    report = layers.run_notes(w, "reference", doc.doc_id, NoteFinder(FakeAdapter(second), Profile()))
    assert report.run == 2
    [only] = notes_of(w, doc)
    gestures.note_gesture(w, "reference", doc.doc_id, "keep", only.ann_id)
    assert [a.value["draft"]["text"] for a in notes_of(w, doc)] == ["un homme massif"]  # la passe 1 ne revient pas
    assert layers.run_notes(w, "reference", doc.doc_id, NoteFinder(FakeAdapter([]), Profile())).run == 3
