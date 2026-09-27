"""Ingestion d'un lot (R-DOC-01, T-ING-01, T-ING-07, T-ING-09) : du dépôt des documents à la file de revue.

1. l'état de base est figé à l'ouverture du lot, commun à tous ses documents ;
2. chaque document est déclaré et découpé en passages (M6) ;
3. chaque passage est extrait, ou relu dans le cache (empreinte du passage, du schéma, de l'extracteur) ;
4. les entités nouvelles sont regroupées au niveau du lot ;
5. les changements sont qualifiés et assemblés en propositions (M9), enregistrées comme éditions
   en attente ; les supports sont enregistrés hors journal. Rien n'est appliqué (R-PRI-05 : `manual`).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Any

from worldkit.core.journal.models import BaseState
from worldkit.core.projection.serialize import state_to_dict
from worldkit.core.schema.changes import CloseEntity, DeleteEntity, SetVisibility
from worldkit.core.world import World
from worldkit.periphery.extraction import Extraction, ExtractionContext, Extractor, KnownEntity

from .declaration import DocumentVersion, name_key
from .proposals import NEW, NewEntity, ProposalDraft, Qualified, depends
from .queue import StoredProposal, pending_new_entities, refresh
from .store import dumps, ensure_tables


class BatchError(ValueError):
    pass


@dataclass
class BatchReport:
    batch_id: str
    base: BaseState
    documents: list[str]
    proposals: list[ProposalDraft]
    supports: list[Qualified]
    new_entities: list[NewEntity]
    flagged: dict[str, list[str]] = field(default_factory=dict)  # « doc p3 » → drapeaux
    extracted: int = 0   # passages envoyés à l'extracteur
    cached: int = 0      # passages relus dans le cache
    unchanged: int = 0   # passages déjà ingérés pour ce document : ni extraits ni reproposés (T-ING-10)
    obsolete: list[str] = field(default_factory=list)  # documents obsolètes : rien d'ingéré (R-DOC-05)
    removed: int = 0     # passages disparus depuis la version précédente : supports retirés (T-ING-11)
    remembered: int = 0  # changements dont la décision passée est reprise sans question (R-PRI-04)
    errors: dict[str, str] = field(default_factory=dict)  # erreurs d'extraction par passage (T-ING-17)


def schema_fingerprint(state: Any) -> str:
    d = state_to_dict(state)
    payload = json.dumps([d["world"], d["systems"]], sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def _known_passages(world: World, branch: str, doc_id: str) -> dict[str, list[tuple[str, int]]]:
    """Passages de la dernière version ingérée d'un document sur la branche : empreinte → [(version, indice)]."""
    latest = world.store.conn.execute(
        "SELECT d.version_fp FROM batch_documents d JOIN batches b ON b.batch_id = d.batch_id"
        " WHERE b.branch_id = ? AND d.doc_id = ? ORDER BY b.opened DESC LIMIT 1", (branch, doc_id)).fetchone()
    out: dict[str, list[tuple[str, int]]] = {}
    if latest is None:
        return out
    for fp, idx in world.store.conn.execute(
            "SELECT passage_fp, idx FROM passages WHERE doc_id = ? AND version_fp = ?", (doc_id, latest[0])):
        out.setdefault(fp, []).append((latest[0], idx))
    return out


def extraction_context(world: World, head: Any) -> ExtractionContext:
    """Entités du monde connues de l'état de base, et créations proposées par les lots en attente (T-ING-07)."""
    entities = []
    for eid, rec in sorted(head.entities.items()):
        if rec.sheet is not None:
            continue  # une fiche se désigne par son entité et son système (sheet_values, J8)
        name = head.facts.get(("attr", eid, "name"))
        aliases = sorted(str(f.value) for f in head.facts.values()
                         if f.kind == "value" and f.subject == eid and f.name == "aliases")
        entities.append(KnownEntity(eid, rec.type, tuple([str(name.value)] if name else []) + tuple(aliases)))
    for e in pending_new_entities(world, head).values():
        entities.append(KnownEntity(e.id, e.type, (e.name,) if e.name else ()))
    return ExtractionContext(head.world, tuple(entities), systems=dict(head.systems))


