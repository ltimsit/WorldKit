"""Accès en ligne de commande à la couche de service (I-CLI-01, décision I1 : générique + dédiées).

    worldkit --db monde.db ops
    worldkit --db monde.db call <opération> [paramètres.yaml] [--param clé=valeur]… [--sandbox N] [--pin] [--json]
    worldkit --db monde.db sandbox create [--from N] [--note …] | list [--all] | drop N
    worldkit --db monde.db runs list [--limit N] [--target …] [--operation …] | show N | purge (N… | --before N | --all)

Sous PowerShell, les paramètres passent par un fichier YAML ou par des paires `clé=valeur` (la valeur est
lue en YAML : `passage=6`, `all=true` ; `edit.id=x1` construit un dictionnaire imbriqué), jamais par du
JSON en argument, dont les guillemets seraient mangés.
"""

from __future__ import annotations

import argparse
import json
from typing import Any

import yaml

from worldkit.core.schema import read_yaml

from .result import Result


def add_parsers(commands: Any) -> None:
    commands.add_parser("ops", help="opérations du service : sorte, résumé, paramètres (I-CLI-01)")
    call = commands.add_parser("call", help="appeler une opération du service")
    call.add_argument("operation")
    call.add_argument("file", nargs="?", default=None, help="paramètres en YAML")
    call.add_argument("--param", action="append", default=[], metavar="CLÉ=VALEUR")
    call.add_argument("--sandbox", default=None, help="numéro du bac à sable visé (défaut : le monde)")
    call.add_argument("--pin", action="store_true", help="enregistrer même une consultation")
    call.add_argument("--json", action="store_true", help="le résultat complet, en JSON")

    sb = commands.add_parser("sandbox", help="bacs à sable (I-SBX-01)")
    sb_cmds = sb.add_subparsers(dest="sandbox_command", required=True)
    create = sb_cmds.add_parser("create")
    create.add_argument("--from", dest="origin", default="world", help="world, ou le numéro d'un bac à dupliquer")
    create.add_argument("--note", default=None)
    sb_cmds.add_parser("list").add_argument("--all", action="store_true")
    sb_cmds.add_parser("drop").add_argument("id", type=int)
    promote = sb_cmds.add_parser("promote", help="rendre réel : répétition à blanc, puis --yes pour appliquer")
    promote.add_argument("id", type=int)
    promote.add_argument("--yes", action="store_true", help="appliquer au monde de travail si rien ne diverge")

    rn = commands.add_parser("runs", help="exécutions enregistrées (I-RUN-01)")
    rn_cmds = rn.add_subparsers(dest="runs_command", required=True)
    lst = rn_cmds.add_parser("list")
    lst.add_argument("--limit", type=int, default=20)
    lst.add_argument("--target", default=None)
    lst.add_argument("--operation", default=None)
    show = rn_cmds.add_parser("show")
    show.add_argument("id", type=int)
    show.add_argument("--json", action="store_true")
    purge = rn_cmds.add_parser("purge")
    purge.add_argument("ids", nargs="*", type=int)
    purge.add_argument("--before", type=int, default=None)
    purge.add_argument("--all", action="store_true")


def parse_params(file: str | None, pairs: list[str]) -> dict[str, Any]:
    params: dict[str, Any] = dict(read_yaml(file) or {}) if file else {}
    for pair in pairs:
        key, sep, value = pair.partition("=")
        if not sep:
            raise ValueError(f"paramètre sans « = » : {pair} (attendu clé=valeur)")
        node = params
        parts = key.split(".")
        for part in parts[:-1]:
            node = node.setdefault(part, {})
        node[parts[-1]] = yaml.safe_load(value) if value else ""
    return params


def show(result: Result, as_json: bool = False) -> int:
    if as_json:
        print(result.to_json())
        return 0 if result.ok else 1
    run = f", exécution #{result.trace.run_id}" if result.trace.run_id else ""
    print(f"{result.operation} [{result.kind}] → {result.target} : {result.status}"
          f" ({result.trace.duration_ms} ms{run})")
    for i in result.issues:
        where = f" {i.path}" if i.path else ""
        rule = f"[{i.rule}] " if i.rule else ""
        print(f"  - {i.severity} {rule}{i.code}{where} : {i.message}")
    if result.indicators:
        print("indicateurs :")
        for k, v in result.indicators.items():
            print(f"  {k} : {v}")
    out = result.output
    if isinstance(out, dict) and isinstance(out.get("markdown"), str):
        print(out["markdown"])
    elif out is not None:
        print("sortie :")
        print(yaml.safe_dump(out, allow_unicode=True, sort_keys=False, width=110).rstrip())
    return 0 if result.ok else 1


