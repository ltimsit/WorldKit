"""Tables de l'ingestion (cadre technique §2.1) : lots, versions de documents, passages, cache
d'extraction, propositions et leurs qualifications, dépendances, supports.

Créées à la demande (`CREATE TABLE IF NOT EXISTS`) : une base créée avant J3 reste utilisable.
Les supports sont hors journal (R-FAI-01, T-ING-11).
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any

_DDL = """
CREATE TABLE IF NOT EXISTS batches (
    batch_id TEXT PRIMARY KEY, branch_id TEXT NOT NULL, base_seq INTEGER NOT NULL,
    base_schema_rev INTEGER NOT NULL, opened INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS document_versions (
    doc_id TEXT NOT NULL, version_fp TEXT NOT NULL, path TEXT NOT NULL, axes TEXT NOT NULL,
    PRIMARY KEY (doc_id, version_fp));
CREATE TABLE IF NOT EXISTS batch_documents (
    batch_id TEXT NOT NULL, doc_id TEXT NOT NULL, version_fp TEXT NOT NULL, position INTEGER NOT NULL,
    PRIMARY KEY (batch_id, doc_id));
CREATE TABLE IF NOT EXISTS passages (
    doc_id TEXT NOT NULL, version_fp TEXT NOT NULL, idx INTEGER NOT NULL, passage_fp TEXT NOT NULL,
    text TEXT NOT NULL, flags TEXT NOT NULL, PRIMARY KEY (doc_id, version_fp, idx));
CREATE TABLE IF NOT EXISTS extraction_cache (
    passage_fp TEXT NOT NULL, schema_fp TEXT NOT NULL, extractor TEXT NOT NULL, payload TEXT NOT NULL,
    PRIMARY KEY (passage_fp, schema_fp, extractor));
CREATE TABLE IF NOT EXISTS proposals (
    edit_id TEXT PRIMARY KEY REFERENCES edits(edit_id), batch_id TEXT NOT NULL, doc_id TEXT NOT NULL,
    version_fp TEXT NOT NULL, passage_idx INTEGER NOT NULL, subject TEXT NOT NULL, kind TEXT NOT NULL,
    issues TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS proposal_changes (
    edit_id TEXT NOT NULL, idx INTEGER NOT NULL, fingerprint TEXT NOT NULL, tags TEXT NOT NULL,
    detail TEXT NOT NULL, PRIMARY KEY (edit_id, idx));
CREATE TABLE IF NOT EXISTS proposal_deps (
    edit_id TEXT NOT NULL, depends_on TEXT NOT NULL, PRIMARY KEY (edit_id, depends_on));
CREATE TABLE IF NOT EXISTS supports (
    doc_id TEXT NOT NULL, version_fp TEXT NOT NULL, passage_idx INTEGER NOT NULL, fact_key TEXT NOT NULL,
    value TEXT NOT NULL, batch_id TEXT NOT NULL, PRIMARY KEY (doc_id, version_fp, passage_idx, fact_key));
CREATE TABLE IF NOT EXISTS new_entities (
    batch_id TEXT NOT NULL, label TEXT NOT NULL, entity_id TEXT NOT NULL, type TEXT NOT NULL, name TEXT,
    PRIMARY KEY (batch_id, label));
"""


def dumps(x: Any) -> str:
    return json.dumps(x, ensure_ascii=False, sort_keys=True, default=list)


def _tuplify(x: Any) -> Any:
    return tuple(_tuplify(i) for i in x) if isinstance(x, list) else x


def loads_key(text: str) -> Any:
    return _tuplify(json.loads(text))


def ensure_tables(conn: sqlite3.Connection) -> None:
    conn.executescript(_DDL)
