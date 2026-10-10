"""Mondes de l'auteur (`mondes/`) : distincts des corpus, qui restent des instruments de mesure (T-TST-01)."""

from __future__ import annotations

import yaml

from support import ROOT
from worldkit.core.journal.models import parse_edit
from worldkit.core.world import World

AUTHOR = ROOT / "mondes" / "corbelle"
CORPUS = ROOT / "corpus" / "corbelle-v1" / "corbelle"
ADDED = {"on_river", "runs", "near", "hates"}


def relations(path):
    return yaml.safe_load(path.read_text(encoding="utf-8"))["relations"]


def test_the_author_corbelle_is_the_corpus_plus_four_relations_and_the_corpus_keeps_hates_out_E_007():
    mine, corpus = relations(AUTHOR / "schema.yaml"), relations(CORPUS / "schema.yaml")
    assert set(mine) - set(corpus) == ADDED and all(mine[r] == corpus[r] for r in corpus)
    assert "hates" not in corpus  # le cas hors schéma de la question ciblée


def test_the_author_corbelle_builds_from_scratch():
    world = World.create(":memory:", AUTHOR / "world.yaml")
    for raw in yaml.safe_load((AUTHOR / "edits" / "base.yaml").read_text(encoding="utf-8"))["edits"]:
        assert world.apply(parse_edit(raw)).status == "applied"
    state = world.state()
    assert ADDED <= set(state.world.relations) and state.world.relations["near"].symmetric
    assert "ysolde-marcastel" in state.entities
