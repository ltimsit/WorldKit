"""Ce que disent les documents : passages qui nomment une entité sur sa page d'auteur (R-VUE-05, T-ING-21).

Niveau 1 du chantier « ingérer plus que les faits » (§10.6) : sans modèle, sans écriture au journal.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from support import ROOT, base_world, create, edit, rel
from test_corpus_corbelle import corbelle_world, documents as corbelle_documents
from test_w10_w11 import after_w05
from worldkit.atelier import store as atelier
from worldkit.atelier.propose import AtelierExtractor
from worldkit.core.views import Filter, PassageLine, PassageStatus, View, render_page
from worldkit.ingest.batch import batch_documents, ingest
from worldkit.ingest.passages import passages_by_entity

PIEGES = ROOT / "corpus" / "pieges-v1" / "docs" / "batches.yaml"
NOTHING = AtelierExtractor({})  # aucun fait : seuls les passages comptent


def lines(world, entity, state=None):
    return passages_by_entity(world, state or world.state()).get(entity, [])


def at(lines_, doc, passage):
    return next(line for line in lines_ if (line.document, line.passage) == (doc, passage))


def forms(line):
    return sorted((line.text[s:e], check) for s, e, check in line.spans)


@pytest.fixture(scope="module")
def valmont():
    w = after_w05()
    yield w
    w.close()


def pieges_world():
    w = base_world()
    ingest(w, "p1", batch_documents(PIEGES, "p1"), NOTHING)
    return w


# --- Liens et repères ---

def test_a_passage_that_supports_a_fact_is_captured_and_lists_the_facts(valmont):
    line = at(lines(valmont, "odon"), "notes-baron", 1)
    assert line.status is PassageStatus.CAPTURED and "rules(odon, brume)" in line.facts
    assert forms(line) == [("Odon de Brume", False), ("le baron", False)]  # titre porté par Odon seul


def test_a_passage_that_names_the_entity_without_a_fact_is_uncaptured(valmont):
    """« Le baron est un traître », murmure-t-on : nommé (« le baron », titre porté par Odon seul), rien n'en sort."""
    line = at(lines(valmont, "odon"), "notes-baron", 6)
    assert line.status is PassageStatus.UNCAPTURED and line.facts == ()


def test_an_in_world_document_gives_claims_not_facts_R_DOC_06():
    w = after_w05()
    ingest(w, "b2", batch_documents(ROOT / "corpus" / "valmont-v1" / "valmont" / "docs" / "batches.yaml", "b2"),
           NOTHING)
    chronique = [line for line in lines(w, "loup-de-cendre") if line.document == "chronique-de-la-chute-extraits"]
    assert chronique and all(line.status is PassageStatus.CLAIM for line in chronique)


def test_lowercase_forms_are_linked_but_to_check_X_012():
    """Notes brouillon : « corbelle », « la sorgue » restent liées (rien n'est perdu), signalées à vérifier."""
    w = corbelle_world()
    ingest(w, "c1", corbelle_documents(), NOTHING)
    line = at(lines(w, "corbelle"), "brouillon-corbelle", 1)
    assert forms(line) == [("corbelle", True)] and line.to_check
    assert at(lines(w, "jehan-marcastel"), "persos", 1).to_check is False  # « Jehan Marcastel », tel quel


def test_homographs_are_flagged_per_span_not_hidden_AX_R11():
    """« Une brume épaisse … les quais de Brume » : le passage nomme bien Brume, « brume » est à vérifier."""
    w = pieges_world()
    line = at(lines(w, "brume"), "homographes", 1)
    assert forms(line) == [("Brume", False), ("brume", True)] and not line.to_check
    assert at(lines(w, "veilleurs"), "homographes", 3).to_check
    assert at(lines(w, "la-chute"), "homographes", 2).to_check
    assert at(lines(w, "la-chute"), "homographes", 6).to_check is False  # « la Chute »


# --- L'atelier corrige les liens ---

def ann(world, doc_id, passage, text, status, entity=None):
    vfp = world.store.conn.execute("SELECT version_fp FROM batch_documents WHERE doc_id = ?", (doc_id,)).fetchone()[0]
    ptext = world.store.conn.execute("SELECT text FROM passages WHERE doc_id = ? AND idx = ?",
                                     (doc_id, passage)).fetchone()[0]
    start = ptext.index(text)
    ref = SimpleNamespace(doc_id=doc_id, fingerprint=vfp)
    atelier.add_annotation(world, world.reference_branch, ref, "mention", {"text": text, "entity": entity}, "author",
                           passage, start, start + len(text), "sure", status)


def test_an_author_decision_overrides_the_known_name_search():
    w = pieges_world()
    ann(w, "homographes", 3, "Les veilleurs", "ignored")       # ce ne sont pas les Veilleurs
    ann(w, "homographes", 2, "chute", "kept", "la-chute")       # pour l'essai : l'auteur garde
    ann(w, "homographes", 1, "brume", "corrected", "hautval")   # pour l'essai : rattachée ailleurs
    assert not any(line.passage == 3 for line in lines(w, "veilleurs"))
    assert at(lines(w, "la-chute"), "homographes", 2).to_check is False
    assert forms(at(lines(w, "brume"), "homographes", 1)) == [("Brume", False)]
    assert ("brume", False) in forms(at(lines(w, "hautval"), "homographes", 1))


