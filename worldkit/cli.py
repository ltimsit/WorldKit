"""Ligne de commande `worldkit` (T-LNG-01).

    worldkit schema validate <fichier.yaml>…
    worldkit --db valmont.db world init world.yaml
    worldkit --db valmont.db edit apply|submit <éditions.yaml> [--id ID…]
    worldkit --db valmont.db edit confirm|rebase|abandon <ID>
    worldkit --db valmont.db edit list [--status pending]
    worldkit --db valmont.db point set <nom> [--at POINT] | point list
    worldkit --db valmont.db wiki page <entité> [--filter author|player] [--point POINT]
    worldkit --db valmont.db wiki render --out <dossier> [--filter …] [--point …]
    worldkit --db valmont.db export [--filter …] [--point …]
    worldkit --db valmont.db check [--point …]
    worldkit --db valmont.db ingest <lot> [documents…] [--batches batches.yaml] --oracle <gold/>
    worldkit --db valmont.db review list [--batch LOT] | review show <proposition>

Code de sortie : 0 succès, 1 refus ou signalement bloquant, 2 entrée illisible.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from worldkit.core.schema import Issue, Severity, has_errors, read_yaml, validate_schema


def _print_issues(issues: list[Issue]) -> None:
    for issue in issues:
        mark = "erreur" if issue.severity is Severity.ERROR else "avertissement"
        print(f"  - {mark} {issue}")


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
        _print_issues(issues)
    return status


def _read_edits(path: str, only: list[str] | None) -> list[Any]:
    """Un fichier d'éditions : `{edits: [...]}`, une liste, ou une seule édition."""
    from worldkit.core.journal.models import parse_edit
    raw = read_yaml(path)
    items = raw["edits"] if isinstance(raw, dict) and "edits" in raw else raw if isinstance(raw, list) else [raw]
    edits = [parse_edit(e) for e in items]
    if only:
        missing = set(only) - {e.id for e in edits}
        if missing:
            raise KeyError(f"éditions absentes du fichier : {', '.join(sorted(missing))}")
        edits = [e for e in edits if e.id in only]
    return edits


TAG_FR = {
    "out_of_schema": "hors schéma", "invalid_value": "valeur invalide", "unresolved": "entité inconnue",
    "anomaly": "anomalie", "intention": "intention", "internal_contradiction": "contradiction interne",
    "batch_conflict": "conflit dans le lot", "competing": "concurrente", "hint_visibility": "indice de notoriété",
    "enrichment": "enrichissement", "optional": "facultatif", "support": "support",
}


def _tags(tags: list[str]) -> str:
    return ", ".join(TAG_FR.get(t, t) for t in tags)


def _run_ingest(world: Any, args: argparse.Namespace) -> int:
    from worldkit.ingest.batch import batch_documents, ingest
    from worldkit.periphery.extraction import OracleExtractor
    paths = list(args.documents) or (batch_documents(args.batches, args.batch) if args.batches else [])
    if not paths:
        print("ERREUR : aucun document (donner les fichiers, ou --batches)")
        return 2
    report = ingest(world, args.batch, paths, OracleExtractor(Path(args.oracle)))
    base = report.base
    print(f"lot {report.batch_id} : base {base.branch}, rang {base.seq} (schema_rev {base.schema_rev})")
    print(f"  {len(report.documents)} document(s), passages extraits {report.extracted}, relus du cache {report.cached}")
    print(f"  {len(report.proposals)} proposition(s) en attente, {len(report.supports)} support(s) enregistré(s)")
    if report.new_entities:
        print("  entités nouvelles : " + ", ".join(f"{e.id} ({e.type})" for e in report.new_entities))
    for where, flags in report.flagged.items():
        print(f"  {where} : {', '.join(flags)}")
    return 0


