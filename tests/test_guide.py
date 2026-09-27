"""Le guide pas à pas (`docs/aide/guide.md`) est exécuté : ses commandes tournent, ses sorties annoncées sont vraies
(jalon I7, I-AID-02).

Conventions du guide (lues ici, invisibles ou discrètes pour le lecteur) :
- bloc ```powershell : chaque ligne `worldkit …` est exécutée, dans l'ordre du guide, sur un même monde temporaire
  (`valmont.db` y est remplacé par son chemin) ; ```powershell sans-test n'est pas exécuté (serve, pytest, modèle) ;
- bloc ```yaml fichier=NOM : écrit dans le dossier temporaire ; un argument égal à NOM désigne ce fichier ;
- bloc ```text sortie : chaque ligne non vide (hors « … ») doit apparaître dans la sortie du bloc exécuté précédent ;
- commentaire `<!-- écran /adresse : "texte" ; "texte" -->` : la page est demandée à l'interface et doit contenir
  chaque texte.
"""

from __future__ import annotations

import contextlib
import html
import io
import re
import shlex
from pathlib import Path

import pytest

GUIDE = Path(__file__).resolve().parents[1] / "docs" / "aide" / "guide.md"
FENCE = re.compile(r"^```([^\n]*)\n(.*?)^```", re.M | re.S)
SCREEN = re.compile(r"<!--\s*écran\s+(\S+)\s*:(.*?)-->", re.S)


def steps() -> list[tuple[str, str, str, int]]:
    """(sorte, info, contenu, ligne) dans l'ordre du guide : blocs de code et vérifications d'écran."""
    text = GUIDE.read_text(encoding="utf-8")
    found = [(m.start(), "fence", m.group(1).strip(), m.group(2)) for m in FENCE.finditer(text)]
    found += [(m.start(), "screen", m.group(1), m.group(2)) for m in SCREEN.finditer(text)]
    return [(kind, info, body, text.count("\n", 0, pos) + 1) for pos, kind, info, body in sorted(found)]


def squash(s: str) -> str:
    return " ".join(s.split())


def test_the_guide_runs_and_says_the_truth_I_AID_02(tmp_path, monkeypatch):
    from worldkit.cli import main
    monkeypatch.chdir(GUIDE.parents[2])  # les chemins du corpus sont relatifs à la racine du projet
    db = tmp_path / "valmont.db"
    files: dict[str, Path] = {}
    last_output, last_line = None, 0
    client = None
    executed = checked = 0
    for kind, info, body, line in steps():
        where = f"guide.md, ligne {line}"
        if kind == "screen":
            if client is None:
                pytest.importorskip("fastapi")
                from fastapi.testclient import TestClient
                from worldkit.web import create_app
                client = TestClient(create_app(db))
            page = client.get(info)
            assert page.status_code == 200, f"{where} : {info} → {page.status_code}"
            text = squash(html.unescape(re.sub(r"<[^>]+>", " ", page.text)))
            for expected in re.findall(r'"([^"]+)"', body):
                assert squash(expected) in text, f"{where} : « {expected} » absent de l'écran {info}"
                checked += 1
            continue
        words = info.split()
        lang = words[0] if words else ""
        options = dict(w.split("=", 1) if "=" in w else (w, "") for w in words[1:])
        if lang == "yaml" and "fichier" in options:
            path = tmp_path / options["fichier"]
            path.write_text(body, encoding="utf-8")
            files[options["fichier"]] = path
        elif lang == "powershell" and "sans-test" not in options:
            out = io.StringIO()
            for command in body.splitlines():
                if not command.startswith("worldkit "):
                    continue
                argv = [str(db) if a == "valmont.db" else str(files[a]) if a in files else a
                        for a in shlex.split(command)[1:]]
                with contextlib.redirect_stdout(out):
                    main(argv)
                executed += 1
            last_output, last_line = out.getvalue(), line
        elif lang == "text" and "sortie" in options:
            assert last_output is not None, f"{where} : bloc « sortie » sans commande avant lui"
            got = squash(last_output)
            for expected in body.splitlines():
                if expected.strip() and expected.strip() != "…":
                    assert squash(expected) in got, (f"{where} : « {expected.strip()} » absent de la sortie des "
                                                     f"commandes de la ligne {last_line} :\n{last_output}")
                    checked += 1
    assert executed >= 20 and checked >= 40, (executed, checked)


def test_the_guide_page_renders_sections_captions_and_links(tmp_path):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    from test_service import make_world
    from worldkit.web import create_app
    page = TestClient(create_app(make_world(tmp_path / "valmont.db"))).get("/aide/guide").text
    assert page.count('<h2 id="s') >= 10 and "sortie attendue (extrait)" in page and "non exécuté par les tests" in page
    assert '<a href="/wiki/aldren-ii?filter=player">' in page  # les écrans annoncés deviennent des liens
    assert 'href="/aide?q=R-FAI-05"' in page and "&lt;!--" not in page
