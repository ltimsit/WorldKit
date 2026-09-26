"""Ligne de commande J2 : créer Valmont, saisir l'état de base, lire les deux wikis (T-LNG-01)."""

from __future__ import annotations

import json

from support import VALMONT
from worldkit.cli import main


def test_cli_world_edit_wiki_export_check(tmp_path, capsys):
    db = str(tmp_path / "valmont.db")
    run = lambda *args: main(["--db", db, *args])  # noqa: E731
    assert run("world", "init", str(VALMONT / "world.yaml")) == 0
    assert run("world", "init", str(VALMONT / "world.yaml")) == 2  # le monde existe déjà
    assert run("edit", "apply", str(VALMONT / "edits" / "base.yaml")) == 0
    assert run("point", "set", "@base") == 0
    capsys.readouterr()

    assert run("wiki", "page", "aldren-ii", "--filter", "player", "--point", "@base") == 0
    out = capsys.readouterr().out
    assert "close" in out and "poison" not in out

    assert run("wiki", "page", "cercle-des-cendres", "--filter", "player") == 1
    capsys.readouterr()

    assert run("export", "--filter", "player", "--point", "@base") == 0
    graph = json.loads(capsys.readouterr().out)
    assert "cercle-des-cendres" not in {e["id"] for e in graph["entities"]}

    assert run("check") == 0
    assert "missing_sheet" in capsys.readouterr().out

    assert run("wiki", "render", "--out", str(tmp_path / "wiki"), "--filter", "player") == 0
    assert (tmp_path / "wiki" / "index.md").exists() and not (tmp_path / "wiki" / "cercle-des-cendres.md").exists()


def test_cli_refused_edit_exit_code(tmp_path, capsys):
    db = str(tmp_path / "v.db")
    main(["--db", db, "world", "init", str(VALMONT / "world.yaml")])
    bad = tmp_path / "bad.yaml"
    bad.write_text("id: x1\norigin: enrichment\nchanges:\n  - { op: delete_entity, entity: odon }\n", encoding="utf-8")
    assert main(["--db", db, "edit", "apply", str(bad)]) == 1
    assert "R-EDI-07" in capsys.readouterr().out
    assert main(["--db", str(tmp_path / "absent.db"), "check"]) == 2
