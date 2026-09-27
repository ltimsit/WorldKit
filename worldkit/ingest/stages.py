"""Le pipeline d'ingestion en étapes (cadre d'interface §4, I-PIP-01 ; décisions I4).

E1 Déclaration · E2 Passages · E3 Nature · E4 Extraction · E5 Traduction · E6 Classement · E7 Résolution ·
E8 Qualification · E9 Propositions · **E9+ Enregistrer** · E10 Revue · E11 Application · E12 Vues.

- Chaque étape prend l'artefact cumulé (`PipelineArt`) et le complète ; l'artefact se sérialise en JSON
  canonique et se réinjecte à n'importe quelle étape (décision I4 : injecter des brouillons écrits à la main
  en E5, par exemple).
- **E1 à E9 sont des calculs** : ils n'écrivent rien dans le monde (décision I4), à une exception près, le
  cache d'extraction d'E4, mémoire de calcul qui évite de repayer un appel au modèle (T-ING-09).
- **E9+ Enregistrer** est l'écriture du lot : il requalifie la file de revue (T-ING-06), recalcule E9 contre
  elle (concurrence entre lots, mémoire des décisions), puis écrit passages, lot, entités nouvelles, supports
  et propositions. `ingest` = E1 à E8, puis Enregistrer : comportement inchangé (J3 à J8).
- E10 applique un artefact « décisions » (écriture) ; E11 et E12 lisent le journal et les vues.
"""

from __future__ import annotations

import json
import threading
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from worldkit.core.journal.models import BaseState, Edit, EditStatus
from worldkit.core.schema.changes import parse_change
from worldkit.core.world import World
from worldkit.periphery.extraction import Extraction, Extractor
from worldkit.periphery.llm.adapters import LLMError

from .declaration import Axes, DocumentVersion, Mode, Nature, Passage, Segment, Voice, name_key, parse_document
from .meta import DIEGETIC, METAN, NATURE_FLAG, UNDETERMINED, expand_sheet_values, is_meta, passage_nature
from .proposals import NEW, Item, NewEntity, ProposalDraft, Qualified, group, new_entities, qualify_all, resolve
from .queue import StoredProposal, load, name_index, pending_new_entities, refresh, save_change
from .store import dumps, ensure_tables

ART_FORMAT = 1
STAGES = ["E1", "E2", "E3", "E4", "E5", "E6", "E7", "E8", "E9", "E9+", "E10", "E11", "E12"]
STAGE_NAMES = {"E1": "Déclaration", "E2": "Passages", "E3": "Nature", "E4": "Extraction", "E5": "Traduction",
               "E6": "Classement", "E7": "Résolution", "E8": "Qualification", "E9": "Propositions",
               "E9+": "Enregistrer", "E10": "Revue", "E11": "Application", "E12": "Vues"}
WRITES = {"E9+", "E10"}


class StageError(ValueError):
    pass


# ---------------------------------------------------------------------------
# Artefacts
# ---------------------------------------------------------------------------

