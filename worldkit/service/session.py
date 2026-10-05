"""Session de service : un monde de travail, son journal d'exécutions et ses bacs à sable.

`Session(db).call(nom, paramètres, cible)` est le seul point d'entrée : l'interface (I2), la ligne de
commande (I-CLI-01) et les tests passent tous par lui. Il valide les paramètres, ouvre la cible (le monde
ou un bac), appelle l'opération, mesure, fabrique le `Result` et l'enregistre selon la sorte (décision I1).
"""

from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass
from importlib import metadata
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from worldkit.core.schema import Severity
from worldkit.core.world import World

from .registry import REGISTRY, Output, Params
from .result import IssueView, Result, Trace, has_error, issues_of, jsonable
from .runs import RunStore, Sandbox

WORLD = "world"


def code_version() -> str:
    try:
        return metadata.version("worldkit")
    except metadata.PackageNotFoundError:  # pragma: no cover — paquet non installé
        return "dev"


def runs_path(db: Path) -> Path:
    return db.with_name(f"{db.stem}.runs.db")


def sandbox_path(db: Path, n: int) -> Path:
    return db.with_name(f"{db.stem}.sandbox-{n}.db")


def parse_target(target: str | int | None) -> str:
    """`world` (défaut), `sandbox:3`, ou simplement `3`."""
    if target in (None, "", WORLD):
        return WORLD
    text = str(target)
    if text.isdigit():
        return f"sandbox:{text}"
    if text.startswith("sandbox:") and text[8:].isdigit():
        return text
    raise ValueError(f"cible inconnue : {target} (world, ou le numéro d'un bac à sable)")


@dataclass
class Context:
    """Ce que reçoit la fonction d'une opération."""

    session: Session
    target: str
    world: World | None = None
    run_id: int | None = None          # exécution enregistrée, créée avant l'appel (artefacts, progression)
    progress: Any = None               # rappel (étape, informations) : tâches de fond (décision I4)
    cancel: Any = None                 # threading.Event : arrêt demandé

    def report(self, stage: str, info: dict[str, Any]) -> None:
        if self.run_id is not None:
            self.session.runs.set_progress(self.run_id, {"stage": stage, **info})
        if self.progress is not None:
            self.progress(stage, info)