VERDICT_FR = {"same": "identique", "gap": "écart", "divergence": "DIVERGENCE", "ignored": "ignorée"}


def _promote(s: Any, sandbox_id: int, confirm: bool) -> int:
    result = s.call("sandbox.promote", {"id": sandbox_id, "confirm": confirm})
    out = result.output or {}
    run_id = f", exécution #{result.trace.run_id}" if result.trace.run_id else ""
    print(f"rendre réel le bac {sandbox_id} (chaîne {out.get('chain')}) : {result.status}{run_id}")
    for step in out.get("steps", []):
        detail = f" — {step['detail']}" if step.get("detail") else ""
        print(f"  #{step['run']} {step['operation']} ({step['from']}) : {VERDICT_FR[step['verdict']]}{detail}")
    if result.status == "pending":
        print("  répétition réussie : relancer avec --yes pour appliquer au monde de travail")
    elif result.status == "refused":
        print("  rien n'a été écrit : corriger dans un nouveau bac, depuis le monde à jour")
    for a in out.get("applied", []):
        print(f"  appliquée : #{a['from_run']} → exécution #{a['run']} ({a['status']})")
    for i in result.issues:
        if i.code in ("invalid_params", "service_error"):
            print(f"  - {i.severity} : {i.message}")
    return 0 if result.status in ("ok", "pending") else 1


def run(args: argparse.Namespace) -> int:
    from . import Session
    with Session(args.db) as s:
        if args.command == "ops":
            for op in s.call("ops.list").output:
                params = ", ".join(f"{k}{'' if v['required'] else '?'}" for k, v in op["params"].items())
                rules = f"  ({', '.join(op['rules'])})" if op["rules"] else ""
                print(f"{op['name']:<16} [{op['kind']}] {op['summary']}{rules}")
                if params:
                    print(f"{'':<16}   paramètres : {params}")
            return 0
        if args.command == "call":
            return show(s.call(args.operation, parse_params(args.file, args.param), args.sandbox,
                               True if args.pin else None), args.json)
        if args.command == "sandbox":
            if args.sandbox_command == "create":
                return show(s.call("sandbox.create", {"origin": args.origin, "note": args.note}))
            if args.sandbox_command == "list":
                result = s.call("sandbox.list", {"all": args.all})
                for b in result.output:
                    note = f" — {b['note']}" if b.get("note") else ""
                    print(f"bac {b['id']} [{b['status']}] depuis {b['origin']}, têtes {b['heads']}{note}")
                    print(f"    {b['file']}")
                if not result.output:
                    print("aucun bac à sable")
                return 0
            if args.sandbox_command == "promote":
                return _promote(s, args.id, args.yes)
            return show(s.call("sandbox.drop", {"id": args.id}))
        if args.runs_command == "list":
            result = s.call("runs.list", {"limit": args.limit, "target": args.target, "operation": args.operation})
            for r in result.output:
                print(f"#{r['id']:<4} {r['created']}  {r['operation']:<16} [{r['kind']}] → {r['target']} : {r['status']}")
            if not result.output:
                print("aucune exécution enregistrée")
            return 0
        if args.runs_command == "show":
            stored = s.call("runs.show", {"id": args.id})
            if not stored.ok:
                return show(stored)
            return show(Result.model_validate(stored.output), args.json)
        return show(s.call("runs.purge", {"ids": args.ids, "before": args.before, "all": args.all}))


# ---------------------------------------------------------------------------
# Pipeline en ligne de commande (I-CLI-01, décisions I4)
# ---------------------------------------------------------------------------

