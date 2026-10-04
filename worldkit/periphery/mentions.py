"""Couches C1 et C2 : repérer les entités d'une fenêtre, puis les recouper avec l'état (chantier ingestion §6.5).

- **Fenêtre** : le document entier (titre et passages) ; le passage reste l'unité de provenance.
- **C1a, noms connus** (sans modèle) : les noms et alias de l'état cherchés tels quels dans le texte.
- **C1b, mentions** (modèle) : une seule question, « quelles entités sont mentionnées ? », sans la liste des
  entités connues ; chaque mention donne son texte exact, un type du schéma, un niveau de confiance.
- **C2, recoupement** (sans modèle) : nom ou alias exact, titre porté par une seule entité, nom connu contenu
  dans la mention (« roi Mervin »), mention contenue dans un seul nom connu (« Odon ») ; sinon entité nouvelle,
  regroupée par nom normalisé dans le lot (T-ING-07).

Le texte exact d'une mention suffit à retrouver ses portions et ses passages, de façon déterministe.
La mesure compare aux `mentions` du gold (expérience X-002) ; elle n'entre pas dans `pytest` avec un vrai modèle.
"""

from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor
from contextlib import nullcontext
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from worldkit.ingest.declaration import name_key, read_document

from .extraction import ExtractionContext, KnownEntity
from .llm.usage import input_budget, summarize

PROMPT_VERSION = 1
CONFIDENCE = ["sure", "likely", "doubt"]

SYSTEM = """Tu repères les entités mentionnées dans un texte de notes de jeu de rôle (français).
Une entité est ce qui pourrait avoir sa propre fiche dans un wiki du monde : un personnage, un lieu, un groupe,
une créature, un objet, un événement, une idée ou un écrit du monde. Elle est désignée par un nom propre
(« Hautval ») ou par une désignation précise qui vaut un nom (« le conseil des marchands », « le baron »).

Règles :
1. Une entrée par forme distincte : recopie le texte exactement tel qu'il apparaît (mêmes mots, même casse),
   sans l'article initial s'il n'en fait pas partie. Si une entité apparaît sous deux formes, donne les deux.
2. Ne relève pas les pronoms (il, elle, ils), les lieux génériques (« les collines », « la vallée ») ni les noms
   communs incidents (« un serment », « une séance », « les quais »).
3. type : le type du monde qui convient le mieux, parmi ceux donnés.
4. confidence : sure, likely ou doubt. Avec doubt, explique en quelques mots dans reason ; sinon reason est vide.
"""


def output_schema(types: list[str]) -> dict[str, Any]:
    return {"type": "object", "additionalProperties": False, "required": ["mentions"], "properties": {
        "mentions": {"type": "array", "items": {
            "type": "object", "additionalProperties": False, "required": ["text", "type", "confidence", "reason"],
            "properties": {"text": {"type": "string"}, "type": {"type": "string", "enum": types},
                           "confidence": {"type": "string", "enum": CONFIDENCE}, "reason": {"type": "string"}}}}}}


@dataclass(frozen=True)
class Window:
    """Le texte soumis aux couches et la position de chaque passage dans ce texte."""

    doc_id: str
    text: str
    passages: tuple[tuple[int, int, int], ...]  # (index du passage, début, fin)
    passage_texts: dict[int, str] = field(default_factory=dict)

    def passage_at(self, position: int) -> int | None:
        return next((i for i, start, end in self.passages if start <= position < end), None)


def document_window(path: str | Path) -> Window:
    doc = read_document(path)
    text = f"# {doc.title}\n\n" if doc.title else ""
    spans = []
    for p in doc.passages:
        start = len(text)
        text += p.text
        spans.append((p.index, start, len(text)))
        text += "\n\n"
    return Window(doc.doc_id, text.rstrip(), tuple(spans), {p.index: p.text for p in doc.passages})


