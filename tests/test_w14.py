"""Parcours W14 — document obsolète, puis levée du statut (J3.4 ; R-DOC-05, R-PRI-01, R-EDI-09).

Décision J3.4 : l'obsolescence bloque sans clore ; la levée réactive telles quelles les propositions
bloquées ; les décisions déjà tracées restent valables.
"""

from __future__ import annotations

import pytest

from support import VALMONT, base_world, edit
from worldkit.core.journal.models import EditStatus
from worldkit.core.schema import IssueCode
from worldkit.ingest import decide
from worldkit.ingest.batch import batch_documents, ingest
from worldkit.ingest.review import proposals
from worldkit.periphery.extraction import OracleExtractor

ORACLE = OracleExtractor(VALMONT / "gold")
B8 = batch_documents(VALMONT / "docs" / "batches.yaml", "b8")


def obsolete(value, id_):
    return edit({"op": "set_document_obsolete", "document": "vieilles-notes", "value": value},
                origin="curation", id=id_)


@pytest.fixture
def world():
    w = base_world()
    ingest(w, "b8", B8, ORACLE)
    yield w
    w.close()


def test_w14_first_ingestion_two_anomalies(world):
    views = proposals(world, "b8")
    assert len(views) == 2 and all("anomaly" in v.tags for v in views)


def test_w14_obsolete_blocks_without_closing(world):
    assert world.apply(obsolete(True, "e103")).status == EditStatus.APPLIED
    views = proposals(world, "b8")
    assert len(views) == 2 and all(v.blocked and v.status is EditStatus.PENDING for v in views)
    result = decide.accept(world, views[0].id)
    assert [i.code for i in result.issues] == [IssueCode.DOCUMENT_OBSOLETE]


def test_w14_reingestion_while_obsolete_produces_nothing(world):
    world.apply(obsolete(True, "e103"))
    report = ingest(world, "b8-bis", B8, ORACLE)
    assert report.obsolete == ["vieilles-notes"] and report.proposals == []


def test_w14_lifting_reactivates_blocked_proposals_as_they_were(world):
    world.apply(obsolete(True, "e103"))
    world.apply(obsolete(False, "e104"))
    views = proposals(world, "b8")
    assert len(views) == 2 and not any(v.blocked for v in views)
    assert decide.refuse(world, views[0].id).ok
    report = ingest(world, "b8-ter", B8, ORACLE)  # rien de neuf : les passages sont connus
    assert report.unchanged == 2 and report.proposals == []


def test_w14_refusing_stays_possible_while_blocked(world):
    world.apply(obsolete(True, "e103"))
    assert decide.refuse(world, proposals(world, "b8")[0].id).ok


def test_w14_curation_rules_R_EDI_09(world):
    mixed = edit({"op": "set_document_obsolete", "document": "vieilles-notes", "value": True},
                 {"op": "set_attribute", "entity": "odon", "attribute": "title", "value": "x"}, origin="curation")
    assert world.apply(mixed).status is None
    assert world.apply(edit({"op": "set_document_obsolete", "document": "vieilles-notes", "value": True})).status is None
