"""Parcours W06 (affirmations de la Chronique) et W07 (valeurs multiples, marqueur, indice) — J3.3.

R-DOC-06, R-DOC-07, R-DOC-08, R-NOT-02, R-NOT-05, R-FAI-05, R-DEC-01, T-ING-12, T-ING-15.
"""

from __future__ import annotations

import pytest

from support import VALMONT, base_world, read_yaml
from worldkit.core.journal.models import EditStatus
from worldkit.core.views import Filter, View
from worldkit.ingest import decide
from worldkit.ingest.batch import batch_documents, ingest
from worldkit.ingest.queue import load
from worldkit.periphery.extraction import OracleExtractor

ORACLE = OracleExtractor(VALMONT / "gold")
CHRONICLE = "b2.chronique-de-la-chute-extraits"


def docs(batch):
    return batch_documents(VALMONT / "docs" / "batches.yaml", batch)


@pytest.fixture
def b2():
    w = base_world()
    ingest(w, "b2", docs("b2"), ORACLE)
    yield w
    w.close()


def claims(world):
    return {p.id: p for p in load(world) if p.kind == "claim"}


def test_w06_ingestion_creates_no_fact_only_public_claims_R_DOC_06_R_NOT_05(b2):
    before = b2.state()
    found = claims(b2)
    assert len(found) == 9 and len(load(b2)) == 9
    assert {p.changes[0].change.op for p in found.values()} == {"add_claim"}
    assert {p.changes[0].change.visibility for p in found.values()} == {"public"}
    assert {p.changes[0].change.speaker for p in found.values()} == {"chronique-de-la-chute"}
    assert b2.state().facts == before.facts


def test_w06_suggestions_match_the_gold_T_ING_12(b2):
    gold = read_yaml(VALMONT / "gold" / "b2-chronique-de-la-chute.yaml")
    expected = {c["text"]: str(c["suggested"]).lower() for p in gold["passages"] for c in p.get("claims", [])}
    got = {p.changes[0].change.text: p.changes[0].detail["suggested"] for p in claims(b2).values()}
    assert got == expected


@pytest.fixture
def qualified(b2):
    w = b2
    ids = {p.changes[0].change.text: p.id for p in claims(w).values()}
    for text, value in [("Aldren est mort en combattant les pillards de Cendrelande.", "false"),
                        ("La Chute a eu lieu en l'an 1492.", "true"),
                        ("Mervin règne sur Valmont.", "true"),
                        ("Corvin est mort dans l'incendie du palais.", "false"),
                        ("Le Loup de cendre hante les plaines de Cendrelande.", "true"),
                        ("La Chronique a été commandée par le roi Mervin.", "true")]:
        assert decide.qualify(w, ids[text], value).ok
    assert decide.promote(w, ids["La Chronique a été achevée en l'an 1493."], visibility="public").ok
    return w, ids


def test_w06_promotion_combines_qualification_and_fact_R_DOC_07(qualified):
    w, ids = qualified
    pid = ids["La Chronique a été achevée en l'an 1493."]
    derived = w.store.edit(f"{pid}.d").edit
    assert [c.op for c in derived.changes] == ["add_claim", "qualify_claim", "set_attribute"]
    fact = w.state().facts[("attr", "chronique-de-la-chute", "date")]
    assert (fact.value, fact.visibility) == ("an 1493", "public")


def test_w06_player_sees_claims_but_not_their_qualifications_R_DOC_07(qualified):
    w, _ = qualified
    state = w.state()
    player = View(state, Filter.PLAYER).page("chronique-de-la-chute")
    author = View(state, Filter.AUTHOR).page("chronique-de-la-chute")
    assert len(player.claims) == 7 and all(c.qualification is None for c in player.claims)
    by_text = {c.text: c for c in author.claims}
    assert by_text["Aldren est mort en combattant les pillards de Cendrelande."].qualification == "false"
    assert by_text["Aldren est mort en combattant les pillards de Cendrelande."].qualification_visibility == "unqualified"


def test_w06_claims_and_facts_coexist_R_DOC_08(qualified):
    w, _ = qualified
    assert w.state().facts[("attr", "aldren-ii", "death_cause")].value == "poison"


def test_w06_variant_public_qualification_reveals_the_error_not_the_truth(qualified):
    w, ids = qualified
    corvin = w.state().claims  # l'affirmation est dans l'état
    cid = next(c for c, v in corvin.items() if v["text"].startswith("Corvin est mort"))
    assert decide.qualify(w, cid, "false", visibility="public").ok
    state = w.state()
    player = View(state, Filter.PLAYER)
    line = next(c for c in player.page("chronique-de-la-chute").claims if c.claim == cid)
    assert line.qualification == "false"
    assert player.page("corvin").identities == []  # rien ne révèle Frère Cendre


def test_w06_unqualified_claims_stay_pending(qualified):
    w, _ = qualified
    left = {p.changes[0].change.text for p in claims(w).values()}
    assert left == {"Mervin fut couronné par le conseil du royaume et règne avec sagesse.",
                    "Le Loup est né des cendres du roi."}


# --- W07 : les Veilleurs ---

@pytest.fixture
def b3():
    w = base_world()
    ingest(w, "b3", docs("b3"), ORACLE)
    for p in load(w):
        if p.kind != "claim":
            assert decide.accept(w, p.id).ok
    yield w
    w.close()


def test_w07_poverty_vow_is_an_enrichment_without_collision_R_FAI_05(b3):
    vows = {v for (tag, e, a, v) in (k for k in b3.state().occupancy if k[0] == "value") if e == "veilleurs"}
    assert vows == {"silence", "pauvreté"}


def test_w07_marker_segment_produces_a_chronicle_claim_R_DEC_01(b3):
    [claim] = [p for p in load(b3) if p.kind == "claim"]
    c = claim.changes[0].change
    assert (c.speaker, c.text) == ("chronique-de-la-chute", "Les Veilleurs ont juré fidélité au roi Mervin.")
    assert claim.passage == 4 and not any(p.passage == 4 and p.kind == "facts" for p in load(b3, status=None))


def test_w07_hint_makes_the_heart_origin_secret_T_ING_15(b3):
    fact = b3.state().facts[("attr", "coeur-de-braise", "origin")]
    assert fact.visibility == "secret"


def test_w07_player_sees_silence_but_not_poverty(b3):
    page = View(b3.state(), Filter.PLAYER).page("veilleurs")
    assert {(a.name, a.value) for a in page.attributes if a.name == "vows"} == {("vows", "silence")}
    assert load(b3, status=EditStatus.PENDING)  # l'affirmation balisée attend sa qualification
