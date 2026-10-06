"""Magasin d'atelier (I8, T1 et T2) : sources, annotations et règles d'atelier, en ajout seul, par branche.

- **Source** : une version de document (Q2) ; son texte entier est gardé (`atelier_sources`), ses passages vont dans
  la table `passages` de l'ingestion. Le texte se relit toujours par `parse_document` : même découpage, mêmes
  empreintes (T-ING-10).
- **Annotation** : une ligne qu'on ne modifie jamais ; une correction est une nouvelle ligne qui en **remplace** une
  autre (`replaces`). L'annotation courante est la dernière de sa chaîne.
- **Lignée** (choix 16) : une branche voit ses annotations et celles de ses ancêtres faites avant son point de départ
  (`at_seq`, tête de la branche à la création, comparée à la lignée du journal). Limite connue : une annotation
  faite sur la branche parente après la création de la branche fille, mais avant toute nouvelle édition de la
  parente, porte le même rang que le point de départ et reste visible de la fille.
- **Règle d'atelier** (Q4) : une correction négative retenue pour le monde (« les veilleurs de nuit ne sont pas les
  Veilleurs »), appliquée aux sources futures de la branche et de ses descendantes.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from typing import Any

from worldkit.ingest.declaration import DocumentVersion, parse_document

_DDL = """
CREATE TABLE IF NOT EXISTS atelier_sources (
    doc_id TEXT NOT NULL, version_fp TEXT NOT NULL, text TEXT NOT NULL, created REAL NOT NULL,
    PRIMARY KEY (doc_id, version_fp));
CREATE TABLE IF NOT EXISTS annotations (
    ann_id INTEGER PRIMARY KEY AUTOINCREMENT, branch_id TEXT NOT NULL, at_seq INTEGER NOT NULL,
    doc_id TEXT NOT NULL, version_fp TEXT NOT NULL, passage INTEGER, start INTEGER, end INTEGER,
    kind TEXT NOT NULL, value TEXT NOT NULL, origin TEXT NOT NULL, confidence TEXT, status TEXT NOT NULL,
    replaces INTEGER, created REAL NOT NULL);
CREATE TABLE IF NOT EXISTS atelier_rules (
    rule_id INTEGER PRIMARY KEY AUTOINCREMENT, branch_id TEXT NOT NULL, at_seq INTEGER NOT NULL,
    form TEXT NOT NULL, kind TEXT NOT NULL, target TEXT, origin TEXT NOT NULL, replaces INTEGER,
    created REAL NOT NULL);
"""

STATUSES = ("proposed", "kept", "removed", "corrected", "ignored")
RULE_KINDS = ("not_entity", "not_entity_of")


def ensure_tables(conn: Any) -> None:
    from worldkit.ingest.store import ensure_tables as ingest_tables
    ingest_tables(conn)
    conn.executescript(_DDL)


@dataclass
class Annotation:
    """Une annotation : une portion d'un passage (ou le passage, ou la source), ce qu'elle désigne, d'où elle vient."""

    ann_id: int
    branch_id: str
    at_seq: int
    doc_id: str
    version_fp: str
    passage: int | None
    start: int | None
    end: int | None
    kind: str
    value: dict[str, Any] = field(default_factory=dict)
    origin: str = "author"
    confidence: str | None = None
    status: str = "proposed"
    replaces: int | None = None

    @property
    def by_author(self) -> bool:
        return self.origin == "author"


@dataclass
class Rule:
    rule_id: int
    branch_id: str
    at_seq: int
    form: str
    kind: str
    target: str | None
    origin: str
    replaces: int | None


# ---------------------------------------------------------------------------
# Sources
# ---------------------------------------------------------------------------

def _slug(text: str) -> str:
    import unicodedata
    folded = "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", "-", folded.lower()).strip("-") or "source"


def with_header(text: str, doc_id: str | None = None, mode: str = "source", nature: str = "diegetic",
                voice: str = "author") -> str:
    """Un texte collé sans en-tête reçoit l'en-tête minimal (R-DOC-02, R-ING-01) ; un texte avec en-tête est gardé."""
    if text.lstrip().startswith("---"):
        return text
    title = next((line.lstrip("# ").strip() for line in text.splitlines() if line.strip()), "source")
    header = f"---\nid: {doc_id or _slug(title)}\nmode: {mode}\nnature: {nature}\nvoice: {voice}\n---\n"
    return header + text


def import_source(world: Any, text: str, doc_id: str | None = None, **axes: str) -> DocumentVersion:
    """Crée la source d'atelier et sa version de document (Q2). Réimporter le même texte ne crée rien de plus."""
    from dataclasses import asdict

    from worldkit.ingest.store import dumps
    conn = world.store.conn
    ensure_tables(conn)
    full = with_header(text, doc_id, **axes)
    doc = parse_document(full, "atelier")
    doc = parse_document(full, f"atelier:{doc.doc_id}")
    with conn:
        conn.execute("INSERT OR IGNORE INTO atelier_sources VALUES (?, ?, ?, ?)",
                     (doc.doc_id, doc.fingerprint, full, time.time()))
        conn.execute("INSERT OR IGNORE INTO document_versions VALUES (?, ?, ?, ?)",
                     (doc.doc_id, doc.fingerprint, doc.path, dumps(asdict(doc.axes))))
        for p in doc.passages:
            conn.execute("INSERT OR IGNORE INTO passages VALUES (?, ?, ?, ?, ?, ?)",
                         (doc.doc_id, doc.fingerprint, p.index, p.fingerprint, p.text, dumps([])))
    return doc