@dataclass
class Mention:
    """Une portion du texte qui désigne une entité, et ce que les couches en disent."""

    text: str
    start: int
    passage: int | None
    type: str | None = None
    source: str = "known"            # known (C1a), model (C1b)
    confidence: str = "sure"
    reason: str = ""
    entity: str | None = None        # identifiant, ou "new:<nom normalisé>"
    rule: str | None = None          # règle de C2 qui a tranché
    candidates: tuple[str, ...] = ()  # plusieurs entités possibles : doute laissé à l'auteur

    @property
    def end(self) -> int:
        return self.start + len(self.text)


def _occurrences(text: str, form: str) -> list[int]:
    """Positions de `form` dans `text`, sans casse, sur des limites de mots (le trait d'union lie : « Brume »
    n'est pas trouvé dans « Brume-sur-Mer »)."""
    if not form.strip():
        return []
    pattern = re.compile(r"(?<![\w-])" + re.escape(form.strip()) + r"(?![\w-])", re.IGNORECASE)
    return [m.start() for m in pattern.finditer(text)]


def _keep_longest(mentions: list[Mention]) -> list[Mention]:
    """Une portion contenue dans une autre est écartée (« Brume » dans « Odon de Brume »)."""
    ordered = sorted(mentions, key=lambda m: (-(m.end - m.start), m.start, m.source != "known"))
    kept: list[Mention] = []
    for m in ordered:
        if not any(k.start <= m.start and m.end <= k.end for k in kept):
            kept.append(m)
    return sorted(kept, key=lambda m: m.start)


def known_mentions(window: Window, entities: tuple[KnownEntity, ...]) -> list[Mention]:
    """C1a : les noms et alias connus, trouvés tels quels (sans modèle)."""
    found = []
    for e in entities:
        for name in e.names:
            for form in {name, re.sub(r"^(?:(?:les|le|la)\s+|l['’]\s*)", "", name, flags=re.IGNORECASE)}:
                for start in _occurrences(window.text, form):
                    found.append(Mention(window.text[start:start + len(form.strip())], start,
                                         window.passage_at(start), e.type, "known", entity=e.id, rule="exact"))
    return _keep_longest(found)


@dataclass
class MentionFinder:
    """C1b : une question au modèle, sur toute la fenêtre, sans la liste des entités connues."""

    adapter: Any
    profile: Any

    @property
    def version(self) -> str:
        return f"mentions-{PROMPT_VERSION}:{self.profile.signature}"

    @property
    def meter(self) -> Any:
        return getattr(self.adapter, "meter", None)

    def prompt(self, window: Window, context: ExtractionContext) -> tuple[str, str]:
        schema = context.schema
        lines = [f"- {name} : {(schema.types[name].labels or {}).get('fr', name)}" for name in sorted(schema.types)]
        return SYSTEM, "Types du monde :\n" + "\n".join(lines) + "\n\nTexte :\n" + window.text

    def find(self, window: Window, context: ExtractionContext) -> list[Mention]:
        system, user = self.prompt(window, context)
        raw = self.adapter.complete(system, user, output_schema(sorted(context.schema.types)))
        found = []
        for m in raw["mentions"]:
            for start in _occurrences(window.text, m["text"]):
                found.append(Mention(window.text[start:start + len(m["text"].strip())], start, window.passage_at(start),
                                     m["type"], "model", m["confidence"], m.get("reason") or ""))
            if not _occurrences(window.text, m["text"]):  # texte réécrit par le modèle : gardé, sans position
                found.append(Mention(m["text"], -1, None, m["type"], "model", m["confidence"], m.get("reason") or ""))
        return found


def merge(known: list[Mention], found: list[Mention]) -> list[Mention]:
    """C1 : les portions connues priment ; une portion du modèle contenue dans une autre est écartée."""
    placed = [m for m in found if m.start >= 0]
    unplaced = [m for m in found if m.start < 0]
    return _keep_longest(known + placed) + unplaced


def _compatible(schema: Any, entity_type: str, mention_type: str | None) -> bool:
    return mention_type is None or schema.is_subtype(entity_type, mention_type) \
        or schema.is_subtype(mention_type, entity_type)