def test_atelier_rules_of_the_branch_apply_Q4():
    w = pieges_world()
    atelier.add_rule(w, "reference", "les veilleurs", "not_entity_of", "veilleurs")
    assert not any(line.passage == 3 for line in lines(w, "veilleurs"))
    assert at(lines(w, "la-chute"), "homographes", 2)
    atelier.add_rule(w, "reference", "chute", "not_entity")  # forme pliée, sans article : « la Chute » aussi
    assert lines(w, "la-chute") == []


# --- Documents pris en compte ---

def test_only_batches_of_the_lineage_count_R_HIS_02():
    w = base_world()
    w.create_branch("variante")
    w.apply(edit(*create("phare", "Place", "le Phare", "public")))  # la référence avance après la divergence
    ingest(w, "p1", batch_documents(PIEGES, "p1"), NOTHING)
    assert lines(w, "brume") and passages_by_entity(w, w.state("variante")) == {}


def test_an_obsolete_document_stays_marked_R_DOC_05_R_PRI_01(valmont):
    w = after_w05()
    w.apply(edit({"op": "set_document_obsolete", "document": "notes-baron", "value": True}, origin="curation"))
    line = at(lines(w, "odon"), "notes-baron", 1)
    assert line.obsolete and not at(lines(w, "brume"), "lieux-de-valmont", 1).obsolete


def test_document_order_changes_nothing_R_PRI_03():
    one, two = corbelle_world(), corbelle_world()
    ingest(one, "c1", corbelle_documents(), NOTHING)
    ingest(two, "c1", list(reversed(corbelle_documents())), NOTHING)
    assert passages_by_entity(one, one.state()) == passages_by_entity(two, two.state())


def test_same_input_same_output_and_nothing_written(valmont):
    before = valmont.store.conn.total_changes
    assert passages_by_entity(valmont, valmont.state()) == passages_by_entity(valmont, valmont.state())
    assert valmont.store.conn.total_changes == before


# --- La page ---

def test_the_section_is_for_the_author_only_R_VUE_05(valmont):
    from worldkit.ingest.review import sources
    state = valmont.state()
    passages = passages_by_entity(valmont, state)
    author = View(state, Filter.AUTHOR, sources(valmont), passages=passages)
    player = View(state, Filter.PLAYER, sources(valmont), passages=passages)  # même si on les lui donne
    assert author.page("odon").passages and player.page("odon").passages == []
    md = render_page(author.page("odon"), author)
    assert "## Ce que disent les documents" in md and "notes-baron §1 — capté : " in md and "**Odon de Brume**" in md
    assert "Ce que disent les documents" not in render_page(player.page("odon"), player)


def test_a_consolidated_page_merges_its_members_passages_R_IDT_04():
    w = base_world()
    w.apply(edit(*create("roi-gris", "Character", "le Roi Gris", "public")))
    w.apply(edit(rel("roi-gris", "same_as", "aldren-ii", kind="duplicate", visibility="public"), origin="correction"))
    text = "Le Roi Gris, c'est Aldren."
    passages = {"roi-gris": [PassageLine("roi-gris", "notes", 1, text, ((0, 11, False),), PassageStatus.UNCAPTURED)],
                "aldren-ii": [PassageLine("aldren-ii", "notes", 1, text, ((19, 25, True),), PassageStatus.CAPTURED,
                                          ("aldren-ii.title",))]}
    page = View(w.state(), Filter.AUTHOR, passages=passages).page("roi-gris")
    assert len(page.passages) == 1
    line = page.passages[0]
    assert line.status is PassageStatus.CAPTURED and line.spans == ((0, 11, False), (19, 25, True))
    assert line.facts == ("aldren-ii.title",) and not line.to_check


def test_the_wiki_command_shows_the_section(tmp_path, capsys):
    from worldkit.cli import main
    from test_service import make_world
    db = make_world(tmp_path / "valmont.db")
    w = __import__("worldkit.core.world", fromlist=["World"]).World.open(db)
    ingest(w, "p1", batch_documents(PIEGES, "p1"), NOTHING)
    w.close()
    assert main(["--db", str(db), "wiki", "page", "brume"]) == 0
    out = capsys.readouterr().out
    assert "homographes §1 — non capté — à vérifier : « brume »" in out
    assert main(["--db", str(db), "wiki", "page", "brume", "--filter", "player"]) == 0
    assert "Ce que disent les documents" not in capsys.readouterr().out


def test_the_wiki_screen_highlights_the_spans_I_VUE_07(tmp_path):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    from test_service import make_world
    from worldkit.core.world import World
    from worldkit.web.app import create_app
    db = make_world(tmp_path / "valmont.db")
    w = World.open(db)
    ingest(w, "p1", batch_documents(PIEGES, "p1"), NOTHING)
    w.close()
    client = TestClient(create_app(db))
    author = client.get("/wiki/brume").text
    assert "Ce que disent les documents" in author
    assert '<mark class="check" title="à vérifier : casse différente du nom connu">brume</mark>' in author
    assert "<mark>Brume</mark>" in author
    assert "Ce que disent les documents" not in client.get("/wiki/brume?filter=player").text