class Session:
    def __init__(self, db: str | Path) -> None:
        self.db = Path(db)
        if not self.db.exists():
            raise FileNotFoundError(f"monde introuvable : {self.db}")
        self.runs = RunStore(runs_path(self.db))

    def close(self) -> None:
        self.runs.close()

    def __enter__(self) -> Session:
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    # --- Cibles ---

    def file_of(self, target: str) -> Path:
        if target == WORLD:
            return self.db
        sandbox = self.runs.sandbox(int(target.split(":", 1)[1]))
        if sandbox.status != "active":
            raise ValueError(f"bac à sable {sandbox.id} jeté : il n'est plus une cible")
        return Path(sandbox.file)

    def open(self, target: str = WORLD) -> World:
        return World.open(self.file_of(parse_target(target)))

    # --- Bacs à sable (I-SBX-01) ---

    def create_sandbox(self, origin: str = WORLD, note: str | None = None) -> Sandbox:
        """Copie cohérente (sauvegarde SQLite) du monde ou d'un autre bac ; la parenté est notée."""
        origin = parse_target(origin)
        source = self.file_of(origin)
        n = self.runs.next_sandbox_id()
        file = sandbox_path(self.db, n)
        if file.exists():
            raise FileExistsError(f"fichier de bac déjà présent : {file}")
        src, dst = sqlite3.connect(str(source)), sqlite3.connect(str(file))
        try:
            src.backup(dst)
        finally:
            src.close()
            dst.close()
        world = World.open(file)
        try:
            heads = {b: world.store.head_seq(b) for b in world.store.branches()}
        finally:
            world.close()
        sid = self.runs.add_sandbox(str(file), origin, heads, note)
        return self.runs.sandbox(sid)

    def create_acceptance(self, world_yaml: str | Path, walkthrough: str) -> Sandbox:
        """Monde d'acceptation neuf, créé depuis `world.yaml`, enregistré comme un bac consultable ; son origine
        (`acceptance:<parcours>`) le rend impossible à promouvoir (I-ACC-01)."""
        n = self.runs.next_sandbox_id()
        file = self.db.with_name(f"{self.db.stem}.acceptance-{n}.db")
        world = World.create(file, world_yaml)
        world.close()
        sid = self.runs.add_sandbox(str(file), f"acceptance:{walkthrough}", {}, f"parcours {walkthrough}")
        return self.runs.sandbox(sid)

    def drop_sandbox(self, sandbox_id: int) -> Sandbox:
        """Jeter un bac : son fichier est supprimé, ses exécutions restent (décision I1)."""
        sandbox = self.runs.sandbox(sandbox_id)
        if sandbox.status != "active":
            raise ValueError(f"bac à sable {sandbox_id} déjà jeté")
        Path(sandbox.file).unlink(missing_ok=True)
        self.runs.drop_sandbox(sandbox_id)
        return self.runs.sandbox(sandbox_id)

    # --- Rendre réel (I-SBX-01, décision I3) ---

    def chain(self, sandbox_id: int) -> list[tuple[Sandbox, int | None]]:
        """Bacs de la racine au bac donné, chacun avec sa borne : les écritures d'un bac parent ne comptent
        que jusqu'à la copie de son enfant (`after_run`)."""
        out: list[tuple[Sandbox, int | None]] = []
        box, upto = self.runs.sandbox(sandbox_id), None
        while True:
            out.append((box, upto))
            if box.origin == WORLD:
                break
            upto = box.after_run
            box = self.runs.sandbox(int(box.origin.split(":", 1)[1]))
        return list(reversed(out))

    def promote(self, sandbox_id: int, confirm: bool = False) -> dict[str, Any]:
        """Répétition à blanc sur une copie du monde **tel qu'il est maintenant**, puis, si rien ne diverge et
        si c'est confirmé, application en tout ou rien sur le monde de travail. Jamais de copie de fichier."""
        box = self.runs.sandbox(sandbox_id)
        if box.status != "active":
            raise ValueError(f"bac à sable {sandbox_id} {box.status} : rien à rendre réel")
        if box.origin.startswith("acceptance:"):
            raise ValueError(f"le bac {sandbox_id} est un monde d'acceptation ({box.origin}) : il ne se rend pas réel")
        steps = [(rec, self.runs.result(rec.id)) for b, upto in self.chain(sandbox_id)
                 for rec in self.runs.writes(b.target, upto)]
        rehearsal = self.create_sandbox(WORLD, note=f"répétition du bac {sandbox_id}")
        report: list[dict[str, Any]] = []
        try:
            for rec, recorded in steps:
                entry = {"run": rec.id, "from": rec.target, "operation": rec.operation, "params": rec.params,
                         "recorded": recorded.status}
                if recorded.status not in ("ok", "pending"):
                    report.append({**entry, "verdict": "ignored", "detail": "refusée ou en erreur dans l'essai"})
                    continue
                again = self.call(rec.operation, rec.params, rehearsal.target, record=False)
                report.append({**entry, "rehearsed": again.status, **_verdict(recorded, again)})
        finally:
            self.drop_sandbox(rehearsal.id)
        divergences = [r for r in report if r["verdict"] == "divergence"]
        applied: list[dict[str, Any]] = []
        if confirm and not divergences:
            for r in report:
                if r["verdict"] == "ignored":
                    continue
                done = self.call(r["operation"], r["params"], WORLD)
                applied.append({"from_run": r["run"], "run": done.trace.run_id, "status": done.status})
            self.runs.set_status(sandbox_id, "promoted")
        return {"sandbox": sandbox_id, "chain": [b.id for b, _ in self.chain(sandbox_id)], "steps": report,
                "divergences": len(divergences), "gaps": sum(1 for r in report if r["verdict"] == "gap"),
                "applied": applied, "confirmed": confirm}

    # --- Appel ---

    def call(self, name: str, params: dict[str, Any] | None = None, target: str | int | None = None,
             record: bool | None = None, run_id: int | None = None, progress: Any = None,
             cancel: Any = None) -> Result:
        op = REGISTRY.get(name)
        if op is None:
            known = ", ".join(sorted(REGISTRY))
            raise KeyError(f"opération inconnue : {name} (connues : {known})")
        raw = dict(params or {})
        start = time.perf_counter()
        target_name = WORLD
        keep = record if record is not None else op.kind != "read"
        try:
            target_name = parse_target(target)
            p = op.params.model_validate(raw)
            if keep and run_id is None:  # l'exécution existe avant de commencer : artefacts et progression s'y rangent
                run_id = self.runs.begin(name, op.kind, target_name, jsonable(p.model_dump(mode="json",
                                                                                            exclude_defaults=True)))
            ctx = Context(self, target_name, None, run_id, progress, cancel)
            if op.needs_world:
                ctx.world = self.open(target_name)
                try:
                    out = op.func(ctx, p)
                finally:
                    ctx.world.close()
            else:
                out = op.func(ctx, p)
            status = out.status or ("refused" if has_error(out.issues) else "ok")
            result = Result(operation=name, kind=op.kind, target=target_name, status=status,
                            params=jsonable(p.model_dump(mode="json", exclude_defaults=True)),
                            output=jsonable(out.value), issues=issues_of(out.issues),
                            indicators=jsonable(out.indicators))
        except ValidationError as e:
            result = _error(name, op.kind, target_name, raw, [
                IssueView(code="invalid_params", severity=str(Severity.ERROR), rule="I-CLI-01",
                          message=f"{'.'.join(map(str, err['loc']))} : {err['msg']}") for err in e.errors()])
        except (KeyError, ValueError, FileNotFoundError, FileExistsError) as e:
            message = e.args[0] if e.args else str(e)
            result = _error(name, op.kind, target_name, raw, [
                IssueView(code="service_error", severity=str(Severity.ERROR), rule="", message=str(message))])
        calls = (result.indicators or {}).get("llm_calls", 0)  # appels au modèle relevés par l'opération (I-LLM-01)
        result.trace = Trace(duration_ms=round((time.perf_counter() - start) * 1000, 1), code_version=code_version(),
                             llm_calls=calls if isinstance(calls, int) else 0)
        if keep:
            self.runs.record(result, run_id)
        return result