@dataclass
class Resolver:
    """C2 : recoupement déterministe avec l'état. Un doute (plusieurs candidats) est laissé à l'auteur."""

    entities: tuple[KnownEntity, ...]
    titles: dict[str, list[str]]  # titre normalisé → entités qui le portent aujourd'hui
    schema: Any

    @classmethod
    def from_state(cls, context: ExtractionContext, state: Any) -> Resolver:
        titles: dict[str, list[str]] = {}
        for e in context.entities:
            fact = state.facts.get(("attr", e.id, "title")) if state is not None else None
            if fact is not None:
                titles.setdefault(name_key(str(fact.value)), []).append(e.id)
        return cls(context.entities, titles, context.schema)

    def resolve(self, m: Mention) -> Mention:
        if m.entity is not None:
            return m
        key = name_key(m.text)
        exact = [e for e in self.entities if key in {name_key(n) for n in e.names}
                 and _compatible(self.schema, e.type, m.type)]
        if len(exact) == 1:
            m.entity, m.rule = exact[0].id, "exact"
            return m
        holders = self.titles.get(key, [])
        if len(holders) == 1:
            m.entity, m.rule = holders[0], "title"
            return m
        contained = [e for e in self.entities if _compatible(self.schema, e.type, m.type) and any(
            re.search(r"(?<!\w)" + re.escape(name_key(n)) + r"(?!\w)", key) for n in e.names if len(name_key(n)) > 2)]
        if len(contained) == 1:
            m.entity, m.rule = contained[0].id, "contains"
            return m
        part = [e for e in self.entities if _compatible(self.schema, e.type, m.type) and len(key) > 2 and any(
            re.search(r"(?<!\w)" + re.escape(key) + r"(?!\w)", name_key(n)) for n in e.names)]
        if not contained and len(part) == 1:
            m.entity, m.rule = part[0].id, "part"
            return m
        candidates = tuple(sorted({e.id for e in exact} | set(holders) | {e.id for e in contained}
                                  | {e.id for e in part}))
        if len(candidates) > 1:
            m.rule, m.candidates = "ambiguous", candidates
            return m
        m.entity, m.rule = f"new:{key}", "new"
        return m


# ---------------------------------------------------------------------------
# Mesure contre les mentions du gold (X-002)
# ---------------------------------------------------------------------------

GESTURES = {"keep": 1, "remove": 1, "change": 2, "add": 3}  # poids provisoires (chantier §9)


@dataclass
class PassageMentions:
    doc: str
    index: int
    gold: dict[str, str]                      # texte → identifiant ou new:…
    found: list[Mention] = field(default_factory=list)
    matched: list[tuple[str, Mention]] = field(default_factory=list)
    missed: list[str] = field(default_factory=list)
    extra: list[Mention] = field(default_factory=list)

    def resolved_ok(self, surface: str, m: Mention) -> bool:
        expected = self.gold[surface]
        if expected.startswith(("new:", "pending:")):
            return bool(m.entity and m.entity.startswith("new:"))
        return m.entity == expected


def _match(p: PassageMentions) -> None:
    """Une mention du gold est trouvée si une portion trouvée a le même nom normalisé, ou le contient
    (« roi Mervin » et « Mervin »)."""
    free = list(p.found)
    for surface in p.gold:
        key = name_key(surface)
        hit = next((m for m in free if name_key(m.text) == key), None) or next(
            (m for m in free if key in name_key(m.text) or name_key(m.text) in key), None)
        if hit is None:
            p.missed.append(surface)
        else:
            free.remove(hit)
            p.matched.append((surface, hit))
    p.extra = free


