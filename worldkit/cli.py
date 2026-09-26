"""Ligne de commande `worldkit` (T-LNG-01).

    worldkit schema validate <fichier.yaml>…

Code de sortie : 0 si tous les schémas sont valides, 1 sinon, 2 si un fichier est illisible.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

import yaml

from worldkit.core.schema import Severity, has_errors, read_yaml, validate_schema


def _schema_validate(paths: Sequence[str]) -> int:
    status = 0
    for path in paths:
        try:
            doc = read_yaml(path)
        except (OSError, yaml.YAMLError) as e:
            print(f"ERREUR  {path} : lecture impossible ({e})")
            status = max(status, 2)
            continue
        issues = validate_schema(doc)
        if has_errors(issues):
            print(f"REJETÉ  {path}")
            status = max(status, 1)
        else:
            print(f"VALIDE  {path}")
        for issue in issues:
            mark = "erreur" if issue.severity is Severity.ERROR else "avertissement"
            print(f"  - {mark} {issue}")
    return status


def main(argv: Sequence[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(prog="worldkit", description="Outil de worldbuilding (nom provisoire).")
    commands = parser.add_subparsers(dest="command", required=True)
    schema = commands.add_parser("schema", help="schémas de monde et systèmes de règles")
    schema_cmds = schema.add_subparsers(dest="schema_command", required=True)
    validate = schema_cmds.add_parser("validate", help="valider un ou plusieurs schémas (R-SCH-02, T-SCH-01)")
    validate.add_argument("files", nargs="+", metavar="fichier.yaml")
    args = parser.parse_args(argv)
    if args.command == "schema" and args.schema_command == "validate":
        return _schema_validate(args.files)
    parser.error("commande inconnue")  # pragma: no cover
    return 2


if __name__ == "__main__":
    sys.exit(main())
