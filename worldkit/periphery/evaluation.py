"""Mesure T2 : qualité d'un extracteur contre les annotations de référence (cadre technique §6, T-ING-19).

Pour chaque passage annoté, les changements extraits sont comparés à ceux du gold après
normalisation : une entité nouvelle est désignée par son nom normalisé (les étiquettes `new:` du
modèle et du gold diffèrent), les chaînes sont comparées sans casse ni espaces superflus.

Indicateurs : précision et rappel par opération ; pièges (`must_not`) ; attributions ; nombre
d'affirmations et changements revendiqués ; stabilité (deux extractions hors cache d'un même passage).
Mesure indicative, jamais bloquante : elle n'entre pas dans `pytest`, un vrai modèle coûte et varie.
"""

from __future__ import annotations

import time
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from worldkit.ingest.declaration import normalize, read_document

from .extraction import Extraction, ExtractionContext, Extractor

NEW_PREFIXES = ("new:", "pending:")
_KEY_FIELDS = ("op", "entity", "type", "attribute", "value", "from", "relation", "to", "target")


def _names(drafts: list[dict[str, Any]]) -> dict[str, str]:
    """Étiquette d'entité nouvelle → nom normalisé, d'après les `set_attribute name` des brouillons."""
    out = {}
    for d in drafts:
        e = d.get("entity")
        if d.get("op") == "set_attribute" and d.get("attribute") == "name" and isinstance(e, str) \
                and e.startswith(NEW_PREFIXES):
            out[e.split(":", 1)[1]] = normalize(str(d.get("value"))).casefold()
    return out


def _norm(v: Any, names: dict[str, str]) -> Any:
    if isinstance(v, str):
        if v.startswith(NEW_PREFIXES):
            label = v.split(":", 1)[1]
            return f"new:{names.get(label, label)}"
        if " " in v and not v.startswith(NEW_PREFIXES):  # désignation « a relation b »
            return " ".join(str(_norm(t, names)) for t in v.split(" ")).casefold()
        return normalize(v).casefold()
    return v


def key(draft: dict[str, Any], names: dict[str, str]) -> tuple[Any, ...]:
    d = dict(draft)
    if d.get("op") == "set_visibility":
        d = {"op": "set_visibility", "target": d.get("target"), "value": d.get("value")}
    return tuple((f, _norm(d.get(f), names)) for f in _KEY_FIELDS + ("value",) if d.get(f) is not None)


def matches(pattern: dict[str, Any], draft_key: tuple[Any, ...], names: dict[str, str]) -> bool:
    """Un piège `must_not` : tous ses champs donnés figurent dans le changement extrait."""
    fields = dict(draft_key)
    return all(fields.get(f) == _norm(v, names) for f, v in pattern.items() if f in _KEY_FIELDS + ("value",))


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


@dataclass
class Report:
    extractor: str
    passages: list[PassageResult]

    def per_op(self) -> dict[str, dict[str, float]]:
        tp, fp, fn = Counter(), Counter(), Counter()
        for p in self.passages:
            for k in p.found & p.expected:
                tp[dict(k)["op"]] += 1
            for k in p.found - p.expected:
                fp[dict(k)["op"]] += 1
            for k in p.expected - p.found:
                fn[dict(k)["op"]] += 1
        out = {}
        for op in sorted(set(tp) | set(fp) | set(fn)):
            prec = tp[op] / (tp[op] + fp[op]) if tp[op] + fp[op] else 0.0
            rec = tp[op] / (tp[op] + fn[op]) if tp[op] + fn[op] else 0.0
            out[op] = {"tp": tp[op], "fp": fp[op], "fn": fn[op], "precision": round(prec, 3), "recall": round(rec, 3)}
        return out

    def summary(self) -> dict[str, Any]:
        tp = sum(len(p.found & p.expected) for p in self.passages)
        fp = sum(len(p.found - p.expected) for p in self.passages)
        fn = sum(len(p.expected - p.found) for p in self.passages)
        stabilities = [p.stability for p in self.passages if p.stability is not None]
        return {
            "extractor": self.extractor,
            "passages": len(self.passages),
            "errors": sum(1 for p in self.passages if p.error),
            "precision": round(tp / (tp + fp), 3) if tp + fp else 0.0,
            "recall": round(tp / (tp + fn), 3) if tp + fn else 0.0,
            "traps_fallen": sum(len(p.traps) for p in self.passages),
            "attribution_errors": sum(1 for p in self.passages if not p.attribution_ok),
            "claims": f"{sum(p.claims_found for p in self.passages)}/{sum(p.claims_expected for p in self.passages)}",
            "claimed_changes": f"{sum(p.claimed_matched for p in self.passages)}"
                               f"/{sum(p.claimed_expected for p in self.passages)}",
            "stability": round(sum(stabilities) / len(stabilities), 3) if stabilities else None,
            "seconds": round(sum(p.seconds for p in self.passages), 1),
            "per_op": self.per_op(),
        }


