"""Mesure T2 : qualité d'un extracteur contre les annotations de référence (cadre technique §6, T-ING-19).

Pour chaque passage annoté, les changements extraits sont comparés à ceux du gold après
normalisation : une entité nouvelle est désignée par son nom normalisé (les étiquettes `new:` du
modèle et du gold diffèrent), les chaînes sont comparées sans casse ni espaces superflus.

Les lots sont mesurés dans l'ordre : chaque lot voit, comme entités en attente, les créations
proposées par les lots précédents (T-ING-07). Les passages méta sont mesurés depuis J8, après traduction
des formes réduites (`sheet_values`) contre l'état de base, comme le fait le lot.

Indicateurs : précision et rappel, globaux et sur les seuls changements qui posent une question
(les supports, qui répètent l'état, n'en posent aucune) ; par opération ; pièges (`must_not`) ;
attributions ; affirmations ; stabilité (deux extractions d'un même passage).
Mesure indicative, jamais bloquante : elle n'entre pas dans `pytest`, un vrai modèle coûte et varie.
"""

from __future__ import annotations

import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

import yaml

from worldkit.ingest.declaration import name_key, normalize, read_document

from .extraction import Extraction, ExtractionContext, Extractor, KnownEntity

NEW_PREFIXES = ("new:", "pending:")
_KEY_FIELDS = ("op", "scope", "entity", "type", "attribute", "value", "from", "relation", "to", "target",
               "constraint")


def _names(drafts: list[dict[str, Any]]) -> dict[str, str]:
    """Étiquette d'entité nouvelle → nom normalisé, d'après les `set_attribute name` des brouillons."""
    out = {}
    for d in drafts:
        e = d.get("entity")
        if d.get("op") == "set_attribute" and d.get("attribute") == "name" and isinstance(e, str) \
                and e.startswith(NEW_PREFIXES):
            out[e.split(":", 1)[1]] = name_key(str(d.get("value")))
    return out


def _norm(v: Any, names: dict[str, str]) -> Any:
    if isinstance(v, dict):  # contraintes d'un attribut de système
        return tuple(sorted((k, _norm(x, names)) for k, x in v.items()))
    if isinstance(v, str):
        label = v.split(":", 1)[1] if v.startswith(NEW_PREFIXES) else v
        if v.startswith(NEW_PREFIXES) or label in names:  # une entité en attente, citée par son identifiant
            return f"new:{names.get(label, label)}"
        if " " in v:  # désignation « a relation b »
            return " ".join(str(_norm(t, names)) for t in v.split(" ")).casefold()
        return normalize(v).casefold()
    return v


def key(draft: dict[str, Any], names: dict[str, str]) -> tuple[Any, ...]:
    d = dict(draft)
    if d.get("scope") == "world":
        del d["scope"]
    if d.get("op") == "set_visibility":
        d = {"op": "set_visibility", "target": d.get("target"), "value": d.get("value")}
    if d.get("attribute") == "name" and isinstance(d.get("value"), str):
        d["value"] = name_key(d["value"])  # « le conseil des marchands » = « conseil des marchands »
    return tuple((f, _norm(d.get(f), names)) for f in _KEY_FIELDS if d.get(f) is not None)


def matches(pattern: dict[str, Any], draft_key: tuple[Any, ...], names: dict[str, str]) -> bool:
    """Un piège `must_not` : tous ses champs donnés figurent dans le changement extrait."""
    fields = dict(draft_key)
    return all(fields.get(f) == _norm(v, names) for f, v in pattern.items() if f in _KEY_FIELDS)


def is_support(draft_key: tuple[Any, ...], state: Any) -> bool:
    """Le changement répète l'état de base : un support, qui ne pose aucune question (T-ING-11)."""
    if state is None:
        return False
    f = dict(draft_key)
    op = f.get("op")
    if op == "set_attribute":
        fact = state.facts.get(("attr", f.get("entity"), f.get("attribute")))
        return fact is not None and _norm(fact.value, {}) == f.get("value")
    if op == "add_value":
        return any(k[0] == "value" and k[1] == f.get("entity") and k[2] == f.get("attribute")
                   and _norm(k[3], {}) == f.get("value") for k in state.occupancy)
    if op == "schema_set_type" and f.get("scope") in state.systems:
        types = {name.casefold(): t for name, t in state.systems[f["scope"]].types.items()}  # clés normalisées
        t = types.get(str(f.get("type")))
        a = t.attributes.get(f.get("attribute")) if t is not None else None
        return a is not None and all(getattr(a, k) == v for k, v in dict(f.get("constraint") or ()).items())
    if op == "add_relation":
        return any(fact.kind == "rel" and fact.name == f.get("relation")
                   and {fact.subject, fact.target} == {f.get("from"), f.get("to")} for fact in state.facts.values())
    return False


