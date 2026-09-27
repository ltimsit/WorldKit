"""Parcours d'acceptation exécutables (cadre d'interface I-ACC-01 ; décisions I5).

pytest et l'interface appellent le même exécuteur (`walkthrough.run`) : W15 et W08 sont exécutés avec leurs
chaînes de prérequis, dans un monde d'acceptation neuf, et chacun de leurs attendus est vérifié.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from support import CORPUS
from test_service import make_world
from worldkit.service import Session
from worldkit.service.walkthroughs import chain_of, load_walkthroughs


@pytest.fixture(scope="module")
def session(tmp_path_factory):
    s = Session(make_world(tmp_path_factory.mktemp("acc") / "valmont.db"))
    yield s
    s.close()


def failures(result):
    target = result.output["results"][-1]
    return [(e["text"], c["detail"]) for e in target["expects"] for c in e["checks"] if not c["ok"]]


@pytest.mark.parametrize("wid, expects", [("W15", 6), ("W08", 4)])
def test_walkthrough_passes_every_structured_expectation_I_ACC_01(session, wid, expects):
    r = session.call("walkthrough.run", {"id": wid})
    assert failures(r) == [] and r.status == "ok"
    assert r.indicators["passed"] == expects and r.indicators["unstructured"] == 0
    assert r.indicators["broken_steps"] == 0
    assert all(res["steps_ok"] for res in r.output["results"])


def test_the_w15_chain_replays_the_whole_reference_story():
    wts = load_walkthroughs()
    assert chain_of(wts, "W15") == ["W01", "W02", "W03", "W04", "W05", "W06", "W07", "W08", "W09", "W10", "W11",
                                    "W12", "W13", "W15"]
    assert chain_of(wts, "W08")[-1] == "W08" and "W09" not in chain_of(wts, "W08")


def test_a_falsified_expectation_fails_explicitly(tmp_path, session):
    corpus = tmp_path / "corpus"
    shutil.copytree(CORPUS, corpus)
    path = corpus / "valmont" / "walkthroughs" / "walkthroughs.yaml"
    text = path.read_text(encoding="utf-8")
    path.write_text(text.replace("id: [attr, loup-de-cendre@system-b, level], value: 7",
                                 "id: [attr, loup-de-cendre@system-b, level], value: 9"), encoding="utf-8")
    r = session.call("walkthrough.run", {"id": "W08", "corpus": str(corpus)})
    assert r.status == "refused" and r.indicators["failed"] == 1
    assert failures(r) == [(failures(r)[0][0], "valeur 7, attendu 9")]


def test_prerequisite_cycles_are_refused():
    wts = {"A": {"id": "A", "requires": ["B"]}, "B": {"id": "B", "requires": ["A"]}}
    with pytest.raises(ValueError):
        chain_of(wts, "A")


def test_an_acceptance_world_is_browsable_but_never_promoted(session):
    r = session.call("walkthrough.run", {"id": "W08"})
    box = r.output["sandbox"]
    assert session.call("wiki.page", {"entity": "loup-de-cendre"}, box).status == "ok"
    refused = session.call("sandbox.promote", {"id": box})
    assert refused.status == "error" and "acceptation" in refused.issues[0].message


def test_walkthrough_list_reports_what_is_executable_and_structured(session):
    r = session.call("walkthrough.list")
    rows = {w["id"]: w for w in r.output}
    assert rows["W15"]["structured"] == 6 and rows["W08"]["structured"] == 4
    assert all(rows[w]["executable"] for w in ["W01", "W05", "W06", "W09", "W10", "W11", "W12", "W13", "W15"])
    assert rows["W15"]["requires"] == ["W13"]


def test_corpus_check_accepts_the_new_format():
    import subprocess
    import sys
    out = subprocess.run([sys.executable, "tools/check_corpus.py"], cwd=CORPUS, capture_output=True, text=True,
                         encoding="utf-8", errors="replace")
    assert out.returncode == 0 and "W08, W15" in out.stdout


def test_cli_walkthrough_list_and_run(tmp_path, capsys):
    from worldkit.cli import main
    db = make_world(tmp_path / "valmont.db")
    assert main(["--db", str(db), "walkthrough", "list"]) == 0
    assert "W15" in capsys.readouterr().out
    assert main(["--db", str(db), "walkthrough", "run", "W08"]) == 0
    out = capsys.readouterr().out
    assert "W08 : ok" in out and out.count("[réussi ]") == 4 and "ÉCHOUÉ" not in out


@pytest.mark.parametrize("wid", ["W00", "W16", "W17"])
def test_the_other_walkthroughs_execute_every_step(session, wid):
    """Leurs attendus restent en prose (à structurer plus tard, I-ACC-01) ; leurs étapes s'exécutent."""
    r = session.call("walkthrough.run", {"id": wid, "keep": False})
    assert all(res["steps_ok"] for res in r.output["results"]), [
        (res["id"], st["detail"]) for res in r.output["results"] for st in res["steps"] if not st["ok"]]
