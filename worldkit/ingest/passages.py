"""Ce que disent les documents : les passages qui nomment chaque entité (R-VUE-05, T-ING-21).

Niveau 1 du chantier « ingérer plus que les faits » (*chantier-ingestion.md* §10.6) : sans modèle, sans écriture.

- **Documents** : la dernière version de chaque document passé par un lot visible de la branche (sa lignée, R-HIS-02),
  ouvert au plus tard au point de la vue. Les sources d'atelier non proposées et les anciennes versions n'entrent pas ;
  un document obsolète reste, marqué (R-DOC-05, R-PRI-01).
- **Liens** : les noms et alias de l'état trouvés dans le texte, comme C1a (`known_mentions` : sans casse, texte barré
  écarté, « le baron » quand un seul porte le titre), et les formes courtes des personnes (« Ysolde » pour Ysolde
  Marcastel, sauf un mot porté par deux personnes : choix 40), puis corrigés par l'atelier : une décision de l'auteur sur une
  portion l'emporte (gardée ou corrigée : le lien qu'il a dit ; retirée ou ignorée : aucun lien) ; les règles
  d'atelier de la branche s'appliquent (`not_entity`, `not_entity_of`).
- **À vérifier** : une forme courte, ou une occurrence dont la casse diffère du nom connu (« une brume épaisse » pour
  Brume, « corbelle » dans des notes brouillon), est montrée, signalée sans décider (X-012, `check_of`) ; une décision
  de l'auteur ou un alias la rend sûre.
- **Repère** : capté (le passage soutient un fait de l'entité présent dans l'état, table `supports`), non capté, ou
  affirmation (document en jeu, R-DOC-06).

Tout est trié : l'ordre des documents et des lots ne change rien (R-PRI-03).
"""

from __future__ import annotations

import json
import re
from types import SimpleNamespace
from typing import Any

from worldkit.core.views import PassageLine, PassageStatus


def _documents(world: Any, state: Any) -> list[tuple[str, str, str]]:
    """(document, version, lot) : dernière version de chaque document des lots visibles au point de la vue."""
    conn = world.store.conn
    allowed = {b: hi for b, _, hi in world.store.segments(state.branch)}
    batches = {}
    for batch_id, branch, base_seq, opened in conn.execute(
            "SELECT batch_id, branch_id, base_seq, opened FROM batches"):
        if branch in allowed and (allowed[branch] is None or base_seq <= allowed[branch]) and base_seq <= state.seq:
            batches[batch_id] = opened
    latest: dict[str, tuple[int, str, str]] = {}
    for batch_id, doc_id, vfp in conn.execute("SELECT batch_id, doc_id, version_fp FROM batch_documents"):
        if batch_id in batches and (doc_id not in latest or batches[batch_id] > latest[doc_id][0]):
            latest[doc_id] = (batches[batch_id], vfp, batch_id)
    return [(doc, vfp, batch) for doc, (_, vfp, batch) in sorted(latest.items())]


def _window(doc_id: str, rows: list[tuple[int, str]]) -> Any:
    """Fenêtre d'un document lu dans la table des passages : même assemblage que `window_of`, sans titre."""
    from worldkit.periphery.mentions import Window
    text, spans = "", []
    for idx, ptext in rows:
        start = len(text)
        text += ptext
        spans.append((idx, start, len(text)))
        text += "\n\n"
    text = text.rstrip()
    struck = tuple((m.start(), m.end()) for m in re.finditer(r"~~.+?~~", text, re.DOTALL))
    return Window(doc_id, text, tuple(spans), dict(rows), struck)


def _new_entities(world: Any, doc: Any) -> dict[str, str]:
    """Étiquette d'une entité nouvelle de l'atelier → identifiant créé par son lot (« bertrand-ostrel »)."""
    from worldkit.atelier.propose import batch_id_of
    rows = world.store.conn.execute("SELECT label, entity_id FROM new_entities WHERE batch_id = ?",
                                    (batch_id_of(doc),)).fetchall()
    return {label.removeprefix("new:").replace(" ", "-"): eid for label, eid in rows}


