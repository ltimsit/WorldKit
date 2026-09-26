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
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from worldkit.core.journal.models import BaseState, Edit, EditStatus
from worldkit.core.projection.serialize import state_to_dict
from worldkit.core.schema.changes import CloseEntity, DeleteEntity, SetVisibility, parse_change
from worldkit.core.world import World
from worldkit.periphery.extraction import Extraction, Extractor

from .declaration import DocumentVersion, Nature, Voice, read_document
from .declaration import normalize
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


def schema_fingerprint(state: Any) -> str:
    d = state_to_dict(state)
    payload = json.dumps([d["world"], d["systems"]], sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def _extract(world: World, extractor: Extractor, doc: DocumentVersion, schema_fp: str,
             report: BatchReport) -> list[tuple[int, Extraction]]:
    out = []
    conn = world.store.conn
    for p in doc.passages:
        row = conn.execute("SELECT payload FROM extraction_cache WHERE passage_fp = ? AND schema_fp = ?"
                           " AND extractor = ?", (p.fingerprint, schema_fp, extractor.version)).fetchone()
        if row is not None:
            d = json.loads(row[0])
            ex = Extraction(tuple(d["drafts"]), frozenset(d["optional"]), tuple(d["claims"]), tuple(d["flags"]),
                            d["nature"])
            report.cached += 1
        else:
            ex = extractor.extract(doc.doc_id, p.text)
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
    docs = [read_document(p) for p in paths]
    if len({d.doc_id for d in docs}) != len(docs):
        raise BatchError("un même document figure deux fois dans le lot")
    report = BatchReport(batch_id, base, [d.doc_id for d in docs], [], [], [])

    # Extraction (ou cache), puis brouillons à résoudre.
    raw: list[tuple[DocumentVersion, int, int, dict[str, Any], bool]] = []
    passage_flags: dict[tuple[str, int], list[str]] = {}
    with conn:
        for doc in docs:
            for index, ex in _extract(world, extractor, doc, schema_fp, report):
                flags = list(ex.flags)
                nature = Nature(ex.nature) if ex.nature in Nature._value2member_map_ else None
                if doc.axes.nature in META or nature in META:
                    flags.append("meta")  # conservé, sans proposition avant J8 (cadre technique §7)
                elif doc.axes.voice is Voice.IN_WORLD:
                    flags.append("in_world")  # affirmations : J3.3
                else:
                    for i, draft in enumerate(ex.drafts):
                        raw.append((doc, index, i, draft, i in ex.optional))
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
                match = by_name.get((t, normalize(str(d["value"])).casefold()))
                if match:
                    reused[label] = match
    raw = [r for r in raw if not (r[3].get("op") == "create_entity" and isinstance(r[3].get("entity"), str)
                                  and r[3]["entity"].startswith(NEW) and r[3]["entity"][len(NEW):] in reused)]
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
    report.supports, report.proposals, report.new_entities = supports, proposals, list(own.values())
    report.flagged = {f"{d} p{i}": f for (d, i), f in sorted(passage_flags.items()) if f}

    with conn:
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
                conn.execute("INSERT INTO proposal_changes (edit_id, idx, fingerprint, tags, detail)"
                             " VALUES (?, ?, ?, ?, ?)", (p.id, i, q.fingerprint, dumps(sorted(q.tags)), dumps(q.detail)))
                for k in q.keys:
                    conn.execute("INSERT OR IGNORE INTO proposal_keys VALUES (?, ?, ?, ?)",
                                 (p.id, i, dumps(k), dumps(q.value)))
            for dep in sorted(p.depends_on):
                conn.execute("INSERT INTO proposal_deps VALUES (?, ?)", (p.id, dep))
        for other in others:
            for c in other.changes:
                save_change(world, other.id, c)  # étiquettes « concurrente » ajoutées de l'autre côté
    return report


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
