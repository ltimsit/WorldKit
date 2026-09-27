"""Jalon I7 : aide et lexique (cadre d'interface I-AID-01).

Le lexique est lu dans les documents ; ces tests vérifient qu'il est **complet** pour ce que l'outil affiche
(statuts, codes, valeurs, étapes, opérations, écrans, identifiants cités) : une valeur nouvelle sans
définition fait échouer la suite, l'aide ne peut pas prendre de retard sur le code.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from test_service import make_world
from worldkit.core.journal.models import EditStatus, Origin
from worldkit.core.schema.changes import Visibility
from worldkit.core.schema.issues import IssueCode, Severity
from worldkit.ingest.declaration import Mode, Nature, Voice
from worldkit.ingest.stages import STAGE_NAMES
from worldkit.service import REGISTRY, Session
from worldkit.service.lexicon import ID, lexicon

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "worldkit" / "web"

DISPLAYED = {
    "statut d'un résultat": ["ok", "refused", "pending", "error"],
    "sorte d'opération": ["read", "compute", "write", "admin"],
    "sévérité": [str(x) for x in Severity],
    "code de signalement": [str(x) for x in IssueCode],
    "notoriété": [str(x) for x in Visibility],
    "statut d'une édition": [str(x) for x in EditStatus],
    "origine": [str(x) for x in Origin],
    "nature, voix, mode": [str(x) for x in (*Nature, *Voice, *Mode)],
    "marque du graphe": ["masked", "redefined_later", "orphan", "layer"],
    "comparaison": ["added", "removed", "changed", "same"],
    "exécution et bac": ["running", "interrupted", "active", "dropped", "promoted"],
    "verdict de répétition à blanc": ["same", "gap", "divergence", "ignored"],
    "attendu de parcours": ["passed", "failed", "unstructured"],
    "filtre": ["author", "player"],
}


@pytest.mark.parametrize("family", sorted(DISPLAYED))
def test_every_displayed_value_has_a_definition_I_AID_01(family):
    missing = [v for v in DISPLAYED[family] if lexicon().get(v) is None]
    assert not missing, f"{family} sans définition (docs/aide/glossaire.md) : {missing}"


def test_every_stage_and_operation_is_explained():
    lx = lexicon()
    assert [s for s in STAGE_NAMES if lx.get(s) is None] == []
    assert [op for op in REGISTRY if lx.get(op) is None] == []
    assert lx.get("E5").title == "Traduction"


def test_every_rule_cited_by_the_code_or_the_help_exists_in_the_documents():
    sources = [*ROOT.joinpath("worldkit").rglob("*.py"), *WEB.joinpath("templates").glob("*.html"),
               *ROOT.joinpath("docs", "aide").glob("*.md")]
    cited = {m for p in sources for m in ID.findall(p.read_text(encoding="utf-8"))}
    missing = sorted(i for i in cited if lexicon().get(i) is None)
    assert missing == [], f"identifiants cités mais définis dans aucun cadre : {missing}"


def test_every_screen_has_its_card_in_the_tool_map():
    from worldkit.web.help import tool_for
    routes = re.findall(r'@app\.get\("([^"]+)"', "".join(p.read_text(encoding="utf-8") for p in WEB.glob("*.py")))
    screens = [re.sub(r"\{[^}]+\}", "1", r) for r in routes if not r.startswith(("/api", "/fragments"))]
    assert [s for s in screens if tool_for(s) is None] == []
    assert tool_for("/runs/3/artifact/E4").title == "Artefact d'une étape"
    assert tool_for("/runs/3").title == "Exécution"


def test_the_tool_map_only_cites_real_operations():
    for e in lexicon().entries.values():
        if e.kind == "tool":
            for op in re.findall(r"`([a-z]+\.[a-z_]+)`", e.fields.get("Opérations", "")):
                assert op in REGISTRY, (e.key, op)


def test_the_help_glossary_redefines_nothing_from_the_frameworks():
    assert [d for d in lexicon().duplicates if d[2].startswith("aide/")] == []


def test_lookup_finds_a_rule_its_citations_and_a_word(tmp_path):
    with Session(make_world(tmp_path / "valmont.db")) as s:
        r = s.call("lexicon.lookup", {"q": "R-NOT-07"})
        assert r.indicators["exact"] and "masqués" in r.output[0]["text"]
        assert {"masked_public_fact", "I-GRA-02"} <= set(r.output[0]["cited_by"])
        words = s.call("lexicon.lookup", {"q": "notoriété effective"}).output
        assert any(e["key"] == "effective_visibility" for e in words)


def test_explain_on_the_command_line(capsys):
    from worldkit.cli import main
    assert main(["explain", "key_collision"]) == 0
    out = capsys.readouterr().out
    assert "Collision de clé" in out and "R-FAI-05" in out
    assert main(["explain", "zzz-inconnu"]) == 1


def test_help_page_links_and_tooltips(tmp_path):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    from worldkit.web import create_app
    c = TestClient(create_app(make_world(tmp_path / "valmont.db")))
    index = c.get("/aide").text
    assert "Tableau de bord" in index and "Traduction" in index and "R-NOT-07" in index
    rule = c.get("/aide?q=R-NOT-07").text
    assert "masqués par une entité non publique" in rule and "cité par" in rule
    graph = c.get("/graph?entity=aldren-ii").text
    assert 'class="help-link"' in graph and "Voir la structure" in graph  # fiche de l'écran, lue dans outils.md
    assert 'href="/aide?q=R-NOT-07"' in graph and 'class="term"' in graph
    ops = c.get("/ops").text
    assert 'href="/aide?q=edit.apply"' in ops
    refused = c.post("/editor", data={"yaml": "id: x1\norigin: enrichment\nchanges:\n  - {op: set_attribute, entity: nobody, "
                                              "attribute: title, value: x}\n"})
    assert refused.status_code == 200
