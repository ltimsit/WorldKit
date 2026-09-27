"""Ligne de commande `worldkit` (T-LNG-01).

    worldkit schema validate <fichier.yaml>…
    worldkit --db valmont.db world init world.yaml
    worldkit --db valmont.db edit apply|submit <éditions.yaml> [--id ID…]
    worldkit --db valmont.db edit confirm|rebase|abandon <ID>
    worldkit --db valmont.db edit list [--status pending]
    worldkit --db valmont.db edit transpose <ID> --to <branche> [--keep | --adapt changes.yaml | --discard]
    worldkit --db valmont.db branch create <nom> [--from BRANCHE] [--at POINT] | branch list
    worldkit --db valmont.db point set <nom> [--at POINT] | point list
    worldkit --db valmont.db wiki page <entité> [--filter author|player] [--point POINT]
    worldkit --db valmont.db wiki render --out <dossier> [--filter …] [--point …]
    worldkit --db valmont.db export [--filter …] [--point …]
    worldkit --db valmont.db check [--point …]
    worldkit --db valmont.db ingest <lot> [documents…] [--batches batches.yaml] (--oracle <gold/> | --profile P)
    worldkit --db valmont.db eval extraction --batches batches.yaml --oracle <gold/> --profile P [--batch b1]…
    worldkit --db valmont.db review list [--batch LOT] | review show <proposition>
    worldkit --db valmont.db review accept <proposition>… [--keep 0,1] [--drop-optional]
    worldkit --db valmont.db review refuse <proposition>… [--changes 2] [--reason …]
    worldkit --db valmont.db review choose <proposition> | adapt <proposition> --prepend|--replace <changes.yaml>
    worldkit --db valmont.db review dismiss <document> <passage>

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
    "batch_conflict": "conflit dans le lot", "competing": "concurrente", "duplicate": "déjà proposé",
    "hint_visibility": "indice de notoriété", "claim": "affirmation",
    "enrichment": "enrichissement", "optional": "facultatif", "support": "support",
}


def _tags(tags: list[str]) -> str:
    return ", ".join(TAG_FR.get(t, t) for t in tags)


def _llm_extractor(args: argparse.Namespace) -> Any:
    from worldkit.periphery.llm import load_config, make_adapter
    from worldkit.periphery.llm_extractor import LLMExtractor
    profile = load_config(args.llm_config).profile(args.profile, "extraction")
    return LLMExtractor(make_adapter(profile), profile)


def _run_ingest(world: Any, args: argparse.Namespace) -> int:
    from worldkit.ingest.batch import batch_documents, ingest
    from worldkit.periphery.extraction import OracleExtractor
    paths = list(args.documents) or (batch_documents(args.batches, args.batch) if args.batches else [])
    if not paths:
        print("ERREUR : aucun document (donner les fichiers, ou --batches)")
        return 2
    extractor = OracleExtractor(Path(args.oracle)) if args.oracle else _llm_extractor(args)
    print(f"extracteur : {extractor.version}")
    report = ingest(world, args.batch, paths, extractor)
    base = report.base
    print(f"lot {report.batch_id} : base {base.branch}, rang {base.seq} (schema_rev {base.schema_rev})")
    print(f"  {len(report.documents)} document(s), passages extraits {report.extracted}, relus du cache {report.cached}")
    print(f"  {len(report.proposals)} proposition(s) en attente, {len(report.supports)} support(s) enregistré(s)")
    if report.new_entities:
        print("  entités nouvelles : " + ", ".join(f"{e.id} ({e.type})" for e in report.new_entities))
    for where, flags in report.flagged.items():
        print(f"  {where} : {', '.join(flags)}")
    if report.unchanged or report.removed or report.remembered:
        print(f"  passages inchangés {report.unchanged}, retirés {report.removed} ;"
              f" décisions reprises sans question {report.remembered}")
    for doc in report.obsolete:
        print(f"  {doc} : document obsolète, rien d'ingéré (R-DOC-05)")
    for where, error in report.errors.items():
        print(f"  {where} : erreur d'extraction ({error[:160]})")
    return 0


def _run_eval(world: Any, args: argparse.Namespace) -> int:
    import json as _json
    from worldkit.ingest.batch import batch_documents, extraction_context
    from worldkit.periphery.evaluation import evaluate
    from worldkit.periphery.extraction import OracleExtractor
    import yaml as _yaml
    declared = _yaml.safe_load(Path(args.batches).read_text(encoding="utf-8"))["batches"]
    batches = args.batch or [b["id"] for b in declared]
    paths = [batch_documents(args.batches, b) for b in batches]
    from worldkit.ingest.batch import CachedExtractor, schema_fingerprint
    state = world.state()
    extractor = _llm_extractor(args)
    if not args.no_cache:
        extractor = CachedExtractor(extractor, world, schema_fingerprint(state))
    print(f"extracteur : {extractor.version} ; {sum(map(len, paths))} document(s) ; répétitions : {args.repeat}")
    report = evaluate(extractor, OracleExtractor(Path(args.oracle)), Path(args.oracle), paths,
                      extraction_context(world, state), args.repeat, state)
    if not args.no_cache:
        print(f"  cache : {extractor.hits} relu(s), {extractor.flush()} ajouté(s)")
    summary = report.summary()
    for k, v in summary.items():
        if k != "per_op":
            print(f"  {k} : {v}")
    for op, m in summary["per_op"].items():
        print(f"  {op:16} précision {m['precision']:.2f}  rappel {m['recall']:.2f}  (vp {m['tp']}, fp {m['fp']}, fn {m['fn']})")
    for r in report.passages:
        missing, extra = r.expected - r.found, r.found - r.expected
        if missing or extra or r.traps or r.error or not r.attribution_ok:
            print(f"  -- {r.doc} p{r.index}" + (f" : ERREUR {r.error[:120]}" if r.error else ""))
            for k in sorted(missing, key=repr):
                print(f"     manque  {dict(k)}")
            for k in sorted(extra, key=repr):
                print(f"     en trop {dict(k)}")
            for t in r.traps:
                print(f"     piège   {t}")
            if not r.attribution_ok:
                print("     attribution mal détectée")
    if args.out:
        Path(args.out).write_text(_json.dumps({"summary": summary, "passages": [
            {"doc": r.doc, "passage": r.index, "expected": sorted(map(str, r.expected)),
             "found": sorted(map(str, r.found)), "traps": r.traps, "error": r.error, "stability": r.stability}
            for r in report.passages]}, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"rapport écrit : {args.out}")
    return 0


def _indices(parts: list[str] | None) -> list[int] | None:
    """« 0,1 », « 0 1 » ou « 0, 1 » : PowerShell passe 0,1 non entre guillemets comme deux arguments."""
    if not parts:
        return None
    return [int(i) for part in parts for i in part.split(",") if i.strip()]


def _print_decided(results: list[Any]) -> int:
    status = 0
    for d in results:
        applied = f" → {d.edit_id} (rang {d.seq})" if d.seq is not None else ""
        print(f"{d.proposal} : {d.action}{applied}" if d.ok else f"{d.proposal} : REFUSÉE")
        _print_issues(d.issues)
        status = status if d.ok else 1
    return status


def _run_decision(world: Any, args: argparse.Namespace) -> int:
    from worldkit.ingest import decide
    cmd = args.review_command
    if cmd == "accept":
        return _print_decided([decide.accept(world, pid, _indices(args.keep), args.drop_optional, args.reason)
                               for pid in args.proposals])
    if cmd == "refuse":
        return _print_decided([decide.refuse(world, pid, _indices(args.changes), args.reason)
                               for pid in args.proposals])
    if cmd == "choose":
        return _print_decided(decide.choose(world, args.proposal, args.reason))
    if cmd == "abandon":
        return _print_decided([decide.abandon(world, pid, args.reason) for pid in args.proposals])
    if cmd == "move":
        return _print_decided([decide.move(world, args.proposal, args.to, args.reason)])
    if cmd == "qualify":
        return _print_decided([decide.qualify(world, args.target, args.value, args.visibility, args.reason)])
    if cmd == "promote":
        return _print_decided([decide.promote(world, args.proposal, args.visibility, args.reason)])
    if cmd == "adapt":
        from worldkit.core.schema import parse_change
        raw = read_yaml(args.prepend or args.replace)
        items = raw["changes"] if isinstance(raw, dict) else raw
        changes = [parse_change(c) for c in items]
        return _print_decided([decide.adapt(world, args.proposal, changes, replace=bool(args.replace),
                                            reason=args.reason)])
    decide.dismiss(world, args.document, args.passage, args.reason)
    print(f"{args.document} p{args.passage} : écarté")
    return 0


def _run_review(world: Any, args: argparse.Namespace) -> int:
    from worldkit.ingest.review import flagged_passages, proposals, supports
    if args.review_command not in ("list", "show"):
        return _run_decision(world, args)
    if args.review_command == "list":
        views = proposals(world, args.batch, branch=args.branch)
        for v in views:
            recheck = " (bloquée : document obsolète)" if v.blocked else ""
            print(f"{v.id}{recheck}  [{_tags(v.tags)}]")
            for c in v.changes:
                if c.state == "open":
                    suggested = c.detail.get("suggested")
                    hint = f"   (suggestion : {suggested})" if suggested else ""
                    print(f"    {c.text}{hint}")
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
    closed = f" ({v.closed_reason})" if v.closed_reason else ""
    print(f"{v.id} — {v.status}{closed}")
    print(f"lot {v.batch}, document {v.doc}, passage {v.passage} ; sujet {v.subject} ; base {base}")
    for i, c in enumerate(v.changes):
        state = "" if c.state == "open" else f" — {c.state}"
        print(f"  [{i}] {c.text}   [{_tags(c.tags)}]{state}")
        occ = c.detail.get("occupied_by")
        if occ:
            fact = occ["fact"]
            held = f"{fact[2]}({fact[1]}, {fact[3]})" if fact[0] == "rel" else f"{fact[1]}.{fact[2]} = {occ.get('value')!r}"
            print(f"      la base contient : {held}")
        for label in c.detail.get("contradicts", []):
            print(f"      contredit {label} (même document)")
        for label in c.detail.get("conflicts_with", []):
            print(f"      en conflit avec {label} (même lot, aucune ne l'emporte)")
        for other in c.detail.get("competes_with", []):
            print(f"      concurrente de {other} (autre lot)")
        if "priority" in c.detail:
            print(f"      priorité suggérée : {c.detail['priority']} (lot plus ancien)")
        for other in c.detail.get("same_as", []):
            print(f"      déjà proposé par {other}")
    pending = {p.id for p in proposals(world)}
    for d in v.depends_on:
        print(f"  dépend de {d}" + ("" if d in pending else " (décidée)"))
    for i in v.issues:
        print(f"  {i}")
    return 0


def _run_transpose(world: Any, args: argparse.Namespace) -> int:
    changes = None
    action = "keep" if args.keep else "discard" if args.discard else "adapt" if args.adapt else "auto"
    if args.adapt:
        from worldkit.core.schema import parse_change
        raw = read_yaml(args.adapt)
        changes = [parse_change(c) for c in (raw["changes"] if isinstance(raw, dict) else raw)]
    outcome, analysis = world.transpose(args.edit_id, args.to, action, changes, args.reason)
    labels = {"independent": "indépendante", "dependent": "dépendante (fait absent de la cible)",
              "contradictory": "contradictoire"}
    print(f"{args.edit_id} ({analysis.source}, rang {analysis.source_seq}) → {args.to} : {labels[analysis.relation]}")
    for d in analysis.divergences:
        print(f"  - {d.describe()}")
    if outcome.status is not None:
        where = f" (rang {outcome.seq})" if outcome.seq else ""
        print(f"{outcome.edit_id} : {outcome.status}{where}")
    else:
        print("non transposée : décider (--keep, --adapt fichier.yaml, --discard)")
    _print_issues(outcome.issues)
    return 0 if outcome.ok and outcome.status is not None else 1


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
        if args.command == "eval":
            return _run_eval(world, args)
        if args.command == "review":
            return _run_review(world, args)
        if args.command == "edit":
            if args.edit_command == "transpose":
                return _run_transpose(world, args)
            if args.edit_command in ("apply", "submit"):
                status = 0
                for edit in _read_edits(args.file, args.id):
                    if args.branch:
                        edit = edit.model_copy(update={"branch": args.branch})
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

        if args.command == "branch":
            if args.branch_command == "create":
                seq = world.create_branch(args.name, args.from_branch, args.at)
                print(f"branche {args.name} créée depuis {args.from_branch or world.reference_branch}, rang {seq}")
            else:
                for b in world.store.branches():
                    parent, fork = world.store.branch_info(b)
                    origin = f"depuis {parent} au rang {fork}" if parent else "branche racine"
                    ref = " (référence)" if b == world.reference_branch else ""
                    print(f"{b}{ref} : {origin}, tête au rang {world.store.head_seq(b)}")
            return 0

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
            from worldkit.ingest.review import sources
            view = View(state, Filter(args.filter), sources(world, args.branch),
                        world.redefined_after(args.branch, state.seq))
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
            from worldkit.ingest.review import orphan_facts
            issues = state_report(state)
            if args.point in (None, "head"):
                issues += orphan_facts(world, args.branch)
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
        p.add_argument("--branch", default=None, help="branche visée (remplace celle du fichier)")
    tr = edit_cmds.add_parser("transpose", help="appliquer une édition sur une autre branche (R-HIS-05)")
    tr.add_argument("edit_id")
    tr.add_argument("--to", required=True, help="branche cible")
    trg = tr.add_mutually_exclusive_group()
    trg.add_argument("--keep", action="store_true", help="garder malgré une contradiction")
    trg.add_argument("--adapt", help="fichier YAML des changements à appliquer à la place")
    trg.add_argument("--discard", action="store_true", help="écarter (tracé)")
    tr.add_argument("--reason", default=None)

    br = commands.add_parser("branch", help="branches et variantes (R-HIS-03)")
    br_cmds = br.add_subparsers(dest="branch_command", required=True)
    brc = br_cmds.add_parser("create")
    brc.add_argument("name")
    brc.add_argument("--from", dest="from_branch", default=None, help="branche d'origine (défaut : référence)")
    brc.add_argument("--at", default=None, help="point de divergence : rang ou point nommé (défaut : tête)")
    br_cmds.add_parser("list")
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
    ing.add_argument("--oracle", help="dossier gold/ lu par l'extracteur oracle (T-ING-19)")
    ing.add_argument("--profile", help="profil LLM (voir worldkit-llm.yaml) ; défaut : tasks.extraction")
    ing.add_argument("--llm-config", default=None, help="fichier de profils LLM (défaut : worldkit-llm.yaml)")

    ev = commands.add_parser("eval", help="mesures T2 d'un extracteur contre le gold")
    ev_cmds = ev.add_subparsers(dest="eval_command", required=True)
    evx = ev_cmds.add_parser("extraction", help="précision, rappel, pièges, stabilité")
    evx.add_argument("--batches", required=True)
    evx.add_argument("--oracle", required=True, help="dossier gold/")
    evx.add_argument("--profile", default=None)
    evx.add_argument("--llm-config", default=None)
    evx.add_argument("--batch", action="append", help="lot à mesurer (répétable) ; défaut : tous")
    evx.add_argument("--repeat", type=int, default=1, help="2 pour mesurer la stabilité (deux appels par passage)")
    evx.add_argument("--out", default=None, help="rapport JSON détaillé")
    evx.add_argument("--no-cache", action="store_true", help="rappeler le modèle même pour un passage déjà extrait")

    review = commands.add_parser("review", help="file de revue des propositions")
    review_cmds = review.add_subparsers(dest="review_command", required=True)
    rl = review_cmds.add_parser("list")
    rl.add_argument("--batch", default=None)
    rl.add_argument("--branch", default=None)
    review_cmds.add_parser("show").add_argument("proposal")
    acc = review_cmds.add_parser("accept", help="accepter (tout, ou --keep)")
    acc.add_argument("proposals", nargs="+")
    acc.add_argument("--keep", nargs="+", help="indices des changements gardés (0,1 ou 0 1) ; les autres sont refusés")
    acc.add_argument("--drop-optional", action="store_true", help="écarter les changements facultatifs")
    ref = review_cmds.add_parser("refuse", help="refuser (tout, ou --changes)")
    ref.add_argument("proposals", nargs="+")
    ref.add_argument("--changes", nargs="+", help="indices des changements refusés (0,1 ou 0 1)")
    mov = review_cmds.add_parser("move", help="déplacer une proposition vers une autre branche (T-ING-16)")
    mov.add_argument("proposal")
    mov.add_argument("--to", required=True)
    abd = review_cmds.add_parser("abandon", help="abandonner (ex. un diff du mode edit)")
    abd.add_argument("proposals", nargs="+")
    cho = review_cmds.add_parser("choose", help="trancher un conflit : accepter celle-ci, refuser les autres")
    cho.add_argument("proposal")
    ada = review_cmds.add_parser("adapt", help="confirmer en adaptant (édition dérivée)")
    ada.add_argument("proposal")
    grp = ada.add_mutually_exclusive_group(required=True)
    grp.add_argument("--prepend", help="fichier YAML de changements ajoutés en tête")
    grp.add_argument("--replace", help="fichier YAML de changements qui remplacent la proposition")
    dis = review_cmds.add_parser("dismiss", help="écarter un passage signalé (attribution)")
    dis.add_argument("document")
    dis.add_argument("passage", type=int)
    qua = review_cmds.add_parser("qualify", help="qualifier une affirmation (R-DOC-07)")
    qua.add_argument("target", help="proposition d'affirmation, ou identifiant d'une affirmation appliquée")
    qua.add_argument("value", choices=["true", "false", "undetermined"])
    qua.add_argument("--visibility", choices=["public", "secret", "unqualified"], default=None)
    pro = review_cmds.add_parser("promote", help="promouvoir une affirmation en fait")
    pro.add_argument("proposal")
    pro.add_argument("--visibility", choices=["public", "secret", "unqualified"], default=None)
    for p in (acc, ref, abd, cho, ada, dis, qua, pro, mov):
        p.add_argument("--reason", default=None)

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
    except (OSError, KeyError, ValueError, RuntimeError, ValidationError, yaml.YAMLError) as e:
        print(f"ERREUR : {e}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
