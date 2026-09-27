"""Jalon I3 : saisie, banc de mécanismes, rendre réel un essai (cadre d'interface I-SAI-01, I-SBX-01, I-VUE-04).

Décisions I3 : écriture dans un bac par défaut, le monde exigeant une confirmation ; rendre réel = répétition à
blanc puis application en tout ou rien ; banc = console générique sur le registre.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from support import VALMONT
from test_service import cond, edit, make_world, snapshot
from worldkit.core.projection.serialize import state_to_json
from worldkit.core.world import World
from worldkit.service import REGISTRY, Session, describe

BATCHES = str(VALMONT / "docs" / "batches.yaml")
GOLD = str(VALMONT / "gold")


@pytest.fixture
def session(tmp_path):
    s = Session(make_world(tmp_path / "valmont.db"))
    yield s
    s.close()


def head(db: Path) -> str:
    w = World.open(db)
    try:
        return state_to_json(w.state())
    finally:
        w.close()


# --- Rendre réel (I-SBX-01) ---

def fill(s: Session, n: int) -> None:
    s.call("edit.apply", edit("x1", cond("odon", "las")), n)
    s.call("ingest.batch", {"batch_id": "b4", "batches": BATCHES, "oracle": GOLD}, n)
    s.call("review.nature", {"document": "bestiaire-loup-de-cendre", "passage": 6, "decision": "accept"}, n)
    s.call("review.accept", {"proposals": ["b4.bestiaire-loup-de-cendre.p6.1"]}, n)


def test_rehearsal_writes_nothing_and_waits_for_confirmation_T1(session):
    n = session.call("sandbox.create").output["id"]
    fill(session, n)
    before = snapshot(session.db)
    r = session.call("sandbox.promote", {"id": n})
    assert r.status == "pending" and [s["verdict"] for s in r.output["steps"]] == ["same"] * 4
    assert snapshot(session.db) == before
    assert session.runs.sandbox(n).status == "active"


def test_confirmed_promotion_makes_the_world_equal_to_the_sandbox_T1(session):
    n = session.call("sandbox.create").output["id"]
    fill(session, n)
    r = session.call("sandbox.promote", {"id": n, "confirm": True})
    assert r.status == "ok" and len(r.output["applied"]) == 4
    assert head(session.db) == head(Path(session.runs.sandbox(n).file))
    assert session.runs.sandbox(n).status == "promoted"
    assert session.call("world.summary", target=n).status == "error"  # un bac rendu réel n'est plus une cible
    assert [x.target for x in session.runs.runs(operation="edit.apply")][:1] == ["world"]


def test_a_divergence_blocks_everything_all_or_nothing_T1(session):
    n = session.call("sandbox.create").output["id"]
    session.call("edit.apply", edit("x1", cond("isabeau", "lasse")), n)
    session.call("edit.apply", edit("x2", cond("corvin", "las")), n)
    session.call("edit.apply", edit("x2", cond("mervin", "autre")))  # le monde a avancé : même identifiant
    before = snapshot(session.db)
    r = session.call("sandbox.promote", {"id": n, "confirm": True})
    assert r.status == "refused" and [s["verdict"] for s in r.output["steps"]] == ["gap", "divergence"]
    assert "R-CYC-01" in r.output["steps"][1]["detail"] and r.output["applied"] == []
    assert snapshot(session.db) == before  # pas même x1, pourtant identique : tout ou rien


def test_a_moved_rank_is_a_gap_not_a_divergence(session):
    n = session.call("sandbox.create").output["id"]
    session.call("edit.apply", edit("x1", cond("isabeau", "lasse")), n)
    session.call("edit.apply", edit("w1", cond("corvin", "las")))  # indépendante, mais décale les rangs
    r = session.call("sandbox.promote", {"id": n})
    assert r.status == "pending" and r.output["steps"][0]["verdict"] == "gap" and "seq" in r.output["steps"][0]["detail"]


def test_a_duplicated_sandbox_promotes_the_whole_chain(session):
    a = session.call("sandbox.create").output["id"]
    session.call("edit.apply", edit("x1", cond("isabeau", "lasse")), a)
    b = session.call("sandbox.create", {"origin": str(a)}).output["id"]
    session.call("edit.apply", edit("x2", cond("corvin", "las")), b)
    session.call("edit.apply", edit("x3", cond("odon", "gris")), a)  # après la copie : pas dans la chaîne de b
    r = session.call("sandbox.promote", {"id": b, "confirm": True})
    assert r.output["chain"] == [a, b] and [s["params"]["edit"]["id"] for s in r.output["steps"]] == ["x1", "x2"]
    state = World.open(session.db)
    try:
        facts = state.state().facts
        assert facts[("attr", "isabeau", "condition")].value == "lasse" and ("attr", "odon", "condition") not in facts
    finally:
        state.close()


def test_cli_sandbox_promote(tmp_path, capsys):
    from worldkit.cli import main
    db = make_world(tmp_path / "valmont.db")
    with Session(db) as s:
        n = s.call("sandbox.create").output["id"]
        s.call("edit.apply", edit("x1", cond("odon", "las")), n)
    run = lambda *a: main(["--db", str(db), *a])
    assert run("sandbox", "promote", str(n)) == 0
    out = capsys.readouterr().out
    assert "identique" in out and "--yes" in out
    assert run("sandbox", "promote", str(n), "--yes") == 0
    assert "appliquée" in capsys.readouterr().out


# --- Mécanismes du catalogue (§3) ---

def test_new_compute_operations_on_valmont(session):
    keys = session.call("change.keys", REGISTRY["change.keys"].example)
    assert keys.status == "ok" and keys.output["readable"] == ["(rules, brume)"]
    assert keys.output["occupied_by"]["(rules, brume)"] == ["rel", "odon", "rules", "brume"]
    schema = session.call("schema.validate", {"file": str(VALMONT / "systems" / "system-a.yaml")})
    assert schema.output["valid"]
    bad = session.call("schema.validate", {"schema": {"schema": "x", "kind": "world", "types": {"Truc": {"extends": "Rien"}}}})
    assert bad.status == "refused" and bad.issues
    doc = session.call("document.declare", REGISTRY["document.declare"].example)
    assert doc.indicators["natures"] == {"undetermined": 4, "meta": 2}
    impact = session.call("redefine.preview", REGISTRY["redefine.preview"].example)
    assert impact.output["anchor_seq"] == 4 and impact.indicators["later"] == 3


def test_transpose_analyse_says_contradictory(session):
    session.call("sandbox.create")
    world = World.open(session.db)
    world.create_branch("variante-mj", point="@base")
    world.close()
    session.call("edit.apply", {"edit": {"id": "e201", "origin": "redefinition", "redefinition": "point",
                                         "branch": "variante-mj", "changes": [
                                             {"op": "remove_relation", "from": "odon", "relation": "rules", "to": "brume"},
                                             {"op": "add_relation", "from": "mervin", "relation": "rules", "to": "brume"}]}})
    r = session.call("transpose.analyse", {"edit": "e201", "to": "reference"})
    assert r.status == "ok" and r.indicators["relation"] in ("contradictory", "independent", "dependent")
    assert all("text" in d for d in r.output["divergences"])


def test_every_operation_offers_initial_params_for_the_bench():
    for op in REGISTRY.values():
        d = describe(op)
        assert op.example is not None or isinstance(d["template"], dict), op.name


# --- Interface (I-SAI-01, décision I3) ---

fastapi = pytest.importorskip("fastapi")


@pytest.fixture
def client(tmp_path):
    from fastapi.testclient import TestClient
    from worldkit.web import create_app
    db = make_world(tmp_path / "valmont.db")
    return TestClient(create_app(db)), db


DRAFT = ("id: x1\norigin: enrichment\nchanges:\n"
         "  - { op: set_attribute, entity: odon, attribute: condition, value: Harasse }\n"
         "  - { op: add_relation, from: mervin, relation: rules, to: brume }\n")


def test_live_check_ties_the_collision_to_its_line_and_writes_nothing(client):
    c, db = client
    before = snapshot(db)
    r = c.post("/fragments/check", data={"yaml": DRAFT, "destination": "new"})
    assert "R-FAI-05" in r.text and re.search(r"changes\[1\]</code> → ligne 5", r.text)
    assert snapshot(db) == before


def test_editor_writes_to_a_new_sandbox_by_default_and_refuses_the_world_unconfirmed(client):
    c, db = client
    before = snapshot(db)
    ok = DRAFT.split("  - { op: add_relation")[0]
    r = c.post("/editor", data={"yaml": ok, "destination": "new", "action": "apply"})
    assert "Écrit dans le" in r.text and "bac 1" in r.text
    r = c.post("/editor", data={"yaml": ok.replace("x1", "x2"), "destination": "world", "action": "apply"})
    assert "confirmation" in r.text
    assert snapshot(db) == before
    r = c.post("/editor", data={"yaml": ok.replace("x1", "x3"), "destination": "world", "confirm_world": "1",
                                "action": "apply"})
    assert snapshot(db) != before


def test_api_write_to_the_world_needs_confirmation(client):
    c, db = client
    body = {"params": {"edit": {"id": "z1", "origin": "enrichment", "changes": [cond("odon", "las")]}}}
    assert c.post("/api/call/edit.apply", json=body).status_code == 409
    assert c.post("/api/call/edit.apply", json={**body, "confirm_world": True}).status_code == 200
    assert c.post("/api/call/change.keys", json={"params": REGISTRY["change.keys"].example}).status_code == 200


def test_bench_runs_any_operation_and_replays_it(client):
    c, _ = client
    assert c.get("/bench?op=document.declare").status_code == 200
    params = "change: {op: add_relation, from: odon, relation: rules, to: brume}\n"
    r = c.post("/bench", data={"op": "change.keys", "params": params, "destination": ""})
    run_id = re.search(r'name="compare_to" value="(\d+)"', r.text).group(1)
    r = c.post("/bench", data={"op": "change.keys", "params": params, "destination": "", "compare_to": run_id})
    assert "identique" in r.text


def test_promote_page_rehearses_then_applies_on_confirmation(client):
    c, db = client
    with Session(db) as s:
        n = s.call("sandbox.create").output["id"]
        s.call("edit.apply", edit("x1", cond("odon", "las")), n)
    before = snapshot(db)
    assert "Appliquer au monde de travail" in c.get(f"/sandbox/{n}/promote").text
    assert "cocher la confirmation" in c.post(f"/sandbox/{n}/promote", data={}).text
    assert snapshot(db) == before
    assert "Appliqué au monde de travail" in c.post(f"/sandbox/{n}/promote", data={"confirm_world": "1"}).text


def test_aldren_retcon_in_a_sandbox_then_made_real_W15(tmp_path):
    """Test humain d'I3, automatisé : retcon d'Aldren dans un bac, vérifié, puis rendu réel."""
    from test_w15_replay import file_world
    db = tmp_path / "valmont.db"
    file_world(db).close()
    with Session(db) as s:
        n = s.call("sandbox.create").output["id"]
        started = s.call("replay.start", REGISTRY["replay.start"].example, n)
        assert started.status == "pending" and started.output["conflict"]["relation"] == "contradictory"
        assert s.call("replay.status", {"id": "r1"}, n).output["current"] == started.output["current"]
        done = s.call("replay.decide", {"id": "r1", "action": "keep"}, n)
        assert done.output["replay"]["status"] == "finished"
        before = snapshot(db)
        assert s.call("sandbox.promote", {"id": n}).status == "pending" and snapshot(db) == before
        assert s.call("sandbox.promote", {"id": n, "confirm": True}).status == "ok"
    w = World.open(db)
    try:
        assert w.reference_branch == "reference-r1"
        assert w.state().facts[("attr", "aldren-ii", "death_cause")].value == "fièvre"
        assert w.store.branch_status("reference") == "archived"
    finally:
        w.close()
