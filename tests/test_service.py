"""Jalon I1 : couche de service, exécutions, bacs à sable (cadre d'interface §7, §8).

I-PRI-02, I-PRI-03, I-PRI-05, I-PRI-07 ; I-SBX-01, I-RUN-01, I-CLI-01 ; décisions I1 (registre d'opérations,
sortes enregistrées, ligne de commande générique et dédiée, bacs à plat dans un seul runs.db).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from support import VALMONT, base_edits
from worldkit.core.journal.models import parse_edit
from worldkit.core.projection.serialize import state_to_json
from worldkit.core.world import World
from worldkit.service import REGISTRY, Result, Session

BATCHES = str(VALMONT / "docs" / "batches.yaml")
GOLD = str(VALMONT / "gold")


def make_world(path: Path) -> Path:
    w = World.create(path, VALMONT / "world.yaml")
    for raw in base_edits():
        assert w.apply(parse_edit(raw)).ok
    w.set_point("@base")
    w.close()
    return path


def edit(eid: str, *changes: dict) -> dict:
    return {"edit": {"id": eid, "origin": "enrichment", "changes": list(changes)}}


def cond(entity: str, value: str) -> dict:
    return {"op": "set_attribute", "entity": entity, "attribute": "condition", "value": value}


@pytest.fixture
def session(tmp_path):
    s = Session(make_world(tmp_path / "valmont.db"))
    yield s
    s.close()


def snapshot(db: Path) -> list[str]:
    """Tout état de toute branche, rang par rang (R-HIS-04)."""
    w = World.open(db)
    try:
        return [state_to_json(w.state(b, s)) for b in w.store.branches() for s in range(w.store.head_seq(b) + 1)]
    finally:
        w.close()


# --- Forme commune d'un résultat (§7) ---

def test_every_operation_declares_kind_params_and_summary():
    assert {op.kind for op in REGISTRY.values()} <= {"read", "compute", "write", "admin"}
    assert all(op.summary for op in REGISTRY.values())
    assert {"world.summary", "wiki.page", "edit.check", "edit.apply", "ingest.batch", "sandbox.create",
            "runs.list"} <= set(REGISTRY)


def test_result_is_canonical_json_and_reads_are_deterministic_I_PRI_05(session):
    for name, params in (("world.summary", {}), ("wiki.page", {"entity": "aldren-ii", "filter": "player"}),
                         ("export.graph", {"filter": "player"}), ("branch.list", {})):
        a, b = session.call(name, params), session.call(name, params)
        assert a.status == "ok" and a.stable() == b.stable()
        assert Result.model_validate_json(a.to_json()).stable() == a.stable()
        assert json.loads(a.to_json()) == json.loads(a.to_json(None))


def test_player_page_hides_secrets_the_service_filters_not_the_interface_I_PRI_02(session):
    page = session.call("wiki.page", {"entity": "aldren-ii", "filter": "player"}).output
    assert "poison" not in page["markdown"] and "poison" in session.call(
        "wiki.page", {"entity": "aldren-ii"}).output["markdown"]


def test_invalid_params_are_refused_with_an_explicit_message(session):
    r = session.call("edit.apply", {**edit("x1", cond("odon", "las")), "bogus": 1})
    assert r.status == "error" and r.issues[0].code == "invalid_params" and "bogus" in r.issues[0].message
    r = session.call("wiki.page", {})
    assert r.status == "error" and "entity" in r.issues[0].message
    with pytest.raises(KeyError):
        session.call("nope.nope")


def test_edit_check_writes_nothing_and_cites_the_rule_R_FAI_05(session):
    before = snapshot(session.db)
    ok = session.call("edit.check", edit("x1", cond("odon", "las")))
    assert ok.status == "ok" and ok.output["applicable"] and ok.output["diff"]["added"][0]["value"] == "las"
    collision = session.call("edit.check", edit("x2", {"op": "add_relation", "from": "mervin", "relation": "rules",
                                                        "to": "brume"}))
    assert collision.status == "refused" and [(i.code, i.rule) for i in collision.issues] == [("key_collision", "R-FAI-05")]
    assert snapshot(session.db) == before


# --- Exécutions (I-RUN-01, décision I1) ---

def test_reads_are_not_recorded_unless_pinned_compute_write_admin_are(session):
    session.call("world.summary")
    assert session.runs.runs() == []
    session.call("world.summary", record=True)
    session.call("edit.check", edit("x1", cond("odon", "las")))
    session.call("edit.apply", edit("x1", cond("odon", "las")))
    session.call("sandbox.create")
    kinds = [(r.operation, r.kind) for r in reversed(session.runs.runs())]
    assert kinds == [("world.summary", "read"), ("edit.check", "compute"), ("edit.apply", "write"),
                     ("sandbox.create", "admin")]


def test_a_recorded_run_reads_back_identically(session):
    r = session.call("edit.check", edit("x1", cond("odon", "las")))
    stored = session.runs.result(r.trace.run_id)
    assert stored.stable() == r.stable() and stored.trace.run_id == r.trace.run_id
    assert session.call("runs.show", {"id": r.trace.run_id}).output["operation"] == "edit.check"


def test_purging_runs_does_not_touch_the_world(session):
    session.call("edit.apply", edit("x1", cond("odon", "las")))
    session.call("edit.check", edit("x2", cond("isabeau", "las")))
    before = snapshot(session.db)
    assert session.call("runs.purge", {"all": True}).output["purged"] == 2
    assert snapshot(session.db) == before
    assert [r.operation for r in session.runs.runs()] == ["runs.purge"]
    assert session.call("runs.purge", {}).status == "error"


# --- Bacs à sable (I-SBX-01, décision I1) ---

def test_writes_in_a_sandbox_never_touch_the_working_world_T1(session):
    before = snapshot(session.db)
    box = session.call("sandbox.create", {"note": "bestiaire"}).output
    assert box["heads"] == {"reference": 7} and box["origin"] == "world"
    assert session.call("edit.apply", edit("x1", cond("odon", "las")), target=1).status == "ok"
    ingested = session.call("ingest.batch", {"batch_id": "b4", "batches": BATCHES, "oracle": GOLD}, target=1)
    assert ingested.indicators["proposals"] == 3 and ingested.indicators["flags"] == {"attribution": 1,
                                                                                       "nature_detected": 1}
    assert session.call("review.nature", {"document": "bestiaire-loup-de-cendre", "passage": 6,
                                          "decision": "accept"}, target=1).status == "ok"
    assert session.call("review.accept", {"proposals": ["b4.bestiaire-loup-de-cendre.p6.1"]}, target=1).status == "ok"
    assert snapshot(session.db) == before
    sandboxed = session.call("wiki.page", {"entity": "loup-de-cendre"}, target=1).output["markdown"]
    working = session.call("wiki.page", {"entity": "loup-de-cendre"}).output["markdown"]
    assert "system-b (Monster)" in sandboxed and "system-b" not in working


def test_a_sandbox_can_be_duplicated_and_dropped_its_runs_remain(session):
    session.call("sandbox.create")
    session.call("edit.apply", edit("x1", cond("odon", "las")), target=1)
    dup = session.call("sandbox.create", {"origin": "1"}).output
    assert dup["origin"] == "sandbox:1" and dup["heads"] == {"reference": 8}
    assert session.call("journal.list", {"limit": 1}, target=2).output["entries"][0]["edit"] == "x1"
    dropped = session.call("sandbox.drop", {"id": 1}).output
    assert dropped["status"] == "dropped" and not Path(dropped["file"]).exists()
    assert [r.target for r in session.runs.runs(operation="edit.apply")] == ["sandbox:1"]
    refused = session.call("world.summary", target=1)
    assert refused.status == "error" and "jeté" in refused.issues[0].message
    assert [b.id for b in session.runs.sandboxes()] == [2]


@settings(max_examples=8, deadline=None, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])
@given(st.lists(st.tuples(st.sampled_from(["odon", "isabeau", "corvin", "mervin"]),
                          st.text(alphabet="abcde", min_size=1, max_size=4)), min_size=1, max_size=4))
def test_any_sequence_of_sandbox_writes_leaves_the_world_identical_T1(tmp_path_factory, writes):
    db = make_world(tmp_path_factory.mktemp("w") / "valmont.db")
    before = snapshot(db)
    with Session(db) as s:
        s.call("sandbox.create")
        for i, (who, value) in enumerate(writes):
            s.call("edit.apply", edit(f"h{i}", cond(who, value)), target=1)
    assert snapshot(db) == before


# --- Ligne de commande (I-CLI-01, décision I1) ---

def test_cli_ops_call_sandbox_runs(tmp_path, capsys):
    from worldkit.cli import main
    db = make_world(tmp_path / "valmont.db")
    run = lambda *a: main(["--db", str(db), *a])
    assert run("ops") == 0
    assert "edit.check" in capsys.readouterr().out
    assert run("call", "wiki.page", "--param", "entity=aldren-ii", "--param", "filter=player") == 0
    assert "# Aldren II" in capsys.readouterr().out
    params = tmp_path / "e.yaml"
    params.write_text("edit:\n  id: x1\n  origin: enrichment\n  changes:\n"
                      "    - { op: set_attribute, entity: odon, attribute: condition, value: las }\n", encoding="utf-8")
    assert run("sandbox", "create", "--note", "essai") == 0
    assert "sandbox.create [admin]" in capsys.readouterr().out
    assert run("call", "edit.apply", str(params), "--sandbox", "1", "--json") == 0
    out = json.loads(capsys.readouterr().out)
    assert (out["status"], out["target"], out["output"]["seq"]) == ("ok", "sandbox:1", 8)
    assert run("call", "edit.check", "--param", "edit.id=x9", "--param", "edit.origin=enrichment",
               "--param", "edit.changes=[{op: set_attribute, entity: odon, attribute: title, value: régent}]") == 0
    assert "edit.check [compute] → world : ok" in capsys.readouterr().out  # set_attribute remplace : pas de collision
    assert run("sandbox", "list") == 0
    assert "bac 1 [active] depuis world" in capsys.readouterr().out
    assert run("runs", "list") == 0
    listed = capsys.readouterr().out
    assert "edit.apply" in listed and "sandbox:1" in listed
    assert run("runs", "show", "2") == 0
    assert "edit.apply [write] → sandbox:1 : ok" in capsys.readouterr().out
    assert run("sandbox", "drop", "1") == 0
    assert run("runs", "purge", "--all") == 0
