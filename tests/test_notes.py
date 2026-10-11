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
