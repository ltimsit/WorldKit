"""Couche C5 : les faits entre entités confirmées (chantier ingestion §6.5 ; expérience X-004).

Entrée : la fenêtre (le document entier) et les entités confirmées qui y apparaissent (identifiant, type, nom).
Le modèle ne voit que les relations du schéma compatibles avec ces types et leurs attributs, et répond à une
seule question : « qu'affirme le texte sur ces entités ? ». Chaque fait cite sa preuve, la phrase exacte : elle
le rattache à son passage sans modèle (T-ING-11). Hors de C5 : la création des entités et leur nom (C2), la
notoriété et les rumeurs (C4).

La mesure compare aux changements du gold, passage par passage, avec la clé de la mesure T2 (`evaluation.key`) ;
les facultatifs du gold sont neutres. Elle n'entre pas dans `pytest` avec un vrai modèle.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from contextlib import nullcontext
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from worldkit.ingest.declaration import name_key, normalize

from .evaluation import _names, is_support, key
from .extraction import ExtractionContext, OracleExtractor
from .llm.usage import input_budget, summarize
from .mentions import Window

PROMPT_VERSION = 1

# Exemples volontairement pris hors de Valmont : on ne règle pas le prompt sur le corpus (X-003).
SYSTEM = """Tu relèves les faits qu'un texte de notes de jeu de rôle (français) affirme sur des entités déjà identifiées.

Règles :
1. Seulement ce que le texte affirme. N'invente pas, ne déduis pas au-delà du texte.
2. subject et object sont des identifiants de la liste d'entités, jamais autre chose.
3. Une relation : une de celles données ; si aucune ne convient, propose un identifiant anglais en snake_case.
   Un attribut : un de ceux donnés pour le type du sujet, avec une valeur courte recopiée du texte, sans
   complément (« capitaine », pas « capitaine du port »).
4. Un fait révolu (« régnait autrefois ») n'est pas un fait actuel ; un repère de temps (« depuis la guerre »)
   n'est pas une relation.
