"""Lexique : retrouver ce que désigne un code, une notion, une étape, une opération ou un outil (jalon I7, I-AID-01).

Une seule source : les **documents**. Le lexique lit les tableaux des cadres (règles `R-`, décisions `T-` et
`I-`, glossaires, étapes E1 à E12) et ceux de `docs/aide/` (carte des outils, glossaire complémentaire), plus
le registre des opérations. Il n'écrit rien et ne recopie rien : corriger une définition, c'est corriger le
document. Lecture pure, sans appel à un modèle (T-ARC-01).
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import Field

from .registry import REGISTRY, Output, Params, describe, operation

DOCS = Path(__file__).resolve().parents[2] / "docs"
# Ordre de priorité des documents (CLAUDE.md) : un identifiant défini deux fois garde la première définition.
SOURCES = ("cadre-fondation.md", "cadre-technique.md", "cadre-interface.md", "aide/glossaire.md", "aide/outils.md")
ID = re.compile(r"\b(?:R|T|I)-[A-Z]{3}-\d{2}\b")
STAGE = re.compile(r"^(E\d{1,2}\+?)\s+(.+)$")
KINDS = {"R": "rule", "T": "technical_decision", "I": "interface_decision"}


@dataclass
class Entry:
    key: str                      # R-NOT-07, E5, edit.apply, World, /graph
    kind: str                     # rule | technical_decision | interface_decision | stage | term | tool | operation
    title: str                    # libellé court
    text: str                     # définition (Markdown en ligne)
    source: str                   # document et section
    fields: dict[str, str] = field(default_factory=dict)
    aliases: list[str] = field(default_factory=list)

    def dump(self) -> dict[str, Any]:
        return {"key": self.key, "kind": self.kind, "title": self.title, "text": self.text, "source": self.source,
                "fields": self.fields, "aliases": self.aliases}


def norm(s: str) -> str:
    s = unicodedata.normalize("NFD", s.strip().strip("`*").lower())
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


def cells(line: str) -> list[str]:
    """Cellules d'une ligne de tableau Markdown ; un `|` entre accents graves n'est pas un séparateur."""
    out, cur, code = [], "", False
    for c in line.strip().strip("|"):
        if c == "`":
            code = not code
        if c == "|" and not code:
            out.append(cur.strip())
            cur = ""
        else:
            cur += c
    out.append(cur.strip())
    return out


def tables(path: Path) -> list[tuple[str, list[str], list[list[str]]]]:
    """(section, en-têtes, lignes) de chaque tableau d'un document."""
    out: list[tuple[str, list[str], list[list[str]]]] = []
    section, lines = "", path.read_text(encoding="utf-8").splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("#"):
            section = line.lstrip("#").strip()
        if line.startswith("|") and i + 1 < len(lines) and re.match(r"^\|[\s:|-]+\|$", lines[i + 1].strip()):
            header, rows = cells(line), []
            i += 2
            while i < len(lines) and lines[i].startswith("|"):
                rows.append(cells(lines[i]))
                i += 1
            out.append((section, header, rows))
            continue
        i += 1
    return out


def _plain(s: str) -> str:
    return re.sub(r"[*`]", "", s).strip()


def _column(header: list[str], row: list[str], *names: str) -> str:
    for n in names:
        for h, v in zip(header, row):
            if norm(h) == norm(n):
                return v
    return ""


