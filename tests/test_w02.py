"""Parcours W02 — ingestion du premier lot b1 avec l'extracteur oracle (J3.1).

R-DOC-01, T-ING-01, T-ING-02, T-ING-03, T-ING-05, T-ING-07, R-PRI-03, R-ING-02, R-SCH-06, R-DEC-02, R-DEC-03.
"""

from __future__ import annotations

import pytest

from support import VALMONT, base_world
from worldkit.core.journal.models import EditStatus
from worldkit.ingest.batch import BatchError, batch_documents, ingest
from worldkit.ingest.review import flagged_passages, proposals, supports
from worldkit.periphery.extraction import OracleExtractor

ORACLE = OracleExtractor(VALMONT / "gold")
B1 = batch_documents(VALMONT / "docs" / "batches.yaml", "b1")


@pytest.fixture(scope="module")
def world():
    w = base_world()
    ingest(w, "b1", B1, ORACLE)
    yield w
    w.close()


@pytest.fixture(scope="module")
def views(world):
    return {v.id: v for v in proposals(world, "b1")}


def tags(views, pid):
    return set(views[pid].tags)


def texts(views):
    return [c.text for v in views.values() for c in v.changes]


def test_w02_all_proposals_share_the_batch_base_T_ING_07(world, views):
    """Base (reference, e006, schema_rev e000) pour toutes les propositions, en attente, rien d'appliqué."""
    e006, e000 = world.resolve_point("@base"), 1
    assert world.store.edit("e000").edit.id == "e000"
    assert {(v.base.seq, v.base.schema_rev) for v in views.values()} == {(e006, e000)}
    assert {v.status for v in views.values()} == {EditStatus.PENDING}
    assert world.state().seq == e006


def test_w02_supports_are_recorded_without_questions_T_ING_11(world, views):
    found = {(s.doc, s.passage) for s in supports(world, "b1")}
    assert found == {("notes-baron", 1), ("lieux-de-valmont", 1), ("lieux-de-valmont", 2), ("lieux-de-valmont", 5)}
    assert not any(v.passage == 1 and v.doc == "notes-baron" for v in views.values())
    assert not any(v.doc == "lieux-de-valmont" and v.passage == 5 for v in views.values())


def test_w02_one_new_council_for_the_whole_batch(views):
    creations = [c for c in texts(views) if c.startswith("+ entité conseil")]
    assert creations == ["+ entité conseil-marchands (Faction)"]
    assert any("conseil-marchands" in t for t in texts(views) if "hautval" in t)  # lieux p2 : même entité


def test_w02_notes_p3_collision_is_an_anomaly_T_ING_03(views):
    p3 = views["b1.notes-baron.p3.1"]
    rules = next(c for c in p3.changes if c.text == "+ rules(conseil-marchands, brume)")
    assert "anomaly" in rules.tags
    assert rules.detail["occupied_by"]["fact"] == ["rel", "odon", "rules", "brume"]
    assert [c.text for c in p3.changes][:2] == ["+ entité conseil-marchands (Faction)",
                                                "conseil-marchands.name = 'le conseil des marchands'"]


def test_w02_notes_p4_member_of_depends_on_the_council_creation_T_ING_05(views):
    assert views["b1.notes-baron.p4.1"].depends_on == ["b1.notes-baron.p3.1"]


def test_w02_symmetric_batch_conflict_on_based_in_R_PRI_03(views):
    notes, lieux = views["b1.notes-baron.p4.2"], views["b1.lieux-de-valmont.p2.1"]
    assert "batch_conflict" in notes.tags and "batch_conflict" in lieux.tags
    assert notes.changes[0].detail["conflicts_with"] == ["lieux-de-valmont p2"]
    assert lieux.changes[0].detail["conflicts_with"] == ["notes-baron p4"]
    assert "anomaly" not in set(notes.tags) | set(lieux.tags)  # aucune ne l'emporte


def test_w02_notes_p2_vassal_of_out_of_schema_R_SCH_06(views):
    assert tags(views, "b1.notes-baron.p2.1") == {"out_of_schema"}


def test_w02_notes_p7_anomaly_and_internal_contradiction_R_ING_02(views):
    p7 = views["b1.notes-baron.p7.1"]
    assert {"anomaly", "internal_contradiction"} <= set(p7.tags)
    assert p7.changes[0].detail["contradicts"] == ["notes-baron p1"]


def test_w02_notes_p5_relation_and_hint_are_two_proposals_T_ING_15(views):
    fact, hint = views["b1.notes-baron.p5.1"], views["b1.notes-baron.p5.2"]
    assert [c.text for c in fact.changes] == ["+ member_of(odon, cercle-des-cendres)"]
    assert tags(views, hint.id) == {"hint_visibility"} and hint.depends_on == [fact.id]


def test_w02_notes_p6_attribution_without_facts_R_DEC_03(world, views):
    assert ("notes-baron", 6, ["attribution"]) in flagged_passages(world, "b1")
    assert not any(v.doc == "notes-baron" and v.passage == 6 for v in views.values())


def test_w02_traps_not_created(views):
    created = [t for t in texts(views) if t.startswith("+ entité")]
    for trap in ("brume-sur-mer", "roi-gris", "collines"):
        assert not any(trap in t for t in created)
    assert "brume.aliases += 'Brume-sur-Mer'" in texts(views)
    assert "aldren-ii.aliases += 'le Roi Gris'" in texts(views)


def test_batch_ids_are_unique(world):
    with pytest.raises(BatchError):
        ingest(world, "b1", B1, ORACLE)


def _signature(world):
    return sorted((v.id, tuple(v.tags), tuple(c.text for c in v.changes), tuple(v.depends_on),
                   tuple(c.fingerprint for c in v.changes)) for v in proposals(world, "b1"))


def test_document_order_does_not_change_proposals_R_PRI_03(views):
    reversed_world = base_world()
    ingest(reversed_world, "b1", list(reversed(B1)), ORACLE)
    straight = base_world()
    ingest(straight, "b1", B1, ORACLE)
    assert _signature(reversed_world) == _signature(straight)


def test_reingesting_the_same_document_asks_nothing_T_ING_10():
    world = base_world()
    ingest(world, "b1", B1, ORACLE)
    again = ingest(world, "b1-bis", B1[:1], ORACLE)
    assert (again.unchanged, again.extracted, again.cached, len(again.proposals)) == (7, 0, 0, 0)


def test_known_passage_text_comes_from_the_cache_T_ING_09(tmp_path):
    """Le cache est indexé par l'empreinte du passage : un autre document au même texte n'est pas réextrait."""
    world = base_world()
    first = ingest(world, "b1", B1, ORACLE)
    copy = tmp_path / "copie.md"
    copy.write_text(B1[0].read_text(encoding="utf-8").replace("id: notes-baron", "id: notes-baron-copie"),
                    encoding="utf-8")
    again = ingest(world, "b1-copie", [copy], ORACLE)
    assert first.cached == 0 and (again.extracted, again.cached) == (0, 7)
