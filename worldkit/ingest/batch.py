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
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from worldkit.core.journal.models import BaseState, Edit, EditStatus
from worldkit.core.projection.serialize import state_to_dict
from worldkit.core.schema.changes import CloseEntity, DeleteEntity, SetVisibility, parse_change
from worldkit.core.world import World
from worldkit.periphery.extraction import Extraction, ExtractionContext, Extractor, KnownEntity
from worldkit.periphery.llm.adapters import LLMError

from .declaration import DocumentVersion, Nature, Voice, read_document
from .declaration import name_key, normalize
from .proposals import NEW, Item, NewEntity, ProposalDraft, Qualified, assemble, depends, new_entities, resolve
from .queue import StoredProposal, load, name_index, pending_new_entities, refresh, save_change
from .store import dumps, ensure_tables

META = {Nature.META_SYSTEM, Nature.META_SHEET}


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
        if rec.scope != "world" or rec.sheet is not None:
            continue
        name = head.facts.get(("attr", eid, "name"))
        aliases = sorted(str(f.value) for f in head.facts.values()
                         if f.kind == "value" and f.subject == eid and f.name == "aliases")
        entities.append(KnownEntity(eid, rec.type, tuple([str(name.value)] if name else []) + tuple(aliases)))
    for e in pending_new_entities(world, head).values():
        entities.append(KnownEntity(e.id, e.type, (e.name,) if e.name else ()))
    return ExtractionContext(head.world, tuple(entities))


def passage_context(context: ExtractionContext, doc: DocumentVersion, passage: Any) -> ExtractionContext:
    speakers = passage.speakers()
    return replace(context, voice="in_world" if speakers or doc.axes.voice == "in_world" else "author",
                   speaker=speakers[0] if speakers else doc.axes.speaker)


def _parallel(extractor: Extractor, doc: DocumentVersion, passages: list[Any], context: ExtractionContext,
              conn: Any, schema_fp: str) -> dict[int, Extraction | LLMError]:
    """Extrait en parallèle les passages absents du cache ; l'ordre des résultats ne dépend que des passages."""
    missing = [p for p in passages if conn.execute(
        "SELECT 1 FROM extraction_cache WHERE passage_fp = ? AND schema_fp = ? AND extractor = ?",
        (p.fingerprint, schema_fp, extractor.version)).fetchone() is None]

    def one(p: Any) -> Extraction | LLMError:
        try:
            return extractor.extract(doc.doc_id, p.text, passage_context(context, doc, p))
        except LLMError as e:
            return e

    workers = max(1, int(getattr(extractor, "concurrency", 1)))
    if workers == 1 or len(missing) < 2:
        return {p.index: one(p) for p in missing}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        return dict(zip((p.index for p in missing), pool.map(one, missing)))


def _extract(world: World, extractor: Extractor, doc: DocumentVersion, schema_fp: str,
             report: BatchReport, skip: set[str], context: ExtractionContext) -> list[tuple[int, Extraction]]:
    out = []
    conn = world.store.conn
    todo = []
    for p in doc.passages:
        if p.fingerprint in skip:
            report.unchanged += 1
            continue
        todo.append(p)
    fresh = _parallel(extractor, doc, todo, context, conn, schema_fp)
    for p in todo:
        row = conn.execute("SELECT payload FROM extraction_cache WHERE passage_fp = ? AND schema_fp = ?"
                           " AND extractor = ?", (p.fingerprint, schema_fp, extractor.version)).fetchone()
        if row is not None:
            d = json.loads(row[0])
            ex = Extraction(tuple(d["drafts"]), frozenset(d["optional"]), tuple(d["claims"]), tuple(d["flags"]),
                            d["nature"])
            report.cached += 1
        else:
            ex = fresh[p.index]
            if isinstance(ex, LLMError):  # T-ING-17 : erreur d'extraction, jamais une proposition ; non mise en cache
                report.errors[f"{doc.doc_id} p{p.index}"] = str(ex)
                out.append((p.index, Extraction(flags=("extraction_error",))))
                continue
            conn.execute("INSERT INTO extraction_cache VALUES (?, ?, ?, ?)",
                         (p.fingerprint, schema_fp, extractor.version,
                          dumps({**asdict(ex), "optional": sorted(ex.optional)})))
            report.extracted += 1
        out.append((p.index, ex))
    return out


