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