class Lexicon:
    def __init__(self, docs: Path = DOCS) -> None:
        self.entries: dict[str, Entry] = {}
        self.alias: dict[str, str] = {}      # forme normalisée → clé
        self.duplicates: list[tuple[str, str, str]] = []  # (terme, source gardée, source ignorée)
        for name in SOURCES:
            path = docs / name
            if path.exists():
                self._read(path, name)
        for op in REGISTRY.values():
            d = describe(op)
            params = "; ".join(f"`{k}`{'' if v['required'] else ' (facultatif)'}{' : ' + v['description'] if v['description'] else ''}"
                               for k, v in d["params"].items())
            fields = {"sorte": f"`{op.kind}`", "règles": ", ".join(op.rules), "paramètres": params,
                      "ligne de commande": f"`worldkit call {op.name}" + "".join(
                          f" --param {k}=…" for k, v in d["params"].items() if v["required"]) + "`"}
            self._add(Entry(op.name, "operation", op.summary, op.summary, "registre des opérations (worldkit/service)",
                            {k: v for k, v in fields.items() if v}))

    def _add(self, e: Entry) -> None:
        if e.key in self.entries:
            self.duplicates.append((e.key, self.entries[e.key].source, e.source))
            return
        self.entries[e.key] = e
        for a in [e.key, *e.aliases]:
            self.alias.setdefault(norm(a), e.key)

    def _read(self, path: Path, name: str) -> None:
        self._paragraphs(path, name)
        for section, header, rows in tables(path):
            source = f"{name} — {section}"
            first = norm(header[0]) if header else ""
            for row in rows:
                if not row or not row[0]:
                    continue
                head = _plain(row[0])
                if ID.fullmatch(head):
                    title = _column(header, row, "Sujet")
                    text = _column(header, row, "Décision", "Règle", "Énoncé") or (row[1] if len(row) > 1 else "")
                    extra = {h: v for h, v in zip(header[1:], row[1:]) if v and v not in (title, text)}
                    self._add(Entry(head, KINDS[head[0]], _plain(title), text, source, extra))
                elif first == "etape" and STAGE.match(head):
                    code, label = STAGE.match(head).groups()  # type: ignore[union-attr]
                    extra = dict(zip(header[1:], row[1:]))
                    text = f"entrée : {extra.pop('Entrée', '')} → produit : {extra.pop('Artefact produit', '')}"
                    self._add(Entry(code, "stage", label, text, source, extra, [head]))
                elif any(norm(h) == "nom technique" for h in header):
                    # glossaires, catalogue des changements, étiquettes d'origine…
                    title = _plain(_column(header, row, "Terme", "Opération", "Étiquette") or head)
                    tech = _column(header, row, "Nom technique")
                    names = re.findall(r"`([^`]+)`", tech) or ([_plain(tech)] if _plain(tech) else [])
                    text = _column(header, row, "Définition", "Origine")
                    example = _column(header, row, "Exemple")
                    if example:
                        text = f"{text} Exemple : {example}".strip()
                    self._add(Entry(names[0] if names else title, "term", title, text, source, {},
                                    [title, *names[1:]]))
                elif first == "outil":
                    address = _plain(_column(header, row, "Adresse"))
                    extra = {h: v for h, v in zip(header[2:], row[2:]) if v and norm(h) != "sert a"}
                    self._add(Entry(address, "tool", head, _column(header, row, "Sert à"), source, extra, [head]))

    def _paragraphs(self, path: Path, name: str) -> None:
        """Décisions écrites en paragraphe : « **T-ING-19 — Extracteur oracle.** *(validé)* » puis le texte."""
        section, lines = "", path.read_text(encoding="utf-8").splitlines()
        for i, line in enumerate(lines):
            if line.startswith("#"):
                section = line.lstrip("#").strip()
            m = re.match(rf"^\*\*({ID.pattern[2:-2]}) — (.+?)\*\*\s*(.*)$", line)
            if not m:
                continue
            body = []
            for nxt in lines[i + 1:]:  # jusqu'à la décision suivante, un titre ou un filet
                if nxt.startswith(("#", "---")) or (nxt.startswith("**") and ID.search(nxt[:14])):
                    break
                body.append(nxt)
            status = m.group(3).strip().strip("*").strip()
            self._add(Entry(m.group(1), KINDS[m.group(1)[0]], m.group(2).rstrip(". "), "\n".join(body).strip(),
                            f"{name} — {section}", {"Statut": status} if status else {}))

    def get(self, q: str) -> Entry | None:
        key = self.alias.get(norm(q))
        return self.entries.get(key) if key else None

    def find(self, q: str, limit: int = 50) -> list[Entry]:
        """Correspondance exacte d'abord ; sinon les entrées dont la clé, le titre ou le texte contient la requête."""
        exact = self.get(q)
        if exact:
            return [exact]
        n = norm(q)
        if not n:
            return []
        named = [e for e in self.entries.values() if n in norm(e.key) or n in norm(e.title)
                 or any(n in norm(a) for a in e.aliases)]
        texted = [e for e in self.entries.values() if e not in named and n in norm(e.text)]
        return (named + texted)[:limit]

    def cited_by(self, key: str) -> list[Entry]:
        """Entrées dont le texte ou les champs citent cette clé (identifiant de règle ou de décision)."""
        pat = re.compile(rf"(?<![\w-]){re.escape(key)}(?![\w-])")
        return [e for e in self.entries.values() if e.key != key
                and (pat.search(e.text) or any(pat.search(v) for v in e.fields.values()))]


@lru_cache(maxsize=1)
def _cached(stamp: tuple[float, ...]) -> Lexicon:
    return Lexicon()


def lexicon() -> Lexicon:
    """Relu quand un document change (le serveur n'a pas à être relancé pour une définition corrigée)."""
    stamp = tuple((DOCS / n).stat().st_mtime if (DOCS / n).exists() else 0.0 for n in SOURCES)
    return _cached(stamp)


# ---------------------------------------------------------------------------
# Opérations (I-CLI-01 : le lexique est aussi en ligne de commande, `worldkit explain`)
# ---------------------------------------------------------------------------

class LookupParams(Params):
    q: str = Field(description="code (règle, décision, étape, opération, statut…), terme ou mot à chercher")


@operation("lexicon.lookup", "read", LookupParams, "ce que désigne un code, une notion, une étape, une opération ou "
           "un outil (définition lue dans les documents)", ("I-AID-01",), needs_world=False,
           example={"q": "R-NOT-07"})
def lexicon_lookup(ctx: Any, p: LookupParams) -> Output:
    lx = lexicon()
    found = lx.find(p.q)
    out = [{**e.dump(), "cited_by": [c.key for c in lx.cited_by(e.key)] if ID.fullmatch(e.key) else []}
           for e in found]
    return Output(out, [], {"found": len(out), "exact": bool(lx.get(p.q))})


class IndexParams(Params):
    kind: str | None = Field(None, description="rule, technical_decision, interface_decision, stage, term, tool, "
                                               "operation")


@operation("lexicon.index", "read", IndexParams, "toutes les entrées du lexique, par sorte", ("I-AID-01",),
           needs_world=False)
def lexicon_index(ctx: Any, p: IndexParams) -> Output:
    lx = lexicon()
    out = [e.dump() for e in lx.entries.values() if p.kind in (None, e.kind)]
    counts: dict[str, int] = {}
    for e in lx.entries.values():
        counts[e.kind] = counts.get(e.kind, 0) + 1
    return Output(out, [], {"entries": len(out), **counts})


__all__ = ["Entry", "Lexicon", "lexicon"]