def ingest(world: World, batch_id: str, paths: list[str | Path], extractor: Extractor,
           branch: str | None = None) -> BatchReport:
    conn = world.store.conn
    ensure_tables(conn)
    if conn.execute("SELECT 1 FROM batches WHERE batch_id = ?", (batch_id,)).fetchone():
        raise BatchError(f"lot déjà ingéré : {batch_id}")
    branch = branch or world.reference_branch
    refresh(world, branch)
    head = world.state(branch)
    base = BaseState(branch=branch, seq=head.seq, schema_rev=head.schema_rev)
    schema_fp = schema_fingerprint(head)
    context = extraction_context(world, head)
    docs = [read_document(p) for p in paths]
    if len({d.doc_id for d in docs}) != len(docs):
        raise BatchError("un même document figure deux fois dans le lot")
    report = BatchReport(batch_id, base, [d.doc_id for d in docs], [], [], [])
    # Un document obsolète ne produit rien, pas même l'enregistrement de ses passages : à la levée du
    # statut, une nouvelle ingestion le traitera comme neuf (R-DOC-05, décision J3.4).
    report.obsolete = [d.doc_id for d in docs if head.obsolete_documents.get(d.doc_id)]
    docs = [d for d in docs if d.doc_id not in report.obsolete]

    # Extraction (ou cache), puis brouillons à résoudre.
    raw: list[tuple[DocumentVersion, int, int, dict[str, Any], bool]] = []
    passage_flags: dict[tuple[str, int], list[str]] = {}
    retracted: list[tuple[str, str, int]] = []
    with conn:
        for doc in docs:
            known = _known_passages(world, branch, doc.doc_id)
            current = {p.fingerprint for p in doc.passages}
            for fp, places in known.items():
                if fp not in current:  # passage supprimé ou modifié : ses supports sont retirés (T-ING-10, T-ING-11)
                    retracted += [(doc.doc_id, vfp, idx) for vfp, idx in places]
                    report.removed += 1
            for index, ex in _extract(world, extractor, doc, schema_fp, report, set(known), context):
                flags = list(ex.flags)
                nature = Nature(ex.nature) if ex.nature in Nature._value2member_map_ else None
                passage = doc.passages[index - 1]
                if doc.axes.nature in META or nature in META:
                    flags.append("meta")  # conservé, sans proposition avant J8 (cadre technique §7)
                else:
                    if doc.axes.voice is not Voice.IN_WORLD:  # en in_world, le contenu n'établit pas de faits
                        for i, draft in enumerate(ex.drafts):
                            raw.append((doc, index, i, draft, i in ex.optional))
                    speakers = passage.speakers()
                    for n, claim in enumerate(ex.claims, start=1):
                        speaker = claim.get("speaker") or (speakers[0] if speakers else doc.axes.speaker)
                        if speaker is None:
                            continue  # une affirmation a un énonciateur (R-DOC-02)
                        raw.append((doc, index, len(ex.drafts) + n, {
                            "op": "add_claim", "claim": f"{doc.doc_id}.p{index}.c{n}", "document": doc.doc_id,
                            "speaker": speaker, "text": claim["text"], "claimed": claim.get("claimed")}, False))
                passage_flags[(doc.doc_id, index)] = flags

    # Résolution : les créations proposées par les lots en attente sont reprises, jamais dupliquées (T-ING-07).
    pending_new = pending_new_entities(world, head)
    by_name = name_index(pending_new)
    reused: dict[str, NewEntity] = dict(pending_new)
    for _, _, _, d, _ in raw:
        entity = d.get("entity")
        if d.get("op") == "set_attribute" and d.get("attribute") == "name" and isinstance(entity, str)                 and entity.startswith(NEW):
            label = entity[len(NEW):]
            types = {x.get("type") for _, _, _, x, _ in raw if x.get("op") == "create_entity" and x.get("entity") == entity}
            for t in types:
                match = by_name.get((t, name_key(str(d["value"]))))
                if match:
                    reused[label] = match
    raw = [r for r in raw if not (r[3].get("op") == "create_entity" and isinstance(r[3].get("entity"), str)
                                  and r[3]["entity"].startswith(NEW) and r[3]["entity"][len(NEW):] in reused)]
    raw = _merge_new_labels(raw)
    taken = set(head.entities) | {r[0] for r in conn.execute("SELECT entity_id FROM new_entities")}
    own = new_entities([r[3] for r in raw], taken)
    new = {**reused, **own}
    items: list[Item] = []
    for order, (doc, index, _, draft, optional) in enumerate(raw):
        draft = resolve(draft, new)
        if doc.axes.visibility is not None and "visibility" not in draft \
                and draft.get("op") not in ("close_entity", "delete_entity", "set_visibility"):
            draft = {**draft, "visibility": doc.axes.visibility.value}  # niveau 1 : en-tête (R-DEC-01)
        try:
            change = parse_change(draft)
        except (ValidationError, ValueError):
            passage_flags.setdefault((doc.doc_id, index), []).append("extraction_error")  # T-ING-17
            continue
        items.append(Item(doc.doc_id, doc.fingerprint, index, order, change, doc.axes.mode, optional))

    supports, proposals = assemble(batch_id, items, head, new)
    others = [p for p in load(world, branch) if p.batch != batch_id]
    _across_batches(proposals, others)
    states = _remembered(world, branch, proposals, report)
    report.supports, report.proposals, report.new_entities = supports, proposals, list(own.values())
    report.flagged = {f"{d} p{i}": f for (d, i), f in sorted(passage_flags.items()) if f}

    with conn:
        for doc_id, vfp, idx in retracted:
            conn.execute("DELETE FROM supports WHERE doc_id = ? AND version_fp = ? AND passage_idx = ?",
                         (doc_id, vfp, idx))
        conn.execute("INSERT INTO batches VALUES (?, ?, ?, ?, (SELECT COUNT(*) FROM batches))",
                     (batch_id, branch, base.seq, base.schema_rev))
        for pos, doc in enumerate(docs):
            conn.execute("INSERT OR IGNORE INTO document_versions VALUES (?, ?, ?, ?)",
                         (doc.doc_id, doc.fingerprint, doc.path, dumps(asdict(doc.axes))))
            conn.execute("INSERT INTO batch_documents VALUES (?, ?, ?, ?)", (batch_id, doc.doc_id, doc.fingerprint, pos))
            for p in doc.passages:
                conn.execute("INSERT OR IGNORE INTO passages VALUES (?, ?, ?, ?, ?, ?)",
                             (doc.doc_id, doc.fingerprint, p.index, p.fingerprint, p.text,
                              dumps(passage_flags.get((doc.doc_id, p.index), []))))
        creators = {q.item.change.entity: p.id for p in proposals for q in p.items
                    if q.item.change.op == "create_entity"}
        for e in own.values():
            conn.execute("INSERT INTO new_entities (batch_id, label, entity_id, type, name, creator)"
                         " VALUES (?, ?, ?, ?, ?, ?)", (batch_id, e.label, e.id, e.type, e.name, creators.get(e.id)))
        for q in supports:
            it = q.item
            for k in q.keys:
                conn.execute("INSERT OR IGNORE INTO supports VALUES (?, ?, ?, ?, ?, ?)",
                             (it.doc_id, it.version_fp, it.passage, dumps(k), dumps(q.value), batch_id))
        for p in proposals:
            edit = Edit(id=p.id, branch=branch, origin=None, tags=["ingestion", batch_id],
                        changes=[q.item.change for q in p.items])
            world.store.record_edit(edit, EditStatus.PENDING, base, frozenset(p.reads), frozenset(p.writes))
            conn.execute("INSERT INTO proposals (edit_id, batch_id, doc_id, version_fp, passage_idx, subject, kind,"
                         " issues) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                         (p.id, batch_id, p.doc_id, p.version_fp, p.passage, p.subject, p.kind, dumps(p.issues)))
            for i, q in enumerate(p.items):
                conn.execute("INSERT INTO proposal_changes (edit_id, idx, fingerprint, tags, detail, state)"
                             " VALUES (?, ?, ?, ?, ?, ?)", (p.id, i, q.fingerprint, dumps(sorted(q.tags)),
                                                            dumps(q.detail), states.get((p.id, i), "open")))
                for k in q.keys:
                    conn.execute("INSERT OR IGNORE INTO proposal_keys VALUES (?, ?, ?, ?)",
                                 (p.id, i, dumps(k), dumps(q.value)))
            for dep in sorted(p.depends_on):
                conn.execute("INSERT INTO proposal_deps VALUES (?, ?)", (p.id, dep))
        for other in others:
            for c in other.changes:
                save_change(world, other.id, c)  # étiquettes « concurrente » ajoutées de l'autre côté
        for p in proposals:
            if all(states.get((p.id, i)) == "refused" for i in range(len(p.items))):
                world.store.update_pending(p.id, status=EditStatus.ABANDONED)
                conn.execute("UPDATE proposals SET closed_reason = 'remembered' WHERE edit_id = ?", (p.id,))
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