def passage_context(context: ExtractionContext, doc: DocumentVersion, passage: Any) -> ExtractionContext:
    speakers = passage.speakers()
    return replace(context, voice="in_world" if speakers or doc.axes.voice == "in_world" else "author",
                   speaker=speakers[0] if speakers else doc.axes.speaker, document=doc.title)






def ingest(world: World, batch_id: str, paths: list[str | Path], extractor: Extractor,
           branch: str | None = None) -> BatchReport:
    """Ingestion d'un lot = étapes E1 à E8 (calculs), puis E9+ Enregistrer (écriture) : `stages.py`."""
    from . import stages as S
    ensure_tables(world.store.conn)
    if world.store.conn.execute("SELECT 1 FROM batches WHERE batch_id = ?", (batch_id,)).fetchone():
        raise BatchError(f"lot déjà ingéré : {batch_id}")
    branch = branch or world.reference_branch
    refresh(world, branch)
    run = S.Run(world, extractor)
    try:
        art = S.run_range(run, S.start(world, batch_id, branch), "E1", "E8", paths)
        art = S.e9_save(run, art)
    except S.StageError as e:
        raise BatchError(str(e)) from e
    return report_of(art)


def report_of(art: Any) -> BatchReport:
    """Le compte rendu d'un lot enregistré, tiré de son artefact."""
    from . import stages as S
    c = art.counters
    report = BatchReport(art.batch_id, BaseState(**art.base), [d.doc_id for d in art.documents],
                         [S.proposal_of(p) for p in art.proposals], [S.qualified_of(q) for q in art.supports],
                         [S.new_of(e) for e in art.new_entities if e.get("own")])
    report.flagged = {k: v for k, v in sorted(art.flagged().items(), key=lambda kv: kv[0])}
    report.extracted, report.cached, report.unchanged = c.extracted, c.cached, c.unchanged
    report.removed, report.remembered, report.errors = c.removed, c.remembered, dict(c.errors)
    report.obsolete = [d.doc_id for d in art.documents if d.obsolete]
    return report




def _merge_new_labels(raw: list[tuple[Any, int, int, dict[str, Any], bool]]) -> list[tuple[Any, int, int, dict[str, Any], bool]]:
    """Regroupement au niveau du lot (T-ING-07) : deux étiquettes `new:` de même type et de même nom
    normalisé désignent une seule entité ; seule la première création est gardée. Un extracteur qui
    traite chaque passage isolément recrée sinon l'entité à chaque mention."""
    types: dict[str, str] = {}
    names: dict[str, str] = {}
    for _, _, _, d, _ in raw:
        e = d.get("entity")
        if isinstance(e, str) and e.startswith(NEW):
            if d.get("op") == "create_entity":
                types.setdefault(e, str(d.get("type")))
            elif d.get("op") == "set_attribute" and d.get("attribute") == "name":
                names.setdefault(e, name_key(str(d.get("value"))))
    canonical: dict[str, str] = {}
    first: dict[tuple[str, str], str] = {}
    for label, t in types.items():
        if label in names:
            canonical[label] = first.setdefault((t, names[label]), label)

    def sub(v: Any) -> Any:
        if isinstance(v, str):
            if v in canonical:
                return canonical[v]
            if " " in v:
                return " ".join(canonical.get(t, t) for t in v.split(" "))
        return v

    out, seen = [], set()
    for doc, index, i, d, optional in raw:
        d = {k: sub(v) for k, v in d.items()}
        signature = (d.get("op"), d.get("entity"), d.get("attribute"), name_key(str(d.get("value"))))
        if d.get("op") in ("create_entity", "set_attribute") and isinstance(d.get("entity"), str) \
                and d["entity"].startswith(NEW) and (d["op"] == "create_entity" or d.get("attribute") == "name"):
            if signature in seen:
                continue  # création ou nom déjà proposés par un autre passage du lot
            seen.add(signature)
        out.append((doc, index, i, d, optional))
    return out