def _run_review(world: Any, args: argparse.Namespace) -> int:
    from worldkit.ingest.review import flagged_passages, proposals, supports
    if args.review_command == "list":
        views = proposals(world, args.batch)
        for v in views:
            recheck = " (à revérifier)" if v.needs_recheck else ""
            print(f"{v.id}{recheck}  [{_tags(v.tags)}]")
            for c in v.changes:
                print(f"    {c.text}")
        print(f"{len(views)} proposition(s) en attente ; {len(supports(world, args.batch))} support(s)")
        for doc, idx, flags in flagged_passages(world, args.batch):
            print(f"  passage {doc} p{idx} : {', '.join(flags)}")
        return 0
    found = [v for v in proposals(world, None, None) if v.id == args.proposal]
    if not found:
        print(f"proposition inconnue : {args.proposal}")
        return 1
    v = found[0]
    base = f"rang {v.base.seq}, schema_rev {v.base.schema_rev}" if v.base else "?"
    print(f"{v.id} — {v.status}{' (à revérifier)' if v.needs_recheck else ''}")
    print(f"lot {v.batch}, document {v.doc}, passage {v.passage} ; sujet {v.subject} ; base {base}")
    for c in v.changes:
        print(f"  {c.text}   [{_tags(c.tags)}]")
        occ = c.detail.get("occupied_by")
        if occ:
            fact = occ["fact"]
            held = f"{fact[2]}({fact[1]}, {fact[3]})" if fact[0] == "rel" else f"{fact[1]}.{fact[2]} = {occ.get('value')!r}"
            print(f"      la base contient : {held}")
        for label in c.detail.get("contradicts", []):
            print(f"      contredit {label} (même document)")
        for label in c.detail.get("conflicts_with", []):
            print(f"      en conflit avec {label} (même lot, aucune ne l'emporte)")
    for d in v.depends_on:
        print(f"  dépend de {d}")
    for i in v.issues:
        print(f"  {i}")
    return 0