def _gold_index(gold_dir: Path) -> dict[str, list[dict[str, Any]]]:
    index: dict[str, list[dict[str, Any]]] = {}
    for path in sorted(gold_dir.glob("*.yaml")):
        doc = yaml.safe_load(path.read_text(encoding="utf-8"))
        index.setdefault(doc["document"], []).extend(doc.get("passages", []))
    return index


def evaluate(extractor: Extractor, oracle: Extractor, gold_dir: Path, documents: list[Path],
             context: ExtractionContext, repeat: int = 1) -> Report:
    """Compare `extractor` à `oracle` (le gold) sur les passages annotés des documents donnés."""
    gold = _gold_index(Path(gold_dir))
    results = []
    collected = []
    for path in documents:
        doc = read_document(path)
        annotated = [(p, g) for p in doc.passages
                     for g in [max((g for g in gold.get(doc.doc_id, []) if p.text.startswith(g["starts_with"])),
                                   key=lambda g: len(g["starts_with"]), default=None)] if g is not None]
        expected_ex = {p.index: oracle.extract(doc.doc_id, p.text, context) for p, _ in annotated}
        runs_by_passage: dict[int, tuple[list[Extraction], str | None, float]] = {}
        for p, _ in annotated:
            speakers = p.speakers()
            ctx = ExtractionContext(context.schema, context.entities,
                                    "in_world" if speakers or doc.axes.voice == "in_world" else "author",
                                    speakers[0] if speakers else doc.axes.speaker)
            runs: list[Extraction] = []
            error = None
            start = time.perf_counter()
            for _ in range(max(1, repeat)):
                try:
                    runs.append(extractor.extract(doc.doc_id, p.text, ctx))
                except Exception as e:  # une erreur d'extraction compte, sans arrêter la mesure
                    error = str(e)
            runs_by_passage[p.index] = (runs, error, time.perf_counter() - start)
        collected.append((doc, annotated, expected_ex, runs_by_passage))
    # Les noms des entités nouvelles se lisent sur l'ensemble des documents mesurés : un passage cite souvent
    # une entité nommée plus haut, ou dans un autre document du même lot. De même côté gold.
    gold_names = _names([d for _, _, ex, _ in collected for e in ex.values() for d in e.drafts])
    names = _names([d for _, _, _, rb in collected for runs, _, _ in rb.values() for run in runs[:1] for d in run.drafts])
    for doc, annotated, expected_ex, runs_by_passage in collected:
        for p, g in annotated:
            runs, error, seconds = runs_by_passage[p.index]
            expected = expected_ex[p.index]
            first = runs[0] if runs else Extraction()
            found = {key(d, names) for d in first.drafts}
            r = PassageResult(doc.doc_id, p.index, {key(d, gold_names) for d in expected.drafts}, found,
                              error=error, seconds=seconds)
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
    return Report(getattr(extractor, "version", type(extractor).__name__), results)
