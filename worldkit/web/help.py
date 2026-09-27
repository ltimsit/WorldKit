"""Aide : retrouver ce que désigne un code, une notion ou un outil, depuis n'importe quel écran (jalon I7, I-AID-01).

Les définitions viennent du lexique du service (`lexicon.lookup`, `lexicon.index`), lu dans les documents ; ce
module ne fait que les mettre en page : page `/aide`, liens et infobulles sur les codes cités (filtres Jinja
`explain` et `linkify`), lien « ? » vers la fiche de l'écran courant.
"""

from __future__ import annotations

import html
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any
from urllib.parse import quote

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from markupsafe import Markup

from worldkit.service.lexicon import Entry, lexicon

KIND_LABELS = {"tool": "Outils", "stage": "Étapes du pipeline", "operation": "Opérations du service",
               "term": "Glossaire", "rule": "Règles (cadre de la fondation)",
               "technical_decision": "Décisions techniques", "interface_decision": "Décisions d'interface"}
# Ce qu'on reconnaît dans un texte : identifiants de règles et décisions, étapes, noms d'opérations.
CODE = re.compile(r"(?<![\w-])(?:[RTI]-[A-Z]{3}-\d{2}|E(?:1[0-2]|[1-9])\+?|[a-z]+\.[a-z_]+)(?![\w-])")


def md_inline(text: str) -> Markup:
    """Markdown en ligne des documents (gras, italique, code) → HTML échappé, codes connus liés."""
    s = html.escape(text or "")
    s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
    s = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)
    s = re.sub(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])", r"<i>\1</i>", s)
    s = s.replace("\n", "<br>")
    return linkify(Markup(s))


def plain(text: str, limit: int = 300) -> str:
    s = re.sub(r"[*`]", "", text or "").replace("\n", " ").strip()
    return s if len(s) <= limit else s[:limit - 1].rstrip() + "…"


def tooltip(e: Entry) -> str:
    head = f"{e.key} — {e.title}" if e.title and e.title != e.key else e.key
    return f"{head} : {plain(e.text)}" if e.text and e.text != e.title else head


def href(key: str) -> str:
    return f"/aide?q={quote(key, safe='')}"


def explain(code: Any, label: Any = None) -> Markup:
    """Un code connu du lexique → lien vers sa définition, avec la définition au survol ; sinon le texte seul."""
    text = "" if code is None else str(code)
    e = lexicon().get(text) if text else None
    shown = html.escape(str(label if label is not None else text))
    if not e:
        return Markup(shown)
    return Markup(f'<a class="term" href="{href(e.key)}" title="{html.escape(tooltip(e))}">{shown}</a>')


def title_of(code: Any) -> str:
    """Définition courte d'un code, pour un attribut `title` (badges)."""
    e = lexicon().get(str(code)) if code else None
    return tooltip(e) if e else ""


def linkify(markup: Any) -> Markup:
    """Lie les codes connus d'un fragment HTML (hors balises, liens et `<code>` déjà liés)."""
    lx = lexicon()
    s = str(markup)

    def code_tag(m: re.Match[str]) -> str:
        inner = html.unescape(m.group(1))
        e = lx.get(inner)
        return str(explain(inner, Markup(m.group(0)))) if e else m.group(0)

    s = re.sub(r"<code>([^<]+)</code>", code_tag, s)
    parts = re.split(r"(<[^>]+>)", s)
    out, depth = [], 0
    for part in parts:
        if part.startswith("<"):
            tag = part[1:].split(None, 1)[0].lower().rstrip(">")
            if tag in ("a", "script", "style", "code", "textarea"):
                depth += 1
            elif tag in ("/a", "/script", "/style", "/code", "/textarea"):
                depth = max(0, depth - 1)
            out.append(part)
        elif depth:
            out.append(part)
        else:
            out.append(CODE.sub(lambda m: str(explain(m.group(0))) if lx.get(m.group(0)) else m.group(0), part))
    return Markup("".join(out))


def tool_for(path: str) -> Entry | None:
    """Fiche de l'écran courant : l'adresse la plus précise de la carte des outils qui correspond."""
    best: tuple[int, Entry] | None = None
    for e in lexicon().entries.values():
        if e.kind != "tool":
            continue
        pattern = "^" + re.sub(r"\\\{[^}]*\\\}", r"[^/]+", re.escape(e.key)) + "$"
        if re.match(pattern, path) and (best is None or len(e.key) > best[0]):
            best = (len(e.key), e)
    return best[1] if best else None


def install(env: Any) -> None:
    env.filters["explain"] = explain
    env.filters["linkify"] = linkify
    env.filters["md"] = md_inline
    env.globals["explain"] = explain
    env.globals["title_of"] = title_of
    env.globals["tool_for"] = tool_for
    env.globals["help_href"] = href


def register(app: FastAPI, db: Path, render: Callable[..., HTMLResponse], page_factory: Callable[[], Any]) -> None:

    @app.get("/aide", response_class=HTMLResponse)
    def aide(request: Request) -> HTMLResponse:
        page = page_factory()
        q = request.query_params.get("q", "").strip()
        kind = request.query_params.get("kind") or None
        found = page.call("lexicon.lookup", {"q": q}) if q else None
        index = page.call("lexicon.index", {"kind": kind} if kind else {})
        groups: dict[str, list[dict[str, Any]]] = {k: [] for k in KIND_LABELS}
        for e in index.output or []:
            groups.setdefault(e["kind"], []).append(e)
        return render(request, "help.html", page, q=q, kind=kind, found=found, groups=groups,
                      kind_labels=KIND_LABELS)