def _remembered(world: World, branch: str, proposals: list[ProposalDraft],
                report: BatchReport) -> dict[tuple[str, int], str]:
    """Mémoire des décisions (T-ING-08, R-PRI-04) : un changement dont l'empreinte a déjà été refusée
    pour ce document sur la branche l'est de nouveau, sans question. Une acceptation passée n'a rien à
    reprendre : le fait est dans l'état, le changement y est un support."""
    out: dict[tuple[str, int], str] = {}
    for p in proposals:
        for i, q in enumerate(p.items):
            row = world.store.conn.execute(
                "SELECT action, proposal FROM decisions WHERE fingerprint = ? AND doc_id = ? AND branch_id = ?"
                " ORDER BY decision_id DESC LIMIT 1", (q.fingerprint, p.doc_id, branch)).fetchone()
            if row and row[0] in ("refuse", "abandon"):
                out[(p.id, i)] = "refused"
                q.tags.add("remembered")
                q.detail["remembered"] = {"action": row[0], "proposal": row[1]}
                report.remembered += 1
    return out


def _across_batches(proposals: list[ProposalDraft], others: list[StoredProposal]) -> None:
    """Face aux propositions en attente des autres lots : concurrence (R-PRI-07, T-ING-18), doublon
    d'empreinte, dépendances (T-ING-05). La priorité est suggérée au lot le plus ancien (R-PRI-02)."""
    for p in proposals:
        for q in p.items:
            if q.is_support or "hint_visibility" in q.tags:
                continue
            value = dumps(q.value)
            for other in others:
                for c in other.open_changes():
                    if not set(q.keys) & set(c.keys) or "hint_visibility" in c.tags:
                        continue
                    if c.value == value:
                        q.tags.add("duplicate")
                        q.detail.setdefault("same_as", []).append(other.id)
                    else:
                        q.tags.add("competing")
                        q.detail.setdefault("competes_with", []).append(other.id)
                        q.detail["priority"] = other.id  # l'autre lot est plus ancien
                        c.tags.add("competing")
                        c.detail.setdefault("competes_with", []).append(p.id)
        for other in others:
            if depends(p.reads, p.writes, other.writes):
                p.depends_on.add(other.id)


def batch_documents(batches_yaml: str | Path, batch_id: str) -> list[Path]:
    """Documents d'un lot déclaré dans un `batches.yaml` (format du corpus)."""
    import yaml
    path = Path(batches_yaml)
    declared = yaml.safe_load(path.read_text(encoding="utf-8"))["batches"]
    for b in declared:
        if b["id"] == batch_id:
            return [path.parent / d for d in b["documents"]]
    raise BatchError(f"lot inconnu dans {path} : {batch_id}")


__all__ = ["BatchError", "BatchReport", "batch_documents", "ingest", "schema_fingerprint",
           "CloseEntity", "DeleteEntity", "SetVisibility"]


class CachedExtractor:
    """Extracteur adossé au cache d'extraction de la base (T-ING-09), pour la mesure : noter de nouveau ne
    rappelle pas le modèle. Lecture au départ, écriture par `flush()` dans le fil principal (SQLite)."""

    def __init__(self, inner: Extractor, world: World, schema_fp: str) -> None:
        self.inner, self.world, self.schema_fp = inner, world, schema_fp
        self.version = inner.version
        self.concurrency = getattr(inner, "concurrency", 1)
        ensure_tables(world.store.conn)
        self._known = {fp: payload for fp, payload in world.store.conn.execute(
            "SELECT passage_fp, payload FROM extraction_cache WHERE schema_fp = ? AND extractor = ?",
            (schema_fp, self.version))}
        self._new: dict[str, str] = {}
        self.hits = 0

    def extract(self, doc_id: str, passage_text: str, context: ExtractionContext | None = None) -> Extraction:
        from .declaration import fingerprint
        fp = fingerprint(passage_text)
        payload = self._known.get(fp) or self._new.get(fp)
        if payload is not None:
            self.hits += 1
            d = json.loads(payload)
            return Extraction(tuple(d["drafts"]), frozenset(d["optional"]), tuple(d["claims"]), tuple(d["flags"]),
                              d["nature"])
        ex = self.inner.extract(doc_id, passage_text, context)
        self._new[fp] = dumps({**asdict(ex), "optional": sorted(ex.optional)})
        return ex

    def flush(self) -> int:
        with self.world.store.conn:
            for fp, payload in self._new.items():
                self.world.store.conn.execute("INSERT OR IGNORE INTO extraction_cache VALUES (?, ?, ?, ?)",
                                              (fp, self.schema_fp, self.version, payload))
        written, self._new = len(self._new), {}
        return written