5. evidence : la phrase du texte qui affirme le fait, recopiée exactement.
"""


def output_schema() -> dict[str, Any]:
    fact = {"type": "object", "additionalProperties": False,
            "required": ["kind", "subject", "predicate", "object", "value", "evidence"],
            "properties": {"kind": {"type": "string", "enum": ["relation", "attribute"]},
                           "subject": {"type": "string"}, "predicate": {"type": "string"},
                           "object": {"type": "string"}, "value": {"type": "string"},
                           "evidence": {"type": "string"}}}
    return {"type": "object", "additionalProperties": False, "required": ["facts"],
            "properties": {"facts": {"type": "array", "items": fact}}}


@dataclass(frozen=True)
class Confirmed:
    """Une entité confirmée pour la fenêtre : connue (identifiant de l'état) ou nouvelle (`new:…`)."""

    id: str
    type: str
    name: str


@dataclass
class Fact:
    draft: dict[str, Any]
    evidence: str
    passage: int | None


def _is_a(schema: Any, type_name: str, accepted: list[str]) -> bool:
    return any(type_name in schema.types and schema.is_subtype(type_name, t) for t in accepted)


@dataclass
class FactFinder:
    """C5 : une question au modèle, sur la fenêtre, à entités données et schéma réduit."""

    adapter: Any
    profile: Any

    @property
    def version(self) -> str:
        return f"facts-{PROMPT_VERSION}:{self.profile.signature}"

    @property
    def meter(self) -> Any:
        return getattr(self.adapter, "meter", None)

    def prompt(self, window: Window, entities: list[Confirmed], schema: Any) -> tuple[str, str]:
        types = {e.type for e in entities}
        lines = [f"- {e.id} ({e.type}) : {e.name}" for e in sorted(entities, key=lambda e: e.id)]
        relations = []
        for name, r in sorted(schema.relations.items()):
            if any(_is_a(schema, t, r.from_) for t in types) and any(_is_a(schema, t, r.to) for t in types):
                label = (r.labels or {}).get("fr", name)
                relations.append(f"- {name} : {'|'.join(r.from_)} → {'|'.join(r.to)} ({label})")
        attributes = []
        for t in sorted(types):
            if t in schema.types:
                names = [f"{a} ({(d.labels or {}).get('fr', a)})" for a, d in schema.attributes_of(t).items()
                         if a != "name"]
                if names:
                    attributes.append(f"- {t} : {', '.join(names)}")
        user = ("Entités (identifiant, type : nom) :\n" + "\n".join(lines)
                + "\n\nRelations possibles :\n" + ("\n".join(relations) or "- (aucune)")
                + "\n\nAttributs par type :\n" + ("\n".join(attributes) or "- (aucun)")
                + "\n\nTexte :\n" + window.text)
        return SYSTEM, user

    def find(self, window: Window, entities: list[Confirmed], schema: Any) -> list[Fact]:
        system, user = self.prompt(window, entities, schema)
        raw = self.adapter.complete(system, user, output_schema())
        types = {e.id: e.type for e in entities}
        facts = []
        for f in raw["facts"]:
            subject = f["subject"].strip()
            if f["kind"] == "relation":
                draft = {"op": "add_relation", "from": subject, "relation": f["predicate"].strip(),
                         "to": f["object"].strip()}
            else:
                attr = f["predicate"].strip()
                definition = schema.attributes_of(types[subject]).get(attr) \
                    if types.get(subject) in schema.types else None
                is_list = definition is not None and definition.type.is_list
                draft = {"op": "add_value" if is_list else "set_attribute", "entity": subject, "attribute": attr,
                         "value": f["value"].strip()}
            facts.append(Fact(draft, f["evidence"], _locate(window, f["evidence"])))
        return facts


def _locate(window: Window, evidence: str) -> int | None:
    """Le passage qui contient la preuve (espaces et casse normalisés) ; None si elle n'est pas dans le texte."""
    target = normalize(evidence).casefold().strip(" .")
    if not target:
        return None
    texts = {i: normalize(t).casefold() for i, t in window.passage_texts.items()}
    for index, text in texts.items():
        if target in text:
            return index
    # Preuve à cheval sur deux passages (le modèle recopie deux paragraphes) : le passage qui en contient
    # le plus long morceau (découpé aux lignes et aux phrases).
    import re
    pieces = [p.strip(" .-") for p in re.split(r"\n|(?<=[.!?])\s+", evidence) if len(p.strip(" .-")) > 10]
    best = max(((len(normalize(p)), i) for p in pieces for i, text in texts.items()
                if normalize(p).casefold() in text), default=None)
    return best[1] if best else None


# ---------------------------------------------------------------------------
# Entités confirmées : celles du gold (qualité propre de C5) ou celles de la chaîne C1 puis C2
# ---------------------------------------------------------------------------

def gold_entities(window: Window, gold_dir: Path, context: ExtractionContext) -> list[Confirmed]:
    """Les entités que le gold mentionne dans la fenêtre ; une entité nouvelle prend le type et le nom du gold."""
    import yaml

    from .mentions import _gold_mentions
    known = {e.id: e for e in context.entities}
    new: dict[str, tuple[str, str]] = {}  # défini à l'échelle du corpus : créé dans un document, cité dans un autre
    for path in sorted(Path(gold_dir).glob("*.yaml")):
        doc = yaml.safe_load(path.read_text(encoding="utf-8"))
        for d in (c for p in doc.get("passages", []) for c in (p.get("changes") or [])):
            e = d.get("entity")
            if isinstance(e, str) and e.startswith("new:"):
                t, n = new.get(e, ("", ""))
                if d.get("op") == "create_entity":
                    t = str(d.get("type"))
                if d.get("op") == "set_attribute" and d.get("attribute") == "name":
                    n = str(d.get("value"))
                new[e] = (t, n)
    ids = {v for mentions in _gold_mentions(gold_dir, window).values() for v in mentions.values()}
    out = []
    for eid in sorted(ids):
        if eid in known and known[eid].names:
            out.append(Confirmed(eid, known[eid].type, known[eid].names[0]))
        elif eid in new and new[eid][0]:
            out.append(Confirmed(eid, new[eid][0], new[eid][1] or eid.split(":", 1)[1]))
    return out


def chain_entities(mentions: list[Any], context: ExtractionContext) -> list[Confirmed]:
    """Les entités rattachées par C2 (doutes exclus : personne ne les a confirmées)."""
    known = {e.id: e for e in context.entities}
    out: dict[str, Confirmed] = {}
    for m in mentions:
        if not m.entity:
            continue
        if m.entity in known and known[m.entity].names:
            out.setdefault(m.entity, Confirmed(m.entity, known[m.entity].type, known[m.entity].names[0]))
        elif m.entity.startswith("new:") and m.type:
            out.setdefault(m.entity, Confirmed(m.entity, m.type, m.text))
    return sorted(out.values(), key=lambda e: e.id)


def gold_forms(window: Window, gold_dir: Path, entities: list[Confirmed]) -> dict[str, set[str]]:
    """Les formes sous lesquelles chaque entité confirmée apparaît (mentions du gold, et son nom)."""
    from .mentions import _gold_mentions
    forms: dict[str, set[str]] = {e.id: {e.name} for e in entities}
    for mentions in _gold_mentions(gold_dir, window).values():
        for surface, eid in mentions.items():
            if eid in forms:
                forms[eid].add(surface)
    return forms


def chain_forms(mentions: list[Any], entities: list[Confirmed]) -> dict[str, set[str]]:
    """Les formes trouvées par C1 pour chaque entité rattachée par C2."""
    forms: dict[str, set[str]] = {e.id: {e.name} for e in entities}
    for m in mentions:
        if m.entity in forms:
            forms[m.entity].add(m.text)
    return forms


# ---------------------------------------------------------------------------
# Mesure contre le gold (X-004)
# ---------------------------------------------------------------------------

_OUT_OF_C5 = {"create_entity", "set_visibility"}  # C2 (création) et C4 (notoriété)


def _in_scope(d: dict[str, Any]) -> bool:
    return d.get("op") not in _OUT_OF_C5 and not (d.get("op") == "set_attribute" and d.get("attribute") == "name")


@dataclass
class PassageFacts:
    doc: str
    index: int
    expected: set[tuple[Any, ...]]
    found: set[tuple[Any, ...]] = field(default_factory=set)
    optional: set[tuple[Any, ...]] = field(default_factory=set)
    supports: set[tuple[Any, ...]] = field(default_factory=set)

    @property
    def scored(self) -> set[tuple[Any, ...]]:
        return self.found - self.optional


@dataclass
class FactReport:
    finder: str
    entities: str
    passages: list[PassageFacts]
    unplaced: list[Fact] = field(default_factory=list)
    calls: list[Any] | None = None
    prompts: dict[str, int] = field(default_factory=dict)  # document → nombre d'entités données
    silent: list[Any] = field(default_factory=list)          # phrases muettes et réponses de la question ciblée
    probe_calls: list[Any] | None = None

    def summary(self) -> dict[str, Any]:
        def scores(pairs: list[tuple[set[Any], set[Any]]]) -> dict[str, Any]:
            tp = sum(len(f & e) for e, f in pairs)
            fp = sum(len(f - e) for e, f in pairs)
            fn = sum(len(e - f) for e, f in pairs)
            return {"precision": round(tp / (tp + fp), 3) if tp + fp else 0.0,
                    "recall": round(tp / (tp + fn), 3) if tp + fn else 0.0, "tp": tp, "fp": fp, "fn": fn}
        return {
            "finder": self.finder, "entities": self.entities, "passages": len(self.passages),
            "facts": scores([(p.expected, p.scored) for p in self.passages]),
            "questions": scores([(p.expected - p.supports, p.scored - p.supports) for p in self.passages]),
            "optional": f"{sum(len(p.found & p.optional) for p in self.passages)}"
                        f"/{sum(len(p.optional) for p in self.passages)}",
            "unplaced": len(self.unplaced),
            "silent_sentences": len(self.silent),
            **({"usage": summarize(self.calls, input_budget())} if self.calls is not None else {}),
            **({"probe_usage": summarize(self.probe_calls, input_budget())} if self.probe_calls is not None else {}),
        }


# ---------------------------------------------------------------------------
# Question ciblée sur les phrases muettes (E-007, choix B) : le hors schéma
# ---------------------------------------------------------------------------

PROBE_PROMPT_VERSION = 1

# Exemples volontairement pris hors de Valmont.
PROBE_SYSTEM = """Une phrase de notes de jeu de rôle (français) cite plusieurs entités. Dis quelle relation durable et actuelle
la phrase affirme entre deux d'entre elles, s'il y en a une.

Règles :
1. Seulement ce que la phrase affirme. Un fait révolu (« régnait autrefois ») ou un repère de temps (« depuis la
   guerre ») n'est pas une relation.
2. relation : un identifiant anglais en snake_case (« ally_of »), même s'il n'existe pas encore dans le monde ;
   phrase : la tournure française de la phrase qui l'exprime (« est l'allié de »).
3. subject et object sont des identifiants de la liste donnée.
4. Aucune relation affirmée : liste vide.
"""


def probe_schema() -> dict[str, Any]:
    item = {"type": "object", "additionalProperties": False, "required": ["subject", "relation", "object", "phrase"],
            "properties": {k: {"type": "string"} for k in ("subject", "relation", "object", "phrase")}}
    return {"type": "object", "additionalProperties": False, "required": ["relations"],
            "properties": {"relations": {"type": "array", "items": item}}}


@dataclass
class Silent:
    """Une phrase qui cite au moins deux entités confirmées et n'a produit aucun fait (signal sans modèle)."""

    passage: int
    sentence: str
    entities: list[str]
    answer: list[dict[str, Any]] = field(default_factory=list)


def _sentences(text: str) -> list[str]:
    import re
    return [s for s in re.split(r"(?<=[.!?…])\s+", text.strip()) if s]


def silent_sentences(window: Window, facts: list[Fact], forms: dict[str, set[str]]) -> list[Silent]:
    """Les phrases muettes : deux entités confirmées au moins (par leurs formes dans le texte), aucun fait cité."""
    from .mentions import _occurrences
    cited = [normalize(f.evidence).casefold().strip(" .") for f in facts]
    out = []
    for index, text in sorted(window.passage_texts.items()):
        for sentence in _sentences(text):
            flat = normalize(sentence).casefold().strip(" .")
            if any(c and (c in flat or flat in c) for c in cited):
                continue
            present = sorted(eid for eid, fs in forms.items() if any(_occurrences(sentence, f) for f in fs))
            if len(present) >= 2:
                out.append(Silent(index, sentence, present))
    return out


@dataclass
class RelationProbe:
    """Question étroite, sans liste de relations : « quelle relation cette phrase affirme-t-elle entre A et B ? »."""

    adapter: Any
    profile: Any

    @property
    def version(self) -> str:
        return f"probe-{PROBE_PROMPT_VERSION}:{self.profile.signature}"

    @property
    def meter(self) -> Any:
        return getattr(self.adapter, "meter", None)

    def prompt(self, silent: Silent, entities: list[Confirmed]) -> tuple[str, str]:
        known = {e.id: e for e in entities}
        lines = [f"- {eid} ({known[eid].type}) : {known[eid].name}" for eid in silent.entities if eid in known]
        return PROBE_SYSTEM, "Entités :\n" + "\n".join(lines) + "\n\nPhrase :\n" + silent.sentence

    def ask(self, silent: Silent, entities: list[Confirmed]) -> list[Fact]:
        system, user = self.prompt(silent, entities)
        silent.answer = self.adapter.complete(system, user, probe_schema())["relations"]
        return [Fact({"op": "add_relation", "from": r["subject"].strip(), "relation": r["relation"].strip(),
                      "to": r["object"].strip()}, silent.sentence, silent.passage)
                for r in silent.answer if r["subject"].strip() in silent.entities and r["object"].strip() in silent.entities]


def evaluate_facts(finder: FactFinder, windows: list[Window], entities: dict[str, list[Confirmed]], gold_dir: Path,
                   context: ExtractionContext, state: Any, label: str, probe: RelationProbe | None = None,
                   forms: dict[str, dict[str, set[str]]] | None = None) -> FactReport:
    """C5 sur chaque fenêtre, à entités données, comparé aux changements du gold qui relèvent de C5. Avec `probe`,
    chaque phrase muette (deux entités confirmées, aucun fait) reçoit ensuite une question ciblée (E-007)."""
    oracle = OracleExtractor(Path(gold_dir))
    meter = finder.meter
    first_call = len(meter.calls) if meter is not None else 0
    probe_meter = probe.meter if probe is not None else None
    first_probe = len(probe_meter.calls) if probe_meter is not None else 0
    silents: list[Silent] = []

    def run(window: Window) -> list[Fact]:
        with meter.label(window.doc_id) if meter is not None else nullcontext():
            facts = finder.find(window, entities.get(window.doc_id, []), context.schema)
        if probe is None:
            return facts
        for s in silent_sentences(window, facts, (forms or {}).get(window.doc_id, {})):
            silents.append(s)
            with probe_meter.label(f"{window.doc_id} p{s.passage}") if probe_meter is not None else nullcontext():
                facts += probe.ask(s, entities.get(window.doc_id, []))
        return facts

    with ThreadPoolExecutor(max_workers=4) as pool:
        found = list(pool.map(run, windows))
    report = FactReport(finder.version + (f"+{probe.version}" if probe is not None else ""), label, [],
                        prompts={w.doc_id: len(entities.get(w.doc_id, [])) for w in windows})
    report.silent = silents
    if probe_meter is not None:
        report.probe_calls = probe_meter.calls[first_probe:]
    # Noms des entités nouvelles à l'échelle du lot : le conseil des marchands est nommé dans notes-baron et cité
    # dans lieux-de-valmont ; gold et faits trouvés doivent le désigner par le même nom normalisé (T-ING-07).
    gold_names = _names([d for w in windows for text in w.passage_texts.values()
                         for d in oracle.extract(w.doc_id, text).drafts])
    names = {**gold_names, **{e.id.split(":", 1)[1]: name_key(e.name)
                              for es in entities.values() for e in es if e.id.startswith("new:")}}
    for window, facts in zip(windows, found):
        expected_by_passage = {i: oracle.extract(window.doc_id, text) for i, text in window.passage_texts.items()}
        report.unplaced += [f for f in facts if f.passage is None]
        for index, ex in sorted(expected_by_passage.items()):  # tous les passages : un fait en trop compte partout
            optional = {key(d, gold_names) for i, d in enumerate(ex.drafts) if i in ex.optional and _in_scope(d)}
            expected = {key(d, gold_names) for d in ex.drafts if _in_scope(d)} - optional
            p = PassageFacts(window.doc_id, index, expected, {key(f.draft, names) for f in facts if f.passage == index},
                             optional)
            p.supports = {k for k in p.expected | p.found if is_support(k, state)}
            report.passages.append(p)
    if meter is not None:
        report.calls = meter.calls[first_call:]
    return report