def _verdict(recorded: Result, again: Result) -> dict[str, Any]:
    """Même statut et mêmes signalements : identique ; sortie seule différente (un rang décalé parce que le
    monde a avancé) : écart, signalé sans bloquer ; statut ou signalements différents : divergence."""
    def signals(r: Result) -> list[tuple[str, str, str, str]]:
        return sorted((i.code, i.rule, i.path, i.severity) for i in r.issues)
    if recorded.status != again.status or signals(recorded) != signals(again):
        head = f"statut {recorded.status} → {again.status}" if recorded.status != again.status else \
            "signalements différents"
        detail = head + "".join(f" ; [{i.rule}] {i.code} : {i.message}" for i in again.issues)
        return {"verdict": "divergence", "detail": detail, "issues": [i.model_dump() for i in again.issues]}
    if recorded.output != again.output:
        return {"verdict": "gap", "detail": "sortie différente (ex. rang décalé) : " + _changed(recorded.output,
                                                                                               again.output)}
    return {"verdict": "same", "detail": ""}


def _changed(a: Any, b: Any) -> str:
    if isinstance(a, dict) and isinstance(b, dict):
        keys = sorted(k for k in set(a) | set(b) if a.get(k) != b.get(k))
        return ", ".join(f"{k} : {a.get(k)!r} → {b.get(k)!r}" if not isinstance(a.get(k), (dict, list)) else k
                         for k in keys)
    return "contenu"


def _error(name: str, kind: str, target: str, raw: dict[str, Any], issues: list[IssueView]) -> Result:
    return Result(operation=name, kind=kind, target=target, status="error", params=jsonable(raw), issues=issues)


__all__ = ["Context", "Output", "Params", "Session", "WORLD", "parse_target", "runs_path", "sandbox_path"]