def _fact_label(fact: Any) -> str:
    if fact.kind == "rel":
        return f"{fact.name}({fact.subject}, {fact.target})"
    if fact.kind == "value":
        return f"{fact.subject}.{fact.name} += {fact.value}"
    return f"{fact.subject}.{fact.name}"


def passages_by_entity(world: Any, state: Any) -> dict[str, list[PassageLine]]:
    """Pour chaque entité de l'état, les passages des documents ingérés qui la nomment (R-VUE-05)."""
    from worldkit.atelier import layers
    from worldkit.atelier import store as atelier
    from worldkit.atelier.propose import _label
    from worldkit.periphery.matching import fold
    from worldkit.periphery.mentions import Resolver, check_of, known_mentions, short_forms

    from .batch import extraction_context
    from .store import loads_key

    conn = world.store.conn
    atelier.ensure_tables(conn)
    context = extraction_context(world, state)
    entities = tuple(e for e in context.entities if e.id in state.entities)
    names = {e.id: e.names for e in entities}
    titles = Resolver.from_state(context, state).titles
    rules = atelier.rules(world, state.branch)
    out: dict[str, list[PassageLine]] = {}

    for doc_id, vfp, _batch in _documents(world, state):
        axes = json.loads(conn.execute("SELECT axes FROM document_versions WHERE doc_id = ? AND version_fp = ?",
                                       (doc_id, vfp)).fetchone()[0])
        claim = axes.get("voice") == "in_world"
        obsolete = bool(state.obsolete_documents.get(doc_id))
        rows = [(int(i), t) for i, t in conn.execute(
            "SELECT idx, text FROM passages WHERE doc_id = ? AND version_fp = ? ORDER BY idx", (doc_id, vfp))]
        if not rows:
            continue
        window = _window(doc_id, rows)
        starts = {i: s for i, s, _ in window.passages}
        ref = SimpleNamespace(doc_id=doc_id, fingerprint=vfp)
        author = [a for a in layers.effective(world, state.branch, ref)
                  if a.by_author and a.kind == "mention" and a.passage is not None and a.start is not None]
        created = _new_entities(world, ref) if author else {}

        links: dict[tuple[str, int], list[tuple[int, int, bool]]] = {}  # (entité, passage) → portions
        for a in author:
            if a.status in ("removed", "ignored"):
                continue
            label = _label(a.value)
            entity = created.get(label) if label is not None else a.value.get("entity")
            if entity in state.entities:
                links.setdefault((entity, a.passage), []).append((a.start, a.end, False))
        known = known_mentions(window, entities, titles)
        for m in known + short_forms(window, known, entities, state.world, anywhere=True):
            if m.passage is None or m.entity not in state.entities:
                continue
            start, end = m.start - starts[m.passage], m.end - starts[m.passage]
            if any(a.passage == m.passage and a.start < end and start < a.end for a in author):
                continue  # l'auteur a décidé de cette portion
            form = fold(m.text)
            if any(r.form == form and (r.kind == "not_entity" or r.target == m.entity) for r in rules):
                continue
            links.setdefault((m.entity, m.passage), []).append((start, end, check_of(m, names[m.entity]) is not None))

        supported: dict[int, set[Any]] = {}
        for idx, key in conn.execute("SELECT passage_idx, fact_key FROM supports WHERE doc_id = ? AND version_fp = ?",
                                     (doc_id, vfp)):
            fid = state.occupancy.get(loads_key(key))
            if fid is not None and fid in state.facts:
                supported.setdefault(int(idx), set()).add(fid)
        texts = dict(rows)
        for (entity, idx), spans in sorted(links.items()):
            facts = tuple(sorted(_fact_label(state.facts[f]) for f in supported.get(idx, ())
                                 if entity in (state.facts[f].subject, state.facts[f].target)))
            status = PassageStatus.CLAIM if claim else \
                PassageStatus.CAPTURED if facts else PassageStatus.UNCAPTURED
            out.setdefault(entity, []).append(PassageLine(entity, doc_id, idx, texts[idx], tuple(sorted(set(spans))),
                                                          status, facts, obsolete))
    return out