class _Art(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PassageArt(_Art):
    index: int
    fingerprint: str
    text: str
    segments: list[dict[str, Any]] = Field(default_factory=list)
    nature: str | None = None            # E3 : nature déclarée (diegetic, meta, both, undetermined)
    unchanged: bool = False              # E3 : déjà ingéré pour ce document : ni extrait ni reproposé
    extraction: dict[str, Any] | None = None  # E4 : drafts, optional, claims, flags, nature
    source: str | None = None            # E4 : cache | extracted | error | cap | injected
    drafts: list[dict[str, Any]] | None = None  # E5 : [{draft, optional}]
    flags: list[str] = Field(default_factory=list)


class DocumentArt(_Art):
    doc_id: str
    path: str
    fingerprint: str
    title: str | None = None
    axes: dict[str, Any]
    text: str
    obsolete: bool = False
    passages: list[PassageArt] = Field(default_factory=list)


class Counters(_Art):
    extracted: int = 0
    cached: int = 0
    unchanged: int = 0
    removed: int = 0
    remembered: int = 0
    llm_calls: int = 0
    capped: int = 0
    errors: dict[str, str] = Field(default_factory=dict)


class PipelineArt(_Art):
    """Artefact cumulé : chaque étape y ajoute sa sortie (JSON canonique, I-PIP-01)."""

    format: int = ART_FORMAT
    batch_id: str
    branch: str
    base: dict[str, Any]
    schema_fp: str = ""
    extractor: str | None = None
    stage: str = ""                          # dernière étape faite
    documents: list[DocumentArt] = Field(default_factory=list)
    retracted: list[list[Any]] = Field(default_factory=list)          # E3 : (doc, version, passage)
    raw: list[dict[str, Any]] = Field(default_factory=list)            # E6
    new_entities: list[dict[str, Any]] = Field(default_factory=list)   # E7 : {label, id, type, name, own}
    items: list[dict[str, Any]] = Field(default_factory=list)          # E7
    qualified: list[dict[str, Any]] = Field(default_factory=list)      # E8
    supports: list[dict[str, Any]] = Field(default_factory=list)       # E9
    proposals: list[dict[str, Any]] = Field(default_factory=list)      # E9
    states: dict[str, str] = Field(default_factory=dict)               # E9 : « proposition|i » → refused
    decisions: list[dict[str, Any]] = Field(default_factory=list)      # E10 (entrée)
    decided: list[dict[str, Any]] = Field(default_factory=list)        # E10 (sortie)
    applied: list[dict[str, Any]] = Field(default_factory=list)        # E11
    views: dict[str, Any] = Field(default_factory=dict)                # E12
    written: bool = False                                              # E9+ fait
    counters: Counters = Field(default_factory=Counters)

    def to_json(self) -> str:
        return json.dumps(self.model_dump(mode="json"), ensure_ascii=False, sort_keys=True, indent=1)

    def flagged(self) -> dict[str, list[str]]:
        return {f"{d.doc_id} p{p.index}": p.flags for d in self.documents for p in d.passages if p.flags}

    def live(self) -> list[DocumentArt]:
        return [d for d in self.documents if not d.obsolete]


# --- Conversions artefact ↔ objets du domaine (aller-retour fidèle, testé) ---

def _tup(x: Any) -> Any:
    return tuple(_tup(i) for i in x) if isinstance(x, list) else x


def _jsonable(x: Any) -> Any:
    if isinstance(x, tuple):
        return [_jsonable(i) for i in x]
    if isinstance(x, list):
        return [_jsonable(i) for i in x]
    if isinstance(x, dict):
        return {k: _jsonable(v) for k, v in x.items()}
    return x


def change_dict(c: Any) -> dict[str, Any]:
    return c.model_dump(mode="json", by_alias=True, exclude_none=True)


def axes_of(d: dict[str, Any]) -> Axes:
    from worldkit.core.schema import Visibility
    return Axes(Mode(d["mode"]), Nature(d["nature"]), Voice(d["voice"]), d.get("speaker"),
                Visibility(d["visibility"]) if d.get("visibility") else None)


def doc_of(art: DocumentArt) -> DocumentVersion:
    axes = axes_of(art.axes)
    passages = tuple(Passage(p.index, p.text, p.fingerprint, tuple(
        Segment(s["text"], Voice(s["voice"]), s.get("speaker"), Nature(s["nature"]), s["declared_by"])
        for s in p.segments)) for p in art.passages)
    return DocumentVersion(art.doc_id, art.path, art.fingerprint, axes, passages, art.title)


def item_dict(it: Item) -> dict[str, Any]:
    return {"doc_id": it.doc_id, "version_fp": it.version_fp, "passage": it.passage, "order": it.order,
            "change": change_dict(it.change), "mode": str(it.mode), "optional": it.optional,
            "awaiting_nature": it.awaiting_nature}


def item_of(d: dict[str, Any]) -> Item:
    return Item(d["doc_id"], d["version_fp"], d["passage"], d["order"], parse_change(d["change"]), Mode(d["mode"]),
                d.get("optional", False), d.get("awaiting_nature", False))


def qualified_dict(q: Qualified) -> dict[str, Any]:
    return {"item": item_dict(q.item), "keys": _jsonable(q.keys), "value": _jsonable(q.value),
            "tags": sorted(q.tags), "detail": _jsonable(q.detail), "fingerprint": q.fingerprint}


def qualified_of(d: dict[str, Any]) -> Qualified:
    return Qualified(item_of(d["item"]), [_tup(k) for k in d["keys"]], _tup(d["value"]), set(d["tags"]),
                     dict(d["detail"]), d["fingerprint"])


def proposal_dict(p: ProposalDraft) -> dict[str, Any]:
    return {"id": p.id, "doc_id": p.doc_id, "version_fp": p.version_fp, "passage": p.passage, "subject": p.subject,
            "kind": p.kind, "items": [qualified_dict(q) for q in p.items], "issues": list(p.issues),
            "reads": sorted(_jsonable(list(p.reads)), key=repr), "writes": sorted(_jsonable(list(p.writes)), key=repr),
            "depends_on": sorted(p.depends_on)}


def proposal_of(d: dict[str, Any]) -> ProposalDraft:
    return ProposalDraft(d["id"], d["doc_id"], d["version_fp"], d["passage"], d["subject"], d["kind"],
                         [qualified_of(q) for q in d["items"]], list(d["issues"]),
                         {_tup(k) for k in d["reads"]}, {_tup(k) for k in d["writes"]}, set(d["depends_on"]))


def new_of(d: dict[str, Any]) -> NewEntity:
    return NewEntity(d["label"], d["id"], d["type"], d.get("name"))


# ---------------------------------------------------------------------------
# Contexte d'exécution
# ---------------------------------------------------------------------------

@dataclass
class Run:
    """Ce dont les étapes ont besoin : le monde, l'extracteur, la progression, l'arrêt, le plafond (I-LLM-01)."""

    world: World
    extractor: Extractor | None = None
    max_calls: int | None = None
    progress: Callable[[str, dict[str, Any]], None] = lambda stage, info: None
    cancel: threading.Event = field(default_factory=threading.Event)
    _head: Any = None

    def head(self, art: PipelineArt) -> Any:
        if self._head is None or self._head.branch != art.branch:
            self._head = self.world.state(art.branch)
        return self._head


def start(world: World, batch_id: str, branch: str | None = None) -> PipelineArt:
    """Artefact vide, base = tête de la branche (T-ING-07 : le lot a une base unique)."""
    from .batch import schema_fingerprint
    ensure_tables(world.store.conn)
    branch = branch or world.reference_branch
    head = world.state(branch)
    return PipelineArt(batch_id=batch_id, branch=branch,
                       base={"branch": branch, "seq": head.seq, "schema_rev": head.schema_rev},
                       schema_fp=schema_fingerprint(head))


# ---------------------------------------------------------------------------
# E1 à E3 : déclaration, passages, nature
# ---------------------------------------------------------------------------

def e1_declare(run: Run, art: PipelineArt, paths: list[str | Path]) -> PipelineArt:
    """Documents et en-têtes (R-DOC-02, R-ING-01) ; documents obsolètes marqués (R-DOC-05)."""
    head = run.head(art)
    docs = []
    for p in paths:
        text = Path(p).read_text(encoding="utf-8")
        doc = parse_document(text, str(p))
        docs.append(DocumentArt(doc_id=doc.doc_id, path=doc.path, fingerprint=doc.fingerprint, title=doc.title,
                                axes=asdict(doc.axes), text=text,
                                obsolete=bool(head.obsolete_documents.get(doc.doc_id))))
    if len({d.doc_id for d in docs}) != len(docs):
        raise StageError("un même document figure deux fois dans le lot")
    art.documents = docs
    return _done(art, "E1")


def e2_passages(run: Run, art: PipelineArt) -> PipelineArt:
    """Passages déterministes, identifiés par empreinte ; segments des marqueurs (T-ING-10, R-DEC-01)."""
    for d in art.documents:
        doc = parse_document(d.text, d.path)
        d.passages = [PassageArt(index=p.index, fingerprint=p.fingerprint, text=p.text,
                                 segments=[asdict(s) for s in p.segments]) for p in doc.passages]
    return _done(art, "E2")


def e3_nature(run: Run, art: PipelineArt) -> PipelineArt:
    """Nature déclarée de chaque passage (R-DEC-04) ; passages déjà ingérés, passages retirés (T-ING-10)."""
    from .batch import _known_passages
    art.retracted = []
    art.counters.removed = 0
    for d in art.live():
        doc = doc_of(d)
        known = _known_passages(run.world, art.branch, d.doc_id)
        current = {p.fingerprint for p in d.passages}
        for fp, places in known.items():
            if fp not in current:  # passage supprimé ou modifié : ses supports seront retirés (T-ING-11)
                art.retracted += [[d.doc_id, vfp, idx] for vfp, idx in places]
                art.counters.removed += 1
        for p, dp in zip(d.passages, doc.passages):
            p.nature = passage_nature(doc, dp)
            p.unchanged = p.fingerprint in known
    return _done(art, "E3")


# ---------------------------------------------------------------------------
# E4 : extraction (cache, plafond, arrêt, progression)
# ---------------------------------------------------------------------------

def missing_from_cache(run: Run, art: PipelineArt) -> list[tuple[str, int]]:
    """Passages qu'E4 enverrait à l'extracteur : ni déjà ingérés, ni en cache pour ce schéma et cet extracteur
    (estimation exacte du coût, I-LLM-01)."""
    assert run.extractor is not None
    conn = run.world.store.conn
    ensure_tables(conn)
    out = []
    for d in art.live():
        for p in d.passages:
            if p.unchanged:
                continue
            row = conn.execute("SELECT 1 FROM extraction_cache WHERE passage_fp = ? AND schema_fp = ? AND extractor = ?",
                               (p.fingerprint, art.schema_fp, run.extractor.version)).fetchone()
            if row is None:
                out.append((d.doc_id, p.index))
    return out


def e4_extract(run: Run, art: PipelineArt) -> PipelineArt:
    """Extraction, ou relecture du cache (T-ING-09) ; erreurs jamais proposées (T-ING-17) ; au plus
    `max_calls` appels à l'extracteur, les passages restants marqués « plafond atteint » (I-LLM-01)."""
    from concurrent.futures import ThreadPoolExecutor
    from .batch import passage_context
    if run.extractor is None:
        raise StageError("E4 demande un extracteur (oracle ou profil de modèle)")
    from .batch import extraction_context
    head = run.head(art)
    context = extraction_context(run.world, head)
    conn = run.world.store.conn
    ext = run.extractor
    art.extractor = ext.version
    c = art.counters
    todo: list[tuple[DocumentArt, PassageArt]] = []
    twins: list[PassageArt] = []  # même texte qu'un passage déjà à extraire : relu comme en cache, un seul appel
    pending: set[str] = set()
    for d in art.live():
        for p in d.passages:
            if p.unchanged:
                c.unchanged += 1
                continue
            row = conn.execute("SELECT payload FROM extraction_cache WHERE passage_fp = ? AND schema_fp = ?"
                               " AND extractor = ?", (p.fingerprint, art.schema_fp, ext.version)).fetchone()
            if row is not None:
                p.extraction, p.source = json.loads(row[0]), "cache"
                c.cached += 1
            elif p.fingerprint in pending:
                twins.append(p)
            else:
                pending.add(p.fingerprint)
                todo.append((d, p))
    if run.max_calls is not None and len(todo) > run.max_calls:
        for d, p in todo[run.max_calls:]:
            p.source = "cap"
            _flag(p.flags, "cap_reached")
            c.capped += 1
        todo = todo[:run.max_calls]
    workers = max(1, int(getattr(ext, "concurrency", 1)))
    total, done = len(todo), 0

    def one(item: tuple[DocumentArt, PassageArt]) -> Extraction | LLMError:
        d, p = item
        try:
            return ext.extract(d.doc_id, p.text, passage_context(context, doc_of(d), doc_of(d).passages[p.index - 1]))
        except LLMError as e:
            return e

    run.progress("E4", {"done": 0, "total": total})
    for start_at in range(0, total, workers):
        if run.cancel.is_set():
            for d, p in todo[start_at:]:
                p.source = "cancelled"
                _flag(p.flags, "cancelled")
            break
        chunk = todo[start_at:start_at + workers]
        with ThreadPoolExecutor(max_workers=workers) as pool:
            results = list(pool.map(one, chunk)) if len(chunk) > 1 else [one(chunk[0])]
        with conn:
            for (d, p), ex in zip(chunk, results):
                if isinstance(ex, LLMError):  # T-ING-17 : erreur d'extraction, jamais une proposition ; non mise en cache
                    c.errors[f"{d.doc_id} p{p.index}"] = str(ex)
                    p.extraction, p.source = asdict(Extraction(flags=("extraction_error",))), "error"
                    p.extraction["optional"] = []
                    continue
                payload = {**asdict(ex), "optional": sorted(ex.optional)}
                conn.execute("INSERT OR IGNORE INTO extraction_cache VALUES (?, ?, ?, ?)",
                             (p.fingerprint, art.schema_fp, ext.version, dumps(payload)))
                p.extraction, p.source = _jsonable(payload), "extracted"  # ordre de l'extracteur gardé
                c.extracted += 1
                if not ext.version.startswith("oracle"):
                    c.llm_calls += 1
        done += len(chunk)
        run.progress("E4", {"done": done, "total": total, "calls": c.llm_calls})
    extracted = {p.fingerprint: p for _, p in todo if p.source == "extracted"}
    for p in twins:
        if p.fingerprint in extracted:
            p.extraction, p.source = extracted[p.fingerprint].extraction, "cache"
            c.cached += 1
    for d in art.live():
        for p in d.passages:
            if p.extraction is not None:
                for f in p.extraction.get("flags", []):
                    _flag(p.flags, f)
    return _done(art, "E4")


def _extraction(p: PassageArt) -> Extraction:
    e = p.extraction or {}
    return Extraction(tuple(e.get("drafts", ())), frozenset(e.get("optional", ())), tuple(e.get("claims", ())),
                      tuple(e.get("flags", ())), e.get("nature"))


# ---------------------------------------------------------------------------
# E5 à E7 : traduction, classement, résolution
# ---------------------------------------------------------------------------

def e5_translate(run: Run, art: PipelineArt) -> PipelineArt:
    """Formes réduites `sheet_values` traduites de façon déterministe (T-ING-20)."""
    head = run.head(art)
    sheets: dict[tuple[str, str], str] = {}
    for d in art.live():
        for p in d.passages:
            if p.unchanged or p.extraction is None:
                continue
            ex = _extraction(p)
            out: list[dict[str, Any]] = []
            for i, draft in enumerate(ex.drafts):
                if draft.get("op") != "sheet_values":
                    out.append({"draft": draft, "optional": i in ex.optional})
                    continue
                changes = expand_sheet_values(draft, head, sheets)
                if changes is None:  # sujet inconnu ou catégorie introuvable : sortie inexploitable (T-ING-17)
                    _flag(p.flags, "extraction_error")
                    continue
                out += [{"draft": ch, "optional": i in ex.optional} for ch in changes]
            p.drafts = out
    return _done(art, "E5")


def e6_classify(run: Run, art: PipelineArt) -> PipelineArt:
    """Garde de classement (R-DEC-01, R-DEC-05, R-MET-03), questions de nature (R-DEC-02), affirmations
    (R-DOC-06) ; ordre du lot préservé."""
    head = run.head(art)
    raw: list[dict[str, Any]] = []
    for d in art.live():
        doc = doc_of(d)
        for p, dp in zip(d.passages, doc.passages):
            if p.unchanged or p.extraction is None:
                continue
            ex = _extraction(p)
            count = lambda: sum(1 for r in raw if r["doc_id"] == d.doc_id and r["passage"] == p.index)  # noqa: E731
            if doc.axes.voice is not Voice.IN_WORLD:  # en in_world, le contenu n'établit pas de faits
                for entry in p.drafts or []:
                    draft = entry["draft"]
                    meta = is_meta(draft, head)
                    if p.nature == DIEGETIC and meta:
                        _flag(p.flags, "meta_in_diegetic")
                        continue
                    if p.nature == METAN and not meta:
                        _flag(p.flags, "diegetic_in_meta")
                        continue
                    awaiting = p.nature == UNDETERMINED and meta
                    if awaiting:
                        _flag(p.flags, NATURE_FLAG)
                    raw.append({"doc_id": d.doc_id, "passage": p.index, "i": count(), "draft": draft,
                                "optional": entry["optional"], "awaiting": awaiting})
            speakers = dp.speakers()
            for n, claim in enumerate(ex.claims, start=1):
                speaker = claim.get("speaker") or (speakers[0] if speakers else doc.axes.speaker)
                if speaker is None:
                    continue  # une affirmation a un énonciateur (R-DOC-02)
                raw.append({"doc_id": d.doc_id, "passage": p.index, "i": count(), "optional": False, "awaiting": False,
                            "draft": {"op": "add_claim", "claim": f"{d.doc_id}.p{p.index}.c{n}", "document": d.doc_id,
                                      "speaker": speaker, "text": claim["text"], "claimed": claim.get("claimed")}})
    art.raw = raw
    return _done(art, "E6")


def e7_resolve(run: Run, art: PipelineArt) -> PipelineArt:
    """Entités nouvelles regroupées au niveau du lot, créations en attente reprises (T-ING-07) ; notoriété de
    l'en-tête (R-DEC-01) ; brouillon invalide → erreur d'extraction (T-ING-17)."""
    from .batch import _merge_new_labels
    world, head = run.world, run.head(art)
    docs = {d.doc_id: d for d in art.live()}
    raw = [(r["doc_id"], r["passage"], r["i"], r["draft"], r["optional"]) for r in art.raw]
    awaiting = {(r["doc_id"], r["passage"], r["i"]) for r in art.raw if r["awaiting"]}
    pending_new = pending_new_entities(world, head)
    by_name = name_index(pending_new)
    reused: dict[str, NewEntity] = dict(pending_new)
    for _, _, _, d, _ in raw:
        entity = d.get("entity")
        if d.get("op") == "set_attribute" and d.get("attribute") == "name" and isinstance(entity, str) \
                and entity.startswith(NEW):
            label = entity[len(NEW):]
            types = {x.get("type") for _, _, _, x, _ in raw if x.get("op") == "create_entity" and x.get("entity") == entity}
            for t in types:
                match = by_name.get((t, name_key(str(d["value"]))))
                if match:
                    reused[label] = match
    raw = [r for r in raw if not (r[3].get("op") == "create_entity" and isinstance(r[3].get("entity"), str)
                                  and r[3]["entity"].startswith(NEW) and r[3]["entity"][len(NEW):] in reused)]
    raw = _merge_new_labels(raw)
    taken = set(head.entities) | {r[0] for r in world.store.conn.execute("SELECT entity_id FROM new_entities")}
    own = new_entities([r[3] for r in raw], taken)
    new = {**reused, **own}
    items: list[dict[str, Any]] = []
    for order, (doc_id, index, i, draft, optional) in enumerate(raw):
        d = docs[doc_id]
        axes = axes_of(d.axes)
        draft = resolve(draft, new)
        if axes.visibility is not None and "visibility" not in draft \
                and draft.get("op") not in ("close_entity", "delete_entity", "set_visibility"):
            draft = {**draft, "visibility": axes.visibility.value}  # niveau 1 : en-tête (R-DEC-01)
        try:
            change = parse_change(draft)
        except (ValidationError, ValueError):
            passage = next(p for p in d.passages if p.index == index)
            passage.flags.append("extraction_error")  # T-ING-17
            continue
        items.append(item_dict(Item(doc_id, d.fingerprint, index, order, change, axes.mode, optional,
                                    (doc_id, index, i) in awaiting)))
    art.items = items
    art.new_entities = [{**asdict(e), "own": label in own} for label, e in new.items()]
    return _done(art, "E7")


def _new(art: PipelineArt) -> dict[str, NewEntity]:
    return {e["label"]: new_of(e) for e in art.new_entities}


# ---------------------------------------------------------------------------
# E8, E9 : qualification, propositions
# ---------------------------------------------------------------------------

def e8_qualify(run: Run, art: PipelineArt) -> PipelineArt:
    """Étiquettes, clés, supports, contradictions internes et du lot, empreintes (T-ING-02 à T-ING-08)."""
    items = [item_of(i) for i in art.items]
    art.qualified = [qualified_dict(q) for q in qualify_all(items, run.head(art), _new(art))]
    return _done(art, "E8")


def _cross(run: Run, art: PipelineArt, proposals: list[ProposalDraft]) -> tuple[list[StoredProposal], dict[tuple[str, int], str]]:
    """Face aux propositions en attente des autres lots (T-ING-18, T-ING-05) et à la mémoire des décisions
    (T-ING-08, R-PRI-04)."""
    from .batch import _across_batches, _remembered

    class _Report:
        remembered = 0
    others = [p for p in load(run.world, art.branch) if p.batch != art.batch_id]
    _across_batches(proposals, others)
    report = _Report()
    states = _remembered(run.world, art.branch, proposals, report)  # type: ignore[arg-type]
    art.counters.remembered = report.remembered
    return others, states


def e9_propose(run: Run, art: PipelineArt) -> PipelineArt:
    """Propositions par passage et sujet, dépendances ; aperçu de la concurrence avec la file telle qu'elle est
    (sans la requalifier : c'est l'affaire d'Enregistrer)."""
    qualified = [qualified_of(q) for q in art.qualified]
    supports, proposals = group(art.batch_id, qualified, run.head(art), _new(art))
    _, states = _cross(run, art, proposals)
    art.supports = [qualified_dict(q) for q in supports]
    art.proposals = [proposal_dict(p) for p in proposals]
    art.states = {f"{pid}|{i}": s for (pid, i), s in states.items()}
    return _done(art, "E9")


# ---------------------------------------------------------------------------
# E9+ : enregistrer le lot (écriture)
# ---------------------------------------------------------------------------

def e9_save(run: Run, art: PipelineArt) -> PipelineArt:
    """L'écriture du lot : requalification de la file (T-ING-06), E9 recalculé contre elle, puis passages, lot,
    entités nouvelles, supports, propositions (T-ING-01). Rien avant : E1 à E9 sont des calculs."""
    world, conn = run.world, run.world.store.conn
    ensure_tables(conn)
    if conn.execute("SELECT 1 FROM batches WHERE batch_id = ?", (art.batch_id,)).fetchone():
        raise StageError(f"lot déjà ingéré : {art.batch_id}")
    if art.written:
        raise StageError("artefact déjà enregistré")
    refresh(world, art.branch)
    head = world.state(art.branch)
    base = BaseState(branch=art.branch, seq=head.seq, schema_rev=head.schema_rev)
    qualified = [qualified_of(q) for q in art.qualified]
    new = _new(art)
    supports, proposals = group(art.batch_id, qualified, head, new)
    others, states = _cross(run, art, proposals)
    own = [new_of(e) for e in art.new_entities if e.get("own")]
    docs = art.live()
    with conn:
        for doc_id, vfp, idx in art.retracted:
            conn.execute("DELETE FROM supports WHERE doc_id = ? AND version_fp = ? AND passage_idx = ?",
                         (doc_id, vfp, idx))
        conn.execute("INSERT INTO batches VALUES (?, ?, ?, ?, (SELECT COUNT(*) FROM batches))",
                     (art.batch_id, art.branch, base.seq, base.schema_rev))
        for pos, d in enumerate(docs):
            conn.execute("INSERT OR IGNORE INTO document_versions VALUES (?, ?, ?, ?)",
                         (d.doc_id, d.fingerprint, d.path, dumps(asdict(axes_of(d.axes)))))
            conn.execute("INSERT INTO batch_documents VALUES (?, ?, ?, ?)", (art.batch_id, d.doc_id, d.fingerprint, pos))
            for p in d.passages:
                conn.execute("INSERT OR IGNORE INTO passages VALUES (?, ?, ?, ?, ?, ?)",
                             (d.doc_id, d.fingerprint, p.index, p.fingerprint, p.text, dumps(_saved_flags(p))))
        creators = {q.item.change.entity: p.id for p in proposals for q in p.items
                    if q.item.change.op == "create_entity"}
        for e in own:
            conn.execute("INSERT INTO new_entities (batch_id, label, entity_id, type, name, creator)"
                         " VALUES (?, ?, ?, ?, ?, ?)", (art.batch_id, e.label, e.id, e.type, e.name, creators.get(e.id)))
        for q in supports:
            it = q.item
            for k in q.keys:
                conn.execute("INSERT OR IGNORE INTO supports VALUES (?, ?, ?, ?, ?, ?)",
                             (it.doc_id, it.version_fp, it.passage, dumps(k), dumps(q.value), art.batch_id))
        for p in proposals:
            edit = Edit(id=p.id, branch=art.branch, origin=None, tags=["ingestion", art.batch_id],
                        changes=[q.item.change for q in p.items])
            world.store.record_edit(edit, EditStatus.PENDING, base, frozenset(p.reads), frozenset(p.writes))
            conn.execute("INSERT INTO proposals (edit_id, batch_id, doc_id, version_fp, passage_idx, subject, kind,"
                         " issues) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                         (p.id, art.batch_id, p.doc_id, p.version_fp, p.passage, p.subject, p.kind, dumps(p.issues)))
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
            for ch in other.changes:
                save_change(world, other.id, ch)  # étiquettes « concurrente » ajoutées de l'autre côté
        for p in proposals:
            if all(states.get((p.id, i)) == "refused" for i in range(len(p.items))):
                world.store.update_pending(p.id, status=EditStatus.ABANDONED)
                conn.execute("UPDATE proposals SET closed_reason = 'remembered' WHERE edit_id = ?", (p.id,))
    art.base = {"branch": base.branch, "seq": base.seq, "schema_rev": base.schema_rev}
    art.supports = [qualified_dict(q) for q in supports]
    art.proposals = [proposal_dict(p) for p in proposals]
    art.states = {f"{pid}|{i}": s for (pid, i), s in states.items()}
    art.written = True
    return _done(art, "E9+")


def _saved_flags(p: PassageArt) -> list[str]:
    """Drapeaux enregistrés d'un passage : ceux de l'extraction, puis ceux des étapes (ordre d'origine)."""
    return list(p.flags)


# ---------------------------------------------------------------------------
# E10 à E12 : revue, application, vues
# ---------------------------------------------------------------------------

def e10_review(run: Run, art: PipelineArt) -> PipelineArt:
    """Décisions scriptées (artefact « décisions ») : accept, refuse, nature, qualify, promote, abandon."""
    from . import decide
    from .meta import decide_nature
    out = []
    for d in art.decisions:
        action = d.get("action")
        if action == "nature":
            ids = decide_nature(run.world, d["document"], int(d["passage"]), d.get("decision") == "accept",
                                d.get("reason"))
            out.append({"action": "nature", "document": d["document"], "passage": d["passage"],
                        "decision": d.get("decision"), "proposals": ids, "ok": True})
            continue
        pid = d.get("proposal", "")
        if action == "accept":
            r = decide.accept(run.world, pid, d.get("keep"), d.get("drop_optional", False), d.get("reason"))
        elif action == "refuse":
            r = decide.refuse(run.world, pid, d.get("changes"), d.get("reason"))
        elif action == "qualify":
            r = decide.qualify(run.world, pid, str(d["value"]).lower(), d.get("visibility"), d.get("reason"))
        elif action == "promote":
            r = decide.promote(run.world, pid, d.get("visibility"), d.get("reason"))
        elif action == "abandon":
            r = decide.abandon(run.world, pid, d.get("reason"))
        else:
            raise StageError(f"décision inconnue : {action} (accept, refuse, nature, qualify, promote, abandon)")
        out.append({"action": action, "proposal": pid, "edit": r.edit_id, "seq": r.seq, "ok": r.ok,
                    "issues": [str(i) for i in r.issues]})
    art.decided = out
    return _done(art, "E10")


def e11_apply(run: Run, art: PipelineArt) -> PipelineArt:
    """Éditions appliquées depuis la base du lot (lecture du journal, R-HIS-02)."""
    seq = int(art.base.get("seq", 0))
    rows = []
    for s, edit_id in run.world.store.journal_ids(art.branch, after=seq):
        e = run.world.store.edit(edit_id).edit
        rows.append({"seq": s, "edit": edit_id, "origin": e.origin, "changes": len(e.changes)})
    art.applied = rows
    return _done(art, "E11")


def e12_views(run: Run, art: PipelineArt) -> PipelineArt:
    """Signalements de l'état et pages des entités touchées par le lot (R-VUE-01, R-CON-04)."""
    from worldkit.core.views import state_report
    state = run.world.state(art.branch)
    touched = sorted({q["item"]["change"].get("entity") or q["item"]["change"].get("from")
                      for p in art.proposals for q in p["items"]} - {None})
    art.views = {"seq": state.seq, "signals": [str(i) for i in state_report(state)],
                 "pages": [e for e in touched if e in state.entities]}
    return _done(art, "E12")


STEP: dict[str, Callable[..., PipelineArt]] = {
    "E2": e2_passages, "E3": e3_nature, "E4": e4_extract, "E5": e5_translate, "E6": e6_classify,
    "E7": e7_resolve, "E8": e8_qualify, "E9": e9_propose, "E9+": e9_save, "E10": e10_review, "E11": e11_apply,
    "E12": e12_views,
}


def _flag(flags: list[str], flag: str) -> None:
    if flag not in flags:
        flags.append(flag)


def _done(art: PipelineArt, stage: str) -> PipelineArt:
    art.stage = stage
    return art


def run_range(run: Run, art: PipelineArt, first: str, last: str, paths: list[str | Path] | None = None,
              on_stage: Callable[[str, PipelineArt], None] | None = None) -> PipelineArt:
    """Exécute les étapes de `first` à `last` sur l'artefact ; `on_stage` reçoit l'artefact après chaque étape."""
    i, j = STAGES.index(first), STAGES.index(last)
    if i > j:
        raise StageError(f"{first} vient après {last}")
    for stage in STAGES[i:j + 1]:
        if run.cancel.is_set():
            break
        run.progress(stage, {})
        if stage == "E1":
            if not paths:
                raise StageError("E1 demande des documents")
            art = e1_declare(run, art, paths)
        else:
            art = STEP[stage](run, art)
        if on_stage is not None:
            on_stage(stage, art)
    return art
