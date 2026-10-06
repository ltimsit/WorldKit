"""Corpus dérivé Valmont bruité (corpus/valmont-bruite-v1) : reproductible et cohérent."""

from __future__ import annotations

import importlib.util

import yaml

from support import ROOT
from worldkit.ingest.batch import batch_documents
from worldkit.ingest.declaration import read_document

NOISY = ROOT / "corpus" / "valmont-bruite-v1"


def load_tool():
    spec = importlib.util.spec_from_file_location("derive_noisy", ROOT / "corpus" / "tools" / "derive_noisy.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_derived_corpus_is_exactly_what_the_script_produces(tmp_path):
    """Graine fixe : régénérer donne les mêmes fichiers (aucune retouche à la main)."""
    load_tool().derive(tmp_path)
    for generated in tmp_path.rglob("*.*"):
        committed = NOISY / generated.relative_to(tmp_path)
        assert committed.read_text(encoding="utf-8") == generated.read_text(encoding="utf-8"), committed


def test_gold_mentions_appear_in_their_noisy_passage():
    for level in ("l1", "l2"):
        docs = {read_document(p).doc_id: read_document(p)
                for p in batch_documents(NOISY / level / "docs" / "batches.yaml", f"{level}-b1")}
        for g in (yaml.safe_load(p.read_text(encoding="utf-8")) for p in (NOISY / level / "gold").glob("*.yaml")):
            doc = docs[g["document"]]
            for entry in g["passages"]:
                passage = next(p for p in doc.passages if p.text.startswith(entry["starts_with"]))
                assert passage.index == entry["index"]
                for surface in entry["mentions"]:
                    assert surface.lower() in passage.text.lower(), (level, g["document"], surface)
                assert len(entry["mentions"]) >= 1