def add_pipeline_parsers(commands: Any) -> None:
    run = commands.add_parser("run", help="pipeline d'ingestion en étapes (I4)")
    run_cmds = run.add_subparsers(dest="run_command", required=True)
    st = run_cmds.add_parser("stages", help="étapes E1 à E9, de x à y, sans rien écrire (cache excepté)")
    st.add_argument("--batch-id", default=None, help="identifiant du lot (défaut : --batch)")
    st.add_argument("--batch", default=None, help="lot déclaré dans --batches")
    st.add_argument("--batches", default=None, help="batches.yaml")
    st.add_argument("documents", nargs="*", help="ou des documents")
    st.add_argument("--from", dest="first", default="E1")
    st.add_argument("--to", dest="last", default="E9")
    st.add_argument("--oracle", default=None, help="dossier gold/ (extracteur oracle)")
    st.add_argument("--profile", default=None, help="profil de modèle (extracteur LLM)")
    st.add_argument("--llm-config", default=None)
    st.add_argument("--input", type=int, default=None, help="exécution dont on reprend l'artefact")
    st.add_argument("--input-stage", default=None)
    st.add_argument("--artifact", default=None, help="artefact saisi (fichier YAML ou JSON)")
    st.add_argument("--max-calls", type=int, default=None)
    st.add_argument("--yes", action="store_true", help="confirmer les appels au modèle estimés")
    st.add_argument("--sandbox", default=None)
    st.add_argument("--json", action="store_true")
    sv = run_cmds.add_parser("save", help="enregistrer le lot d'une exécution (E9+), jusqu'à E12")
    sv.add_argument("input", type=int)
    sv.add_argument("--input-stage", default=None)
    sv.add_argument("--to", default="E9+")
    sv.add_argument("--decisions", default=None, help="décisions scriptées pour E10 (fichier YAML)")
    sv.add_argument("--sandbox", default=None, help="numéro du bac (défaut : le monde, comme les autres commandes)")
    sv.add_argument("--json", action="store_true")
    df = commands.add_parser("runs-diff", help="comparer deux exécutions de pipeline étape par étape")
    df.add_argument("a", type=int)
    df.add_argument("b", type=int)
    df.add_argument("--json", action="store_true")


def run_pipeline(args: argparse.Namespace) -> int:
    import threading
    from . import Session
    with Session(args.db) as s:
        if args.command == "runs-diff":
            result = s.call("runs.diff", {"a": args.a, "b": args.b})
            if args.json or not result.ok:
                return show(result, args.json)
            o = result.output
            print(f"#{o['a']} ↔ #{o['b']} : " + (f"première différence en {o['first_difference']}"
                                                   if o["first_difference"] else "identiques sur les étapes communes"))
            for st in o["stages"]:
                print(f"  {st['stage']:4} {'identique' if st['same'] else 'DIFFÉRENT'}"
                      f"  ({st['duration_ms']['a']} / {st['duration_ms']['b']} ms)")
                for k in st["only_a"]:
                    print(f"       − seulement #{o['a']} : {k}")
                for k in st["only_b"]:
                    print(f"       + seulement #{o['b']} : {k}")
                for c in st["changed"]:
                    print(f"       ~ {c['key']} : {c['a']} → {c['b']}")
            return 0
        if args.run_command == "save":
            params: dict[str, Any] = {"input": args.input, "to": args.to}
            if args.input_stage:
                params["input_stage"] = args.input_stage
            if args.decisions:
                params["decisions"] = read_yaml(args.decisions) or []
            return show(s.call("pipeline.save", params, args.sandbox), args.json)
        params = {"batch_id": args.batch_id or args.batch or "lot", "from": args.first, "to": args.last}
        for key, value in (("batches", args.batches), ("batch", args.batch), ("oracle", args.oracle),
                           ("profile", args.profile), ("llm_config", args.llm_config), ("input", args.input),
                           ("input_stage", args.input_stage), ("max_calls", args.max_calls)):
            if value is not None:
                params[key] = value
        if args.documents:
            params["documents"] = list(args.documents)
        if args.artifact:
            params["artifact"] = read_yaml(args.artifact)
        if args.yes:
            params["confirm"] = True
        cancel = threading.Event()

        def progress(stage: str, info: dict[str, Any]) -> None:
            detail = f" {info['done']}/{info['total']} passages" if info.get("total") else ""
            calls = f", {info['calls']} appel(s)" if info.get("calls") else ""
            if "completed" not in info:
                print(f"  … {stage}{detail}{calls}", flush=True)

        box: dict[str, Result] = {}
        worker = threading.Thread(target=lambda: box.update(r=Session(args.db).call(
            "pipeline.run", params, args.sandbox, progress=progress, cancel=cancel)), daemon=True)
        worker.start()
        try:
            while worker.is_alive():
                worker.join(0.2)
        except KeyboardInterrupt:  # Ctrl+C : arrêt propre entre deux groupes de passages
            print("  arrêt demandé…", flush=True)
            cancel.set()
            worker.join()
        result = box["r"]
        if args.json:
            return show(result, True)
        out = result.output or {}
        run_id = f", exécution #{result.trace.run_id}" if result.trace.run_id else ""
        print(f"pipeline.run {params['from']} → {params['to']} : {result.status}{run_id}")
        for i in result.issues:
            print(f"  - {i.severity} [{i.rule}] {i.message}")
        if result.status == "pending" and out.get("estimate"):
            e = out["estimate"]
            print(f"  estimation : {e['calls']} appel(s) au modèle {e['model']} (plafond {e['max_calls']}) ;"
                  " relancer avec --yes pour confirmer")
        for stg in out.get("stages", []):
            print(f"  {stg['stage']:4} {stg['name']:<14} {stg['duration_ms']:>8} ms  {json.dumps(stg['indicators'], ensure_ascii=False)}")
        if out.get("proposals"):
            print(f"  propositions : {', '.join(out['proposals'])}")
        if result.trace.run_id and out.get("stages"):
            print(f"  enregistrer : worldkit run save {result.trace.run_id} [--sandbox N] [--to E12]")
        return 0 if result.ok else 1


