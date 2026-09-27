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

    def drop_sandbox(self, sandbox_id: int) -> Sandbox:
        """Jeter un bac : son fichier est supprimé, ses exécutions restent (décision I1)."""
        sandbox = self.runs.sandbox(sandbox_id)
        if sandbox.status != "active":
            raise ValueError(f"bac à sable {sandbox_id} déjà jeté")
        Path(sandbox.file).unlink(missing_ok=True)
        self.runs.drop_sandbox(sandbox_id)
        return self.runs.sandbox(sandbox_id)

    # --- Appel ---

    def call(self, name: str, params: dict[str, Any] | None = None, target: str | int | None = None,
             record: bool | None = None) -> Result:
        op = REGISTRY.get(name)
        if op is None:
            known = ", ".join(sorted(REGISTRY))
            raise KeyError(f"opération inconnue : {name} (connues : {known})")
        raw = dict(params or {})
        start = time.perf_counter()
        target_name = WORLD
        try:
            target_name = parse_target(target)
            p = op.params.model_validate(raw)
            ctx = Context(self, target_name)
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
        result.trace = Trace(duration_ms=round((time.perf_counter() - start) * 1000, 1), code_version=code_version())
        if record if record is not None else op.kind != "read":
            self.runs.record(result)
        return result


def _error(name: str, kind: str, target: str, raw: dict[str, Any], issues: list[IssueView]) -> Result:
    return Result(operation=name, kind=kind, target=target, status="error", params=jsonable(raw), issues=issues)


__all__ = ["Context", "Output", "Params", "Session", "WORLD", "parse_target", "runs_path", "sandbox_path"]
