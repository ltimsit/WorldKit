"""J8 : méta à l'ingestion — parcours W08 (« Bestiaire : fiche, système, détection de nature »).

R-MET-01 à R-MET-06, R-SCH-02, R-SCH-06, R-SCH-10, R-DEC-01 à R-DEC-03, R-PRI-04 ; T-FAI-01, T-ING-11, T-ING-13.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from support import base_world, edit
from test_w10_w11 import ORACLE, docs
from worldkit.core.journal.models import EditStatus
from worldkit.core.schema import IssueCode
from worldkit.core.views import state_report
from worldkit.ingest import decide
from worldkit.ingest.batch import ingest
from worldkit.ingest.meta import decide_nature, open_questions
from worldkit.ingest.queue import load, load_one
from worldkit.ingest.review import flagged_passages, proposals, supports
from worldkit.periphery.extraction import Extraction

DOC = "bestiaire-loup-de-cendre"
P2, P3, P6 = f"b4.{DOC}.p2.1", f"b4.{DOC}.p3.1", f"b4.{DOC}.p6.1"
SHEET_B = "loup-de-cendre@system-b"


@pytest.fixture
def b4():
    w = base_world()
    report = ingest(w, "b4", docs("b4"), ORACLE)
    yield w, report
    w.close()


def flags(world):
    return {i: f for d, i, f in flagged_passages(world) if d == DOC}


# --- W08 ---

def test_w08_p3_sheet_values_are_supports_constitution_out_of_schema_R_SCH_06(b4):
    w, _ = b4
    keys = {s.key for s in supports(w) if s.passage == 3}
    assert {("attr", "loup-de-cendre@system-a", a) for a in ("hp", "strength", "dexterity", "intelligence")} <= keys
    assert ("value", "loup-de-cendre@system-a", "abilities", "system-a:bite") in keys
    p3 = load_one(w, P3)
    assert [(c.change.attribute, sorted(c.tags)) for c in p3.changes] == [("constitution", ["out_of_schema"])]


def test_w08_p4_system_rule_is_a_support_not_an_edit_T_FAI_01(b4):
    w, _ = b4
    assert [s.key for s in supports(w) if s.passage == 4] == [("schema", "system-a", "type", "Creature", "hp")]
    assert not [p for p in load(w) if p.passage == 4]


def test_w08_p6_nature_is_proposed_never_decided_R_DEC_02(b4):
    w, _ = b4
    assert flags(w)[6] == ["nature_detected"]
    assert [(d, i, s) for d, i, _, s in open_questions(w)] == [(DOC, 6, [SHEET_B])]
    assert P6 not in {v.id for v in proposals(w)}          # non présentée
    refused = decide.accept(w, P6)                          # ni acceptable
    assert not refused.ok and refused.issues[0].rule == "R-DEC-02"
    assert SHEET_B not in w.state().entities


def test_w08_accepting_the_nature_then_the_sheet_creates_it_and_lifts_the_missing_sheet_R_MET_06(b4):
    w, _ = b4
    missing = [i for i in state_report(w.state()) if i.code is IssueCode.MISSING_SHEET]
    assert [i.path for i in missing] == [SHEET_B]
    assert decide_nature(w, DOC, 6, accept=True) == [P6]
    assert open_questions(w) == [] and P6 in {v.id for v in proposals(w)}
    assert decide.accept(w, P6).ok and decide.accept(w, P2).ok
    state = w.state()
    sheet = state.entities[SHEET_B].sheet
    assert (sheet.of, sheet.system, sheet.category) == ("loup-de-cendre", "system-b", "Monster")
    assert (state.facts[("attr", SHEET_B, "level")].value, state.facts[("attr", SHEET_B, "threat")].value) == (7, 8)
    assert not [i for i in state_report(state) if i.code is IssueCode.MISSING_SHEET]


def test_w08_after_e102_sheet_a_is_non_conforming_not_modified_R_SCH_10(b4):
    w, _ = b4
    before = w.state().facts[("attr", "loup-de-cendre@system-a", "hp")]
    assert w.apply(edit({"op": "schema_set_type", "scope": "system-a", "type": "Creature", "attribute": "hp",
                         "constraint": {"min": 6, "max": 10}}, id="e102")).ok
    state = w.state()
    assert state.facts[("attr", "loup-de-cendre@system-a", "hp")] == before
    assert [(i.code, i.path) for i in state_report(state) if i.code is IssueCode.NON_CONFORMING] == \
        [(IssueCode.NON_CONFORMING, "loup-de-cendre@system-a.hp")]


def test_w08_traps_attribution_and_no_invented_weakness_R_DEC_03(b4):
    w, _ = b4
    assert flags(w)[5] == ["attribution"]
    values = [c.change.value for p in load(w) for c in p.changes if getattr(c.change, "attribute", "") == "weaknesses"]
    assert values == ["eau courante"]


def test_refusing_the_nature_closes_the_meta_proposals_and_is_remembered_R_PRI_04(b4):
    w, _ = b4
    assert decide_nature(w, DOC, 6, accept=False, reason="le niveau 7 est une rumeur") == [P6]
    assert load_one(w, P6).status is EditStatus.ABANDONED and load_one(w, P6).closed_reason == "nature refusée"
    assert open_questions(w) == []
    ingest(w, "b4bis", docs("b4"), ORACLE)  # même texte : ni question ni proposition nouvelle
    assert open_questions(w) == [] and not [p for p in load(w) if p.passage == 6]
    with pytest.raises(KeyError):
        decide_nature(w, DOC, 6, accept=True)


# --- Garde de classement (R-MET-03) et forme réduite `sheet_values` (décisions J8) ---

@dataclass
class Scripted:
    """Extracteur de test : des brouillons par préfixe de passage."""

    script: dict[str, tuple[dict, ...]]
    version: str = "scripted-1"

    def extract(self, doc_id, passage_text, context=None):
        for prefix, drafts in self.script.items():
            if passage_text.startswith(prefix):
                return Extraction(tuple(drafts))
        return Extraction()


def write(tmp_path, name, nature, body):
    path = tmp_path / f"{name}.md"
    path.write_text(f"---\nid: {name}\nmode: source\nnature: {nature}\nvoice: author\n---\n{body}\n", encoding="utf-8")
    return path


LEVEL = {"op": "set_attribute", "entity": "loup-de-cendre@system-a", "attribute": "hp", "value": 6}
HAUNTS = {"op": "add_value", "entity": "loup-de-cendre", "attribute": "weaknesses", "value": "le sel"}


def test_declared_nature_wins_changes_against_it_are_flagged_not_proposed_R_DEC_01_R_MET_03(tmp_path):
    w = base_world()
    diegetic = write(tmp_path, "chronique-loup", "diegetic", "Le Loup a six PV et craint le sel.")
    marked = write(tmp_path, "notes-loup", "mixed", "[meta]Le Loup a six PV et craint le sel.[/meta]")
    both = write(tmp_path, "melange-loup", "mixed", "Il craint le sel. [meta]Le Loup a six PV.[/meta]")
    extractor = Scripted({"Le Loup a six": (LEVEL, HAUNTS), "[meta]Le Loup a six": (LEVEL, HAUNTS),
                          "Il craint le sel": (LEVEL, HAUNTS)})
    ingest(w, "g1", [diegetic, marked, both], extractor)
    by_doc = {d: f for d, _, f in flagged_passages(w)}
    assert by_doc["chronique-loup"] == ["meta_in_diegetic"]
    assert by_doc["notes-loup"] == ["diegetic_in_meta"]
    assert "melange-loup" not in by_doc
    subjects = sorted((p.doc, p.subject) for p in load(w))
    assert subjects == [("chronique-loup", "loup-de-cendre"), ("melange-loup", "loup-de-cendre"),
                        ("melange-loup", "loup-de-cendre@system-a"), ("notes-loup", "loup-de-cendre@system-a")]
    w.close()


def test_sheet_values_translate_deterministically_Q4(tmp_path):
    w = base_world()
    doc = write(tmp_path, "fiches-loup", "meta_sheet", "Système B : niveau 5.\n\nSystème A : PV 7.\n\nSystème B pour Brume.")
    extractor = Scripted({
        "Système B : niveau": ({"op": "sheet_values", "of": "loup-de-cendre", "system": "system-b",
                               "values": {"level": 5, "threat": 3}},),
        "Système A": ({"op": "sheet_values", "of": "loup-de-cendre", "system": "system-a", "values": {"hp": 7}},),
        "Système B pour": ({"op": "sheet_values", "of": "brume", "system": "system-b", "values": {"level": 1}},),
    })
    report = ingest(w, "s1", [doc], extractor)
    changes = {p.passage: [(c.change.op, c.change.entity) for c in p.changes] for p in load(w)}
    assert changes[1] == [("create_entity", SHEET_B), ("set_attribute", SHEET_B), ("set_attribute", SHEET_B)]
    created = next(c.change for p in load(w) if p.passage == 1 for c in p.changes if c.change.op == "create_entity")
    assert created.sheet.category == "Monster"  # fiches exigées du monde (R-MET-06)
    assert changes[2] == [("set_attribute", "loup-de-cendre@system-a")]  # fiche existante : valeurs seules
    assert 3 not in changes and report.flagged[f"fiches-loup p3"] == ["extraction_error"]  # Brume : aucune catégorie
    w.close()


def test_cli_review_lists_and_decides_the_nature_question(tmp_path, capsys):
    from worldkit.cli import main
    from support import VALMONT
    from worldkit.core.world import World
    db = tmp_path / "valmont.db"
    w = World.create(db, VALMONT / "world.yaml")
    base = base_world()
    for _, e in base.store.journal("reference")[1:]:
        assert w.apply(e).ok
    base.close()
    w.close()
    run = lambda *a: main(["--db", str(db), *a])
    assert run("ingest", "b4", "--batches", str(VALMONT / "docs" / "batches.yaml"), "--oracle", str(VALMONT / "gold")) == 0
    capsys.readouterr()
    assert run("review", "list") == 0
    out = capsys.readouterr().out
    assert f"question de nature : {DOC} p6" in out and P6 not in out.split("question de nature")[0]
    assert run("review", "accept", P6) == 1
    assert "R-DEC-02" in capsys.readouterr().out
    assert run("review", "nature", DOC, "6", "accept") == 0
    assert "acceptée" in capsys.readouterr().out
    assert run("review", "accept", P6) == 0
