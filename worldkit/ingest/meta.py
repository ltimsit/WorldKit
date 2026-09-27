"""Méta à l'ingestion (J8) : nature d'un passage, classement des changements, fiches, questions de nature.

- **Nature déclarée** (§5.3, R-DEC-01) : un en-tête `diegetic`, `meta_system` ou `meta_sheet` décide pour
  tout le document. Dans un document `mixed`, un marqueur `[meta]` déclare le méta ; un passage fait
  seulement de marqueurs méta est méta, un passage qui mêle marqueur et texte libre admet les deux ; un
  passage sans marqueur est **à déterminer** : diégétique par défaut, la détection peut proposer le méta.
- **Destination d'un changement** (décision J8) : `[meta]` ne dit pas « système » ou « fiche » ; chaque
  changement le dit. Est méta un changement de portée système, qui vise une fiche ou un élément de
  système, ou la forme réduite `sheet_values`. Un changement de schéma de monde est diégétique.
- **Garde de classement** (R-MET-03, décision J8) : la nature déclarée l'emporte ; un changement qui la
  contredit n'est pas proposé et le passage est signalé (`meta_in_diegetic`, `diegetic_in_meta`).
- **Question de nature** (R-DEC-02, décision J8) : dans un passage à déterminer, un changement méta rend
  le passage « nature détectée ». Ses propositions méta sont enregistrées **bloquées** : ni présentées ni
  acceptables tant que l'auteur n'a pas accepté la nature. Refuser clôt ces propositions. La décision est
  tracée par l'empreinte du passage : le même texte ne repose jamais la question (R-PRI-04).
- **Forme réduite d'une fiche** (décision J8) : l'extracteur LLM écrit `sheet_values` (sujet, système,
  valeurs) ; la traduction en changements est déterministe : catégorie lue dans les fiches exigées du
  monde (R-MET-06), identifiant `entité@système`, création de la fiche seulement si elle manque.
"""

from __future__ import annotations

from typing import Any

from worldkit.core.journal.models import EditStatus
from worldkit.core.projection.state import State
from worldkit.core.world import World

from .declaration import DocumentVersion, Nature, Passage

META = {Nature.META_SYSTEM, Nature.META_SHEET}
NATURE_FLAG = "nature_detected"
REFUSED_NATURE = "nature refusée"

DIEGETIC, METAN, BOTH, UNDETERMINED = "diegetic", "meta", "both", "undetermined"


def passage_nature(doc: DocumentVersion, passage: Passage) -> str:
    """Nature déclarée d'un passage : `diegetic`, `meta`, `both` ou `undetermined`."""
    header = doc.axes.nature
    if header is Nature.DIEGETIC:
        return DIEGETIC
    if header in META:
        return METAN
    meta = [s for s in passage.segments if s.declared_by == "marker" and s.nature in META]
    if not meta:
        return UNDETERMINED
    return METAN if len(meta) == len(passage.segments) else BOTH


def _refs(d: dict[str, Any]) -> list[str]:
    out = [d.get(k) for k in ("entity", "from", "to", "value")]
    target = d.get("target")
    if isinstance(target, dict):
        out += [target.get(k) for k in ("entity", "from", "to")]
    return [r for r in out if isinstance(r, str)]


def is_meta(d: dict[str, Any], head: State) -> bool:
    """Le changement va-t-il vers un système ou une fiche ?"""
    if d.get("op") == "sheet_values":
        return True
    if d.get("scope", "world") != "world":
        return True
    if d.get("op") == "create_entity" and d.get("type") == "Sheet":
        return True
    systems = set(head.systems)
    for ref in _refs(d):
        rec = head.entities.get(ref)
        if rec is not None and (rec.sheet is not None or rec.scope != "world"):
            return True
        if ":" in ref and ref.split(":", 1)[0] in systems:
            return True
        if "@" in ref and ref.rsplit("@", 1)[1] in systems:
            return True
    return False