@dataclass
class MentionReport:
    finder: str
    passages: list[PassageMentions]
    calls: list[Any] | None = None
    unplaced: list[Mention] = field(default_factory=list)
    stability: dict[str, float] = field(default_factory=dict)

    def summary(self) -> dict[str, Any]:
        tp = sum(len(p.matched) for p in self.passages)
        fn = sum(len(p.missed) for p in self.passages)
        fp = sum(len(p.extra) for p in self.passages)
        known_tp = sum(1 for p in self.passages for _, m in p.matched if m.source == "known")
        ok = sum(1 for p in self.passages for s, m in p.matched if p.resolved_ok(s, m))
        gold = tp + fn
        rules: dict[str, int] = {}
        for p in self.passages:
            for _, m in p.matched:
                rules[m.rule or "?"] = rules.get(m.rule or "?", 0) + 1
        wrong = tp - ok
        gestures = {"keep": ok, "remove": fp, "change": wrong, "add": fn}
        return {
            "finder": self.finder, "passages": len(self.passages), "gold_mentions": gold,
            "c1": {"recall": round(tp / gold, 3) if gold else 0.0,
                   "precision": round(tp / (tp + fp), 3) if tp + fp else 0.0, "tp": tp, "fp": fp, "fn": fn,
                   "found_without_model": known_tp, "recall_without_model": round(known_tp / gold, 3) if gold else 0.0,
                   "unplaced": len(self.unplaced)},
            "c2": {"resolved_ok": ok, "of": tp, "accuracy": round(ok / tp, 3) if tp else 0.0, "rules": rules},
            "gestures": {**gestures, "weighted": sum(GESTURES[k] * v for k, v in gestures.items())},
            **({"stability": self.stability} if self.stability else {}),
            **({"usage": summarize(self.calls, input_budget())} if self.calls is not None else {}),
        }


def _gold_mentions(gold_dir: Path, window: Window) -> dict[int, dict[str, str]]:
    """Mentions du gold pour chaque passage de la fenêtre, appariées par le début du texte (comme la mesure T2) :
    deux versions d'un même document ont chacune leur gold."""
    entries = []
    for path in sorted(Path(gold_dir).glob("*.yaml")):
        doc = yaml.safe_load(path.read_text(encoding="utf-8"))
        if doc.get("document") == window.doc_id:
            entries += [p for p in doc.get("passages", []) if p.get("mentions")]
    out = {}
    for index, text in window.passage_texts.items():
        candidates = [g for g in entries if text.startswith(g["starts_with"])]
        if candidates:
            g = max(candidates, key=lambda g: len(g["starts_with"]))
            out[index] = {str(k): str(v) for k, v in g["mentions"].items()}
    return out


def evaluate_mentions(finder: MentionFinder | None, documents: list[Path], gold_dir: Path,
                      context: ExtractionContext, state: Any, repeat: int = 1) -> MentionReport:
    """C1 (C1a, et C1b si `finder`) puis C2 sur chaque document, comparés aux mentions du gold."""
    windows = [document_window(path) for path in documents]
    meter = finder.meter if finder is not None else None
    first_call = len(meter.calls) if meter is not None else 0

    def run(window: Window) -> list[list[Mention]]:
        if finder is None:
            return []
        with meter.label(window.doc_id) if meter is not None else nullcontext():
            return [finder.find(window, context) for _ in range(max(1, repeat))]

    with ThreadPoolExecutor(max_workers=4) as pool:
        model_runs = list(pool.map(run, windows))
    resolver = Resolver.from_state(context, state)
    report = MentionReport(finder.version if finder is not None else "known-only", [])
    for window, runs in zip(windows, model_runs):
        mentions = merge(known_mentions(window, context.entities), runs[0] if runs else [])
        for m in mentions:
            resolver.resolve(m)
        report.unplaced += [m for m in mentions if m.start < 0]  # texte réécrit par le modèle, introuvable
        for index, expected in sorted(_gold_mentions(gold_dir, window).items()):
            p = PassageMentions(window.doc_id, index, expected, [m for m in mentions if m.passage == index])
            _match(p)
            report.passages.append(p)
        if len(runs) > 1:
            a, b = ({(name_key(m.text), m.type) for m in r} for r in runs[:2])
            report.stability[window.doc_id] = round(len(a & b) / len(a | b), 3) if a | b else 1.0
    if meter is not None:
        report.calls = meter.calls[first_call:]
    return report