def _run_world(args: argparse.Namespace) -> int:
    from worldkit.core.journal.models import EditStatus
    from worldkit.core.views import Filter, View, export_json, render_page, state_report
    from worldkit.core.world import World

    if args.command == "world":
        world = World.create(args.db, args.world_yaml)
        print(f"monde « {world.decl.world} » créé : {args.db} (schéma chargé par e000)")
        return 0

    world = World.open(args.db)
    try:
        if args.command == "ingest":
            return _run_ingest(world, args)
        if args.command == "review":
            return _run_review(world, args)
        if args.command == "edit":
            if args.edit_command in ("apply", "submit"):
                status = 0
                for edit in _read_edits(args.file, args.id):
                    outcome = (world.apply if args.edit_command == "apply" else world.submit)(edit)
                    label = outcome.status or "REFUSÉE"
                    where = f" (rang {outcome.seq})" if outcome.seq is not None else ""
                    print(f"{edit.id} : {label}{where}")
                    _print_issues(outcome.issues)
                    if outcome.status is None:
                        return 1
                    if args.edit_command == "apply" and not outcome.ok:
                        status = 1
                return status
            if args.edit_command == "list":
                wanted = EditStatus(args.status) if args.status else None
                for rec in world.store.edits(args.branch or world.reference_branch, wanted):
                    flag = " (à revérifier)" if rec.needs_recheck else ""
                    base = f" base {rec.base.seq}" if rec.base else ""
                    print(f"{rec.edit.id} {rec.status} {rec.edit.origin}{base}{flag}")
                return 0
            action = {"confirm": world.confirm, "rebase": world.rebase, "abandon": world.abandon}[args.edit_command]
            outcome = action(args.edit_id)
            print(f"{outcome.edit_id} : {outcome.status}" + (f" (rang {outcome.seq})" if outcome.seq else ""))
            _print_issues(outcome.issues)
            return 0 if outcome.ok else 1

        if args.command == "point":
            if args.point_command == "set":
                from worldkit.core.world import point_name
                seq = world.set_point(args.name, args.at, args.branch)
                print(f"{point_name(args.name)} = rang {seq}")
            else:
                for name, seq in world.store.named_points(args.branch or world.reference_branch).items():
                    print(f"{name} = rang {seq}")
            return 0

        state = world.state(args.branch, args.point)
        if args.command == "wiki":
            view = View(state, Filter(args.filter))
            if args.wiki_command == "page":
                page = view.page(args.entity)
                if page is None:
                    print(f"aucune page « {args.entity} » dans la vue {args.filter}")
                    return 1
                print(render_page(page, view))
                return 0
            out = Path(args.out)
            out.mkdir(parents=True, exist_ok=True)
            ids = view.entity_ids()
            for eid in ids:
                page = view.page(eid)
                assert page is not None
                (out / f"{eid}.md").write_text(render_page(page, view), encoding="utf-8")
            index = [f"# Wiki {args.filter} — {state.branch}, rang {state.seq}", ""]
            index += [f"- [{view.title(eid)}]({eid}.md)" for eid in ids]
            (out / "index.md").write_text("\n".join(index) + "\n", encoding="utf-8")
            print(f"{len(ids)} pages écrites dans {out}")
            return 0
        if args.command == "export":
            print(export_json(state, Filter(args.filter)))
            return 0
        if args.command == "check":
            issues = state_report(state)
            print(f"{state.branch}, rang {state.seq} : {len(issues)} signalement(s)")
            _print_issues(issues)
            return 0
    finally:
        world.close()
    return 2  # pragma: no cover


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="worldkit", description="Outil de worldbuilding (nom provisoire).")
    parser.add_argument("--db", default="worldkit.db", help="fichier SQLite du monde (défaut : worldkit.db)")
    commands = parser.add_subparsers(dest="command", required=True)

    schema = commands.add_parser("schema", help="schémas de monde et systèmes de règles")
    schema_cmds = schema.add_subparsers(dest="schema_command", required=True)
    validate = schema_cmds.add_parser("validate", help="valider un ou plusieurs schémas (R-SCH-02, T-SCH-01)")
    validate.add_argument("files", nargs="+", metavar="fichier.yaml")

    world = commands.add_parser("world", help="créer un monde")
    world_cmds = world.add_subparsers(dest="world_command", required=True)
    init = world_cmds.add_parser("init", help="créer la base depuis world.yaml (édition e000)")
    init.add_argument("world_yaml")

    def view_opts(p: argparse.ArgumentParser, with_filter: bool = True) -> None:
        p.add_argument("--branch", default=None)
        p.add_argument("--point", default=None, help="rang, point nommé (@base) ou head")
        if with_filter:
            p.add_argument("--filter", choices=["author", "player"], default="author")

    edit = commands.add_parser("edit", help="éditions structurées")
    edit_cmds = edit.add_subparsers(dest="edit_command", required=True)
    for name, text in (("apply", "vérifier et appliquer"), ("submit", "mettre en attente")):
        p = edit_cmds.add_parser(name, help=f"{text} les éditions d'un fichier YAML")
        p.add_argument("file")
        p.add_argument("--id", action="append", help="ne traiter que cette édition (répétable)")
    for name in ("confirm", "rebase", "abandon"):
        edit_cmds.add_parser(name).add_argument("edit_id")
    lst = edit_cmds.add_parser("list")
    lst.add_argument("--status", choices=["pending", "applied", "abandoned"])
    lst.add_argument("--branch", default=None)

    point = commands.add_parser("point", help="points nommés de l'historique")
    point_cmds = point.add_subparsers(dest="point_command", required=True)
    pset = point_cmds.add_parser("set")
    pset.add_argument("name", help="nom du point, avec ou sans @ (base ou '@base')")
    pset.add_argument("--at", default=None, help="rang ou point nommé (défaut : tête)")
    pset.add_argument("--branch", default=None)
    point_cmds.add_parser("list").add_argument("--branch", default=None)

    wiki = commands.add_parser("wiki", help="wiki d'auteur ou joueur (vue calculée)")
    wiki_cmds = wiki.add_subparsers(dest="wiki_command", required=True)
    page = wiki_cmds.add_parser("page")
    page.add_argument("entity")
    view_opts(page)
    render = wiki_cmds.add_parser("render")
    render.add_argument("--out", required=True)
    view_opts(render)

    ing = commands.add_parser("ingest", help="ingérer un lot de documents (propositions en attente)")
    ing.add_argument("batch", help="identifiant du lot (b1…)")
    ing.add_argument("documents", nargs="*", help="documents du lot (sinon : --batches)")
    ing.add_argument("--batches", help="fichier batches.yaml qui déclare les documents du lot")
    ing.add_argument("--oracle", required=True, help="dossier gold/ lu par l'extracteur oracle (T-ING-19)")

    review = commands.add_parser("review", help="file de revue des propositions")
    review_cmds = review.add_subparsers(dest="review_command", required=True)
    review_cmds.add_parser("list").add_argument("--batch", default=None)
    review_cmds.add_parser("show").add_argument("proposal")

    view_opts(commands.add_parser("export", help="graphe filtré en JSON, pour un LLM (R-LLM-01)"))
    view_opts(commands.add_parser("check", help="non-conformités, fiches manquantes, faits masqués"), False)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = build_parser().parse_args(argv)
    if args.command == "schema":
        return _schema_validate(args.files)
    try:
        return _run_world(args)
    except (OSError, KeyError, ValueError, ValidationError, yaml.YAMLError) as e:
        print(f"ERREUR : {e}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