def expand_sheet_values(d: dict[str, Any], head: State, created: dict[tuple[str, str], str]) -> list[dict[str, Any]] | None:
    """`{op: sheet_values, of, system, values, category?}` → changements. `created` : fiches déjà créées
    par le lot, (entité, système) → identifiant. None si la catégorie ne peut être déterminée."""
    of, system, values = d.get("of"), d.get("system"), d.get("values") or {}
    if not isinstance(of, str) or not isinstance(system, str) or not isinstance(values, dict):
        return None
    sheet = next((sid for sid, rec in sorted(head.entities.items())
                  if rec.sheet is not None and not rec.closed and (rec.sheet.of, rec.sheet.system) == (of, system)),
                 None) or created.get((of, system))
    out: list[dict[str, Any]] = []
    if sheet is None:
        category = _category(of, system, head) or d.get("category")
        if not category:
            return None
        sheet = f"{of}@{system}"
        created[(of, system)] = sheet
        out.append({"op": "create_entity", "entity": sheet, "type": "Sheet",
                    "sheet": {"of": of, "system": system, "category": category}})
    for attribute, value in sorted(values.items()):
        if isinstance(value, list):
            out += [{"op": "add_value", "entity": sheet, "attribute": attribute, "value": v} for v in value]
        else:
            out.append({"op": "set_attribute", "entity": sheet, "attribute": attribute, "value": value})
    return out


def _category(of: str, system: str, head: State) -> str | None:
    """Catégorie exigée par le monde pour le type de l'entité (sous-types compris, R-MET-06)."""
    rec = head.entities.get(of)
    if rec is None:
        return None
    ctx = head.context()
    for world_type, category in sorted(ctx.sheet_requirements.get(system, {}).items()):
        if head.world.is_subtype(rec.type, world_type):
            return category
    return None


# ---------------------------------------------------------------------------
# Questions de nature (R-DEC-02)
# ---------------------------------------------------------------------------

def nature_decision(world: World, passage_fp: str, branch: str) -> str | None:
    """`accept_nature`, `refuse_nature`, ou None si la question est ouverte."""
    row = world.store.conn.execute(
        "SELECT action FROM decisions WHERE fingerprint = ? AND branch_id = ? AND action IN"
        " ('accept_nature', 'refuse_nature') ORDER BY decision_id DESC LIMIT 1",
        (f"nature:{passage_fp}", branch)).fetchone()
    return row[0] if row else None


def awaiting_nature(world: World, p: Any) -> bool:
    """Proposition bloquée par une question de nature ouverte (ni présentée ni acceptable)."""
    from .queue import branch_of, passage_fp
    if not any(NATURE_FLAG in c.tags for c in p.changes):
        return False
    return nature_decision(world, passage_fp(world, p.doc, p.version_fp, p.passage), branch_of(world, p)) is None


def open_questions(world: World, branch: str | None = None) -> list[tuple[str, int, str, list[str]]]:
    """Passages dont la nature méta est détectée et pas encore décidée : (document, passage, empreinte, sujets)."""
    from .queue import load, passage_fp
    branch = branch or world.reference_branch
    out: dict[tuple[str, int], tuple[str, set[str]]] = {}
    for p in load(world, branch):
        if any(NATURE_FLAG in c.tags for c in p.changes):
            fp = passage_fp(world, p.doc, p.version_fp, p.passage)
            if nature_decision(world, fp, branch) is None:
                out.setdefault((p.doc, p.passage), (fp, set()))[1].add(p.subject)
    return [(d, i, fp, sorted(s)) for (d, i), (fp, s) in sorted(out.items())]


def decide_nature(world: World, doc: str, passage: int, accept: bool, reason: str | None = None) -> list[str]:
    """Accepter ou refuser la nature méta détectée d'un passage. Rend les propositions concernées :
    débloquées (acceptée) ou closes (refusée)."""
    from .queue import branch_of, close, load, passage_fp
    branch = world.reference_branch
    concerned = [p for p in load(world, branch) if p.doc == doc and p.passage == passage
                 and any(NATURE_FLAG in c.tags for c in p.changes)]
    if not concerned:
        raise KeyError(f"aucune question de nature ouverte pour {doc} p{passage}")
    fp = passage_fp(world, doc, concerned[0].version_fp, passage)
    conn = world.store.conn
    with conn:
        conn.execute("INSERT INTO decisions (fingerprint, doc_id, passage_fp, branch_id, action, reason)"
                     " VALUES (?, ?, ?, ?, ?, ?)", (f"nature:{fp}", doc, fp, branch_of(world, concerned[0]),
                                                   "accept_nature" if accept else "refuse_nature", reason))
        if not accept:
            for p in concerned:
                close(world, p, EditStatus.ABANDONED, REFUSED_NATURE)
    return [p.id for p in concerned]