@dataclass
class PassageResult:
    doc: str
    index: int
    expected: set[tuple[Any, ...]]
    found: set[tuple[Any, ...]]
    traps: list[str] = field(default_factory=list)
    attribution_ok: bool = True
    claims_expected: int = 0
    claims_found: int = 0
    claimed_matched: int = 0
    claimed_expected: int = 0
    stability: float | None = None
    error: str | None = None
    seconds: float = 0.0
    supports: set[tuple[Any, ...]] = field(default_factory=set)  # attendus ou trouvés qui répètent l'état

    @property
    def expected_questions(self) -> set[tuple[Any, ...]]:
        return self.expected - self.supports

    @property
    def found_questions(self) -> set[tuple[Any, ...]]:
        return self.found - self.supports


def _scores(pairs: list[tuple[set[Any], set[Any]]]) -> dict[str, Any]:
    tp = sum(len(f & e) for e, f in pairs)
    fp = sum(len(f - e) for e, f in pairs)
    fn = sum(len(e - f) for e, f in pairs)
    return {"precision": round(tp / (tp + fp), 3) if tp + fp else 0.0,
            "recall": round(tp / (tp + fn), 3) if tp + fn else 0.0, "tp": tp, "fp": fp, "fn": fn}


@dataclass
class Report:
    extractor: str
    passages: list[PassageResult]
    elapsed: float | None = None  # temps écoulé ; les passages sont extraits en parallèle, leurs durées se recouvrent

    @property
    def all_failed(self) -> bool:
        """Toutes les extractions ont échoué : la mesure ne mesure rien (précision et rappel à 0 trompeurs)."""
        return bool(self.passages) and all(p.error for p in self.passages)

    def per_op(self) -> dict[str, dict[str, Any]]:
        ops = sorted({dict(k)["op"] for p in self.passages for k in p.expected | p.found})
        return {op: _scores([({k for k in p.expected if dict(k)["op"] == op},
                              {k for k in p.found if dict(k)["op"] == op}) for p in self.passages]) for op in ops}

    def questions(self) -> dict[str, Any]:
        """Précision et rappel sur les seuls changements qui posent une question (supports écartés)."""
        return _scores([(p.expected_questions, p.found_questions) for p in self.passages])

    def summary(self) -> dict[str, Any]:
        overall = _scores([(p.expected, p.found) for p in self.passages])
        stabilities = [p.stability for p in self.passages if p.stability is not None]
        return {
            "extractor": self.extractor,
            "passages": len(self.passages),
            "errors": sum(1 for p in self.passages if p.error),
            "precision": overall["precision"],
            "recall": overall["recall"],
            "questions": self.questions(),
            "extra_supports": sum(len((p.found - p.expected) & p.supports) for p in self.passages),
            "traps_fallen": sum(len(p.traps) for p in self.passages),
            "attribution_errors": sum(1 for p in self.passages if not p.attribution_ok),
            "claims": f"{sum(p.claims_found for p in self.passages)}/{sum(p.claims_expected for p in self.passages)}",
            "claimed_changes": f"{sum(p.claimed_matched for p in self.passages)}"
                               f"/{sum(p.claimed_expected for p in self.passages)}",
            "stability": round(sum(stabilities) / len(stabilities), 3) if stabilities else None,
            "seconds": round(self.elapsed if self.elapsed is not None else sum(p.seconds for p in self.passages), 1),
            "per_op": self.per_op(),
        }


def _gold_index(gold_dir: Path) -> dict[str, list[dict[str, Any]]]:
    index: dict[str, list[dict[str, Any]]] = {}
    for path in sorted(gold_dir.glob("*.yaml")):
        doc = yaml.safe_load(path.read_text(encoding="utf-8"))
        index.setdefault(doc["document"], []).extend(doc.get("passages", []))
    return index


@dataclass
class _Batch:
    items: list[tuple[Any, Any, dict[str, Any], Extraction]]  # (document, passage, gold, extraction attendue)


def _prepare(oracle: Extractor, gold: dict[str, list[dict[str, Any]]], documents: list[Path],
             context: ExtractionContext) -> _Batch:
    items = []
    for path in documents:
        doc = read_document(path)
        for p in doc.passages:
            candidates = [g for g in gold.get(doc.doc_id, []) if p.text.startswith(g["starts_with"])]
            if not candidates:
                continue
            g = max(candidates, key=lambda g: len(g["starts_with"]))
            items.append((doc, p, g, oracle.extract(doc.doc_id, p.text, context)))
    return _Batch(items)