# ---------------------------------------------------------------------------
# Parcours d'acceptation en ligne de commande (I-CLI-01, I-ACC-01)
# ---------------------------------------------------------------------------

def add_walkthrough_parsers(commands: Any) -> None:
    wt = commands.add_parser("walkthrough", help="parcours d'acceptation (I5)")
    wt_cmds = wt.add_subparsers(dest="walkthrough_command", required=True)
    wt_cmds.add_parser("list")
    r = wt_cmds.add_parser("run", help="exécuter un parcours et ses prérequis dans un monde d'acceptation neuf")
    r.add_argument("id")
    r.add_argument("--corpus", default="corpus/valmont-v1")
    r.add_argument("--json", action="store_true")


def run_walkthrough(args: argparse.Namespace) -> int:
    from . import Session
    with Session(args.db) as s:
        if args.walkthrough_command == "list":
            for w in s.call("walkthrough.list").output:
                flag = "exécutable" if w["executable"] else "à convertir"
                print(f"{w['id']}  {w['title']:<55} {w['milestone']:<4} prérequis {','.join(w['requires']) or '—':<5}"
                      f" attendus {w['structured']}/{w['expects']} structurés  {flag}")
            return 0
        result = s.call("walkthrough.run", {"id": args.id, "corpus": args.corpus})
        if args.json:
            return show(result, True)
        o = result.output or {}
        run_id = f", exécution #{result.trace.run_id}" if result.trace.run_id else ""
        print(f"{args.id} : {result.status}{run_id} — chaîne {' → '.join(o.get('chain', []))}")
        if o.get("sandbox"):
            print(f"  monde d'acceptation : bac {o['sandbox']} (worldkit call … --sandbox {o['sandbox']})")
        for res in o.get("results", []):
            broken = [i + 1 for i, st in enumerate(res["steps"]) if not st["ok"]]
            print(f"  {res['id']} : {len(res['steps'])} étape(s)" + (f", EN ÉCHEC : {broken}" if broken else ""))
        labels = {"passed": "réussi ", "failed": "ÉCHOUÉ", "unstructured": "à lire "}
        for e in (o.get("results") or [{}])[-1].get("expects", []):
            print(f"    [{labels[e['status']]}] {e['text']}")
            for c in e["checks"]:
                if not c["ok"]:
                    print(f"        ✘ {c['check']['check']} : {c['detail']}")
        for i in result.issues:
            if i.code in ("invalid_params", "service_error"):
                print(f"  - {i.severity} : {i.message}")
        return 0 if result.ok else 1