def sources(world: Any) -> list[tuple[str, str]]:
    """(document, version) des sources, la plus récente version de chaque document d'abord."""
    ensure_tables(world.store.conn)
    rows = world.store.conn.execute("SELECT doc_id, version_fp, created FROM atelier_sources ORDER BY created DESC")
    seen, out = set(), []
    for doc_id, vfp, _ in rows:
        if doc_id not in seen:
            seen.add(doc_id)
            out.append((doc_id, vfp))
    return out


def source(world: Any, doc_id: str, version_fp: str | None = None) -> DocumentVersion:
    """La source (sa dernière version si `version_fp` est omis), relue depuis son texte."""
    ensure_tables(world.store.conn)
    if version_fp is None:
        row = world.store.conn.execute("SELECT text FROM atelier_sources WHERE doc_id = ? ORDER BY created DESC"
                                       " LIMIT 1", (doc_id,)).fetchone()
    else:
        row = world.store.conn.execute("SELECT text FROM atelier_sources WHERE doc_id = ? AND version_fp = ?",
                                       (doc_id, version_fp)).fetchone()
    if row is None:
        raise KeyError(f"source d'atelier inconnue : {doc_id}")
    return parse_document(row[0], f"atelier:{doc_id}")


# ---------------------------------------------------------------------------
# Annotations et règles, en ajout seul, lues par lignée
# ---------------------------------------------------------------------------

def _visible(world: Any, branch: str, rows: list[Any], branch_of, seq_of) -> list[Any]:
    """Les lignes visibles d'une branche : les siennes, et celles des ancêtres faites jusqu'au point de départ."""
    allowed = {b: hi for b, _, hi in world.store.segments(branch)}
    return [r for r in rows if branch_of(r) in allowed
            and (allowed[branch_of(r)] is None or seq_of(r) <= allowed[branch_of(r)])]


def add_annotation(world: Any, branch: str, doc: DocumentVersion, kind: str, value: dict[str, Any],
                   origin: str = "author", passage: int | None = None, start: int | None = None,
                   end: int | None = None, confidence: str | None = None, status: str = "proposed",
                   replaces: int | None = None) -> int:
    assert status in STATUSES, status
    conn = world.store.conn
    ensure_tables(conn)
    with conn:
        cur = conn.execute("INSERT INTO annotations (branch_id, at_seq, doc_id, version_fp, passage, start, end, kind,"
                           " value, origin, confidence, status, replaces, created)"
                           " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                           (branch, world.store.head_seq(branch), doc.doc_id, doc.fingerprint, passage, start, end,
                            kind, json.dumps(value, ensure_ascii=False, sort_keys=True), origin, confidence, status,
                            replaces, time.time()))
    return int(cur.lastrowid)


def _annotation(row: Any) -> Annotation:
    (ann_id, branch_id, at_seq, doc_id, vfp, passage, start, end, kind, value, origin, confidence, status,
     replaces, _) = row
    return Annotation(ann_id, branch_id, at_seq, doc_id, vfp, passage, start, end, kind, json.loads(value), origin,
                      confidence, status, replaces)


def history(world: Any, branch: str, doc: DocumentVersion) -> list[Annotation]:
    """Toutes les annotations visibles de la source sur la branche, remplacées comprises (ordre de création)."""
    ensure_tables(world.store.conn)
    rows = world.store.conn.execute("SELECT * FROM annotations WHERE doc_id = ? AND version_fp = ? ORDER BY ann_id",
                                    (doc.doc_id, doc.fingerprint)).fetchall()
    return [_annotation(r) for r in _visible(world, branch, rows, lambda r: r[1], lambda r: r[2])]


def current(world: Any, branch: str, doc: DocumentVersion) -> list[Annotation]:
    """Les annotations courantes : visibles, et non remplacées par une annotation visible."""
    seen = history(world, branch, doc)
    replaced = {a.replaces for a in seen if a.replaces is not None}
    return [a for a in seen if a.ann_id not in replaced]


def add_rule(world: Any, branch: str, form: str, kind: str, target: str | None = None, origin: str = "author",
             replaces: int | None = None) -> int:
    from worldkit.periphery.matching import fold
    assert kind in RULE_KINDS, kind
    conn = world.store.conn
    ensure_tables(conn)
    with conn:
        cur = conn.execute("INSERT INTO atelier_rules (branch_id, at_seq, form, kind, target, origin, replaces, created)"
                           " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                           (branch, world.store.head_seq(branch), fold(form), kind, target, origin, replaces,
                            time.time()))
    return int(cur.lastrowid)


def rules(world: Any, branch: str) -> list[Rule]:
    """Les règles d'atelier courantes de la branche (lignée, remplacements)."""
    ensure_tables(world.store.conn)
    rows = world.store.conn.execute("SELECT rule_id, branch_id, at_seq, form, kind, target, origin, replaces"
                                    " FROM atelier_rules ORDER BY rule_id").fetchall()
    seen = [Rule(*r) for r in _visible(world, branch, rows, lambda r: r[1], lambda r: r[2])]
    replaced = {r.replaces for r in seen if r.replaces is not None}
    return [r for r in seen if r.rule_id not in replaced]
