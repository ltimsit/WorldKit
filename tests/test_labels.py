"""Libellés du schéma dans l'interface (R-SCH-08, R-SCH-09) : libellé puis identifiant, l'identifiant restant visible
(I-PRI-01) ; l'export JSON pour un LLM garde les identifiants."""

from __future__ import annotations

from support import base_world
from worldkit.core.views import Filter, View, export_json, render_page
from worldkit.core.views.model import attribute_label, relation_label, type_label


def test_page_lines_carry_the_schema_labels():
    state = base_world().state()
    page = View(state, Filter.AUTHOR).page("aldren-ii")
    assert page.type_label == "Personnage"
    assert {(a.name, a.label) for a in page.attributes} >= {("title", "titre"), ("death_cause", "cause de la mort")}
    assert ("sibling_of", "frère ou sœur de") in {(r.relation, r.label) for r in page.relations}
    md = render_page(page, View(state, Filter.AUTHOR))
    assert "- frère ou sœur de (sibling_of) → Mervin (`mervin`)" in md and "Personnage (Character)" in md


def test_labels_fall_back_to_identifiers_and_sheets_use_their_system():
    state = base_world().state()
    assert relation_label(state, "same_as") == "same_as"  # relation de la plateforme : pas de libellé de schéma
    assert attribute_label(state, "nobody", "title") == "title" and type_label(state, "nobody") == ""
    sheet = next(e for e, r in state.entities.items() if r.sheet is not None and r.sheet.system == "system-a")
    assert attribute_label(state, sheet, "hp") == "PV"


def test_the_llm_export_keeps_identifiers():
    out = export_json(base_world().state(), Filter.AUTHOR)
    assert "sibling_of" in out and "frère ou sœur de" not in out


def test_graph_and_review_speak_french(tmp_path):
    from test_service import make_world
    from worldkit.service import Session
    with Session(make_world(tmp_path / "valmont.db")) as s:
        g = s.call("graph.view", {"entity": "aldren-ii"}, record=False).output
    edge = next(e for e in g["edges"] if e["relation"] == "sibling_of")
    assert edge["relation_label"] == "frère ou sœur de"
    node = next(n for n in g["nodes"] if n["id"] == "aldren-ii")
    assert node["type_label"] == "Personnage" and any(a["label"] == "titre" for a in node["attributes"])
    from worldkit.core.journal.models import parse_edit
    from worldkit.service.ops import in_french
    state = base_world().state()
    change = parse_edit({"id": "x", "changes": [{"op": "add_relation", "from": "odon", "relation": "rules",
                                                 "to": "brume"}]}).changes[0]
    assert in_french(change, state) == "Odon de Brume — gouverne — Brume"