def evaluate(extractor: Extractor, oracle: Extractor, gold_dir: Path, documents: list[Any],
             context: ExtractionContext, repeat: int = 1, state: Any = None) -> Report:
    """Compare `extractor` à `oracle` (le gold) sur les passages annotés des documents donnés.

    `documents` : une liste de chemins (un seul lot), ou une liste de lots (listes de chemins), mesurés
    dans l'ordre. Noms des entités nouvelles et créations répétées se lisent à l'échelle du lot.
    """
    start = time.perf_counter()
    groups = [documents] if documents and not isinstance(documents[0], (list, tuple)) else documents
    gold = _gold_index(Path(gold_dir))
    batches = [_prepare(oracle, gold, list(group), context) for group in groups]
    gold_names = _names([d for b in batches for *_, ex in b.items for d in ex.drafts])
    results: list[PassageResult] = []
    pending: list[KnownEntity] = []
    for batch in batches:
        ctx = replace(context, entities=context.entities + tuple(pending))
        results += _measure(extractor, batch, ctx, repeat, state, gold_names)
        for *_, ex in batch.items:  # les créations du lot deviennent « en attente » pour les suivants
            for d in ex.drafts:
                e = d.get("entity")
                if d.get("op") == "create_entity" and isinstance(e, str) and e.startswith(NEW_PREFIXES):
                    label = e.split(":", 1)[1]
                    if not any(k.id == label for k in pending):
                        pending.append(KnownEntity(label, str(d.get("type")), (gold_names.get(label, label),)))
    return Report(getattr(extractor, "version", type(extractor).__name__), results, time.perf_counter() - start)


def _expand(drafts: tuple[dict[str, Any], ...], state: Any, sheets: dict[tuple[str, str], str]) -> list[dict[str, Any]]:
    """Formes réduites `sheet_values` traduites comme le fait le lot (sans état, laissées telles quelles)."""
    if state is None:
        return list(drafts)
    from worldkit.ingest.meta import expand_sheet_values
    out: list[dict[str, Any]] = []
    for d in drafts:
        if d.get("op") == "sheet_values":
            out += expand_sheet_values(d, state, sheets) or [d]
        else:
            out.append(d)
    return out


def _measure(extractor: Extractor, batch: _Batch, context: ExtractionContext, repeat: int, state: Any,
             gold_names: dict[str, str]) -> list[PassageResult]:
    def one(item: tuple[Any, Any, dict[str, Any], Extraction]) -> tuple[list[Extraction], str | None, float]:
        doc, p, _, _ = item
        speakers = p.speakers()
        ctx = replace(context, voice="in_world" if speakers or doc.axes.voice == "in_world" else "author",
                      speaker=speakers[0] if speakers else doc.axes.speaker)
        runs: list[Extraction] = []
        error = None
        start = time.perf_counter()
        for attempt in range(max(1, repeat)):
            try:
                target = extractor if attempt == 0 else getattr(extractor, "inner", extractor)  # stabilité hors cache
                runs.append(target.extract(doc.doc_id, p.text, ctx))
            except Exception as e:  # une erreur d'extraction compte, sans arrêter la mesure
                error = str(e)
        return runs, error, time.perf_counter() - start

    workers = max(1, int(getattr(extractor, "concurrency", 1)))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        measured = list(pool.map(one, batch.items))
    names = {**gold_names, **_names([d for runs, _, _ in measured for run in runs[:1] for d in run.drafts])}
    results = []
    created: set[tuple[Any, ...]] = set()  # création ou nom déjà proposés plus haut : regroupés par le lot (T-ING-07)
    sheets: dict[tuple[str, str], str] = {}
    for (doc, p, g, expected), (runs, error, seconds) in zip(batch.items, measured):
        first = runs[0] if runs else Extraction()
        found = set()
        for d in _expand(first.drafts, state, sheets):
            k = key(d, names)
            fields = dict(k)
            repeated = str(fields.get("entity", "")).startswith("new:") and (
                fields["op"] == "create_entity" or fields.get("attribute") == "name")
            if repeated and k in created:
                continue
            if repeated:
                created.add(k)
            found.add(k)
        r = PassageResult(doc.doc_id, p.index, {key(d, gold_names) for d in expected.drafts}, found,
                          error=error, seconds=seconds)
        r.supports = {k for k in r.expected | r.found if is_support(k, state)}
        r.traps = [str(t) for t in g.get("must_not") or [] if any(matches(t, k, names) for k in found)]
        r.attribution_ok = ("attribution" in first.flags) == ("attribution" in expected.flags)
        r.claims_expected, r.claims_found = len(expected.claims), len(first.claims)
        expected_claimed = {key(c["claimed"], gold_names) for c in expected.claims if c.get("claimed")}
        found_claimed = {key(c["claimed"], names) for c in first.claims if c.get("claimed")}
        r.claimed_expected, r.claimed_matched = len(expected_claimed), len(expected_claimed & found_claimed)
        if len(runs) > 1:
            other = {key(d, names) for d in runs[1].drafts}
            union = found | other
            r.stability = len(found & other) / len(union) if union else 1.0
        results.append(r)
    return results
