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

# Variante stricte (X-008, E-010, E-004) : mêmes règles, la 3 et la 4 resserrées. Exemples hors des corpus.
SYSTEM_STRICT = SYSTEM.replace(
    """3. Une relation : une de celles données ; si aucune ne convient, propose un identifiant anglais en snake_case.""",
    """3. Une relation : une de celles données, seulement si le texte l'affirme telle quelle. Être au bord d'un lieu,
   près d'un lieu ou le traverser n'est pas y être situé ; travailler quelque part n'est pas y habiter. Si aucune
   relation de la liste ne dit exactement ce que dit le texte, ne produis rien pour ce fait.""").replace(
    """4. Un fait révolu (« régnait autrefois ») n'est pas un fait actuel ; un repère de temps (« depuis la guerre »)
   n'est pas une relation.""",
    """4. Un fait révolu (« régnait autrefois », « avant l'incendie il était ») n'est pas un fait actuel ; un repère
   de temps (« depuis la guerre », « avant l'incendie ») n'est ni un fait ni une relation.""")


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
    phrase: str = ""  # tournure française d'une relation proposée par la question ciblée


def _is_a(schema: Any, type_name: str, accepted: list[str]) -> bool:
    return any(type_name in schema.types and schema.is_subtype(type_name, t) for t in accepted)


@dataclass
class FactFinder:
    """C5 : une question au modèle, sur la fenêtre, à entités données et schéma réduit."""

    adapter: Any
    profile: Any
    strict: bool = False  # variante stricte (X-008)

    @property
    def version(self) -> str:
        return f"facts-{PROMPT_VERSION}{'+strict' if self.strict else ''}:{self.profile.signature}"

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
        return (SYSTEM_STRICT if self.strict else SYSTEM), user

    def find(self, window: Window, entities: list[Confirmed], schema: Any, state: Any = None) -> list[Fact]:
        system, user = self.prompt(window, entities, schema)
        raw = self.adapter.complete(system, user, output_schema())
        return check_facts(self._facts(raw, window, entities, schema), entities, schema, state, self.rejected)

    def __post_init__(self) -> None:
        self.rejected: list[tuple[Fact, str]] = []  # écartés par les contrôles sans modèle (E-011), avec la raison

    def _facts(self, raw: dict[str, Any], window: Window, entities: list[Confirmed], schema: Any) -> list[Fact]:
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


def check_facts(facts: list[Fact], entities: list[Confirmed], schema: Any, state: Any,
                rejected: list[tuple[Fact, str]]) -> list[Fact]:
    """Contrôles sans modèle après C5 (E-011) :

    - une relation du schéma dont les types ne conviennent pas (« rules » vers une Faction) est écartée ;
    - un alias égal au nom ou à un alias connu de l'entité (« la Sorgue » pour la Sorgue) est écarté ;
    - une valeur proche de la valeur connue (« bourgmèstre » pour « bourgmestre ») prend la valeur connue : c'est
      un support, pas une collision.
    """
    from rapidfuzz.distance import JaroWinkler

    from .matching import fold
    types = {e.id: e.type for e in entities}
    names: dict[str, set[str]] = {e.id: {fold(e.name)} for e in entities}
    for f in (state.facts.values() if state is not None else ()):
        if f.kind == "value" and f.name == "aliases" and f.subject in names:
            names[f.subject].add(fold(str(f.value)))
    kept = []
    for fact in facts:
        d = fact.draft
        if d["op"] == "add_relation" and d["relation"] in schema.relations:
            r = schema.relations[d["relation"]]
            subject, target = types.get(d["from"]), types.get(d["to"])
            if subject and target and not (_is_a(schema, subject, r.from_) and _is_a(schema, target, r.to)):
                rejected.append((fact, f"types : {d['relation']} va de {'|'.join(r.from_)} vers {'|'.join(r.to)}"))
                continue
        if d["op"] == "add_value" and d.get("attribute") == "aliases" and fold(str(d["value"])) in names.get(d["entity"], ()):
            rejected.append((fact, "alias égal au nom"))
            continue
        if d["op"] == "set_attribute" and state is not None:
            known = state.facts.get(("attr", d["entity"], d["attribute"]))
            if known is not None and str(known.value) != d["value"]:
                a, b = fold(str(known.value)), fold(str(d["value"]))
                if a == b or JaroWinkler.normalized_similarity(a, b) >= 0.9:
                    fact.draft = {**d, "value": known.value}  # « bourgmèstre » : la valeur connue
        kept.append(fact)
    return kept


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
            # le nom donné est la forme de référence du groupe (celle qui a fait l'identifiant), si elle est citée
            reference = next((x.text for x in mentions if x.entity == m.entity
                              and f"new:{name_key(x.text)}" == m.entity), m.text)
            out.setdefault(m.entity, Confirmed(m.entity, m.type, reference))
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


OUT_OF_SCHEMA = "(hors schéma)"


def _key(d: dict[str, Any], names: dict[str, str], schema: Any) -> tuple[Any, ...]:
    """Clé de comparaison : une relation hors schéma se compare par sa paire d'entités, pas par l'identifiant
    proposé (`detests` ou `hates`) : c'est l'auteur qui le fixera en l'acceptant (§6.6)."""
    if d.get("op") == "add_relation" and d.get("relation") not in schema.relations:
        d = {**d, "relation": OUT_OF_SCHEMA}
    return key(d, names)


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
    rejected: list[Any] = field(default_factory=list)        # faits écartés par les contrôles (E-011)
    judged: list[Any] = field(default_factory=list)          # faits jugés par le critique, avec son verdict (X-009)
    critic_calls: list[Any] | None = None
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
            "rejected": len(self.rejected),
            **({"critic": {v: sum(1 for _, j in self.judged if j.get("verdict") == v)
                           for v in ("supported", "unsure", "not_supported")}} if self.judged else {}),
            **({"usage": summarize(self.calls, input_budget())} if self.calls is not None else {}),
            **({"probe_usage": summarize(self.probe_calls, input_budget())} if self.probe_calls is not None else {}),
            **({"critic_usage": summarize(self.critic_calls, input_budget())} if self.critic_calls is not None else {}),
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

# Variante (X-008, E-012) : les relations connues, compatibles avec les types, données comme préférence.
PROBE_RELATIONS_RULE = """5. Relations connues du monde (liste donnée) : si l'une dit la même chose que la phrase, utilise son identifiant
   et sa direction ; sinon seulement, propose un identifiant nouveau.
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


def silent_sentences(window: Window, facts: list[Fact], forms: dict[str, set[str]],
                     by_pair: bool = False) -> list[Silent]:
    """Les phrases muettes : deux entités confirmées au moins (par leurs formes dans le texte), aucun fait cité.

    Avec `by_pair` (X-008, E-012) : une phrase dont au moins une **paire** d'entités citées n'est reliée par aucune
    relation trouvée dans la fenêtre, même si la phrase a produit un autre fait (« elle tient l'apothicairerie
    près du pont. elle deteste les bateliers ») ; la question ne porte que sur les entités de ces paires."""
    from itertools import combinations

    from .mentions import _occurrences
    cited = [normalize(f.evidence).casefold().strip(" .") for f in facts]
    linked = {frozenset((f.draft["from"], f.draft["to"])) for f in facts if f.draft.get("op") == "add_relation"}
    out = []
    for index, text in sorted(window.passage_texts.items()):
        # par paire, l'unité est le passage : « elle deteste les bateliers » ne cite Ysolde que par un pronom ;
        # c'est la phrase d'avant, dans le même passage, qui la nomme (pas de coréférence, C3, pour l'instant)
        for sentence in ([text] if by_pair else _sentences(text)):
            present = sorted(eid for eid, fs in forms.items() if any(_occurrences(sentence, f) for f in fs))
            if len(present) < 2:
                continue
            if by_pair:
                loose = {e for a, b in combinations(present, 2) if frozenset((a, b)) not in linked for e in (a, b)}
                if loose:
                    out.append(Silent(index, sentence, sorted(loose)))
                continue
            flat = normalize(sentence).casefold().strip(" .")
            if not any(c and (c in flat or flat in c) for c in cited):
                out.append(Silent(index, sentence, present))
    return out


@dataclass
class RelationProbe:
    """Question étroite, sans liste de relations : « quelle relation cette phrase affirme-t-elle entre A et B ? »."""

    adapter: Any
    profile: Any
    with_relations: bool = False  # relations connues données comme préférence (X-008)
    by_pair: bool = False         # signal par paire d'entités non reliées, plutôt que par phrase muette (X-008)

    @property
    def version(self) -> str:
        flags = ("+rel" if self.with_relations else "") + ("+pairs" if self.by_pair else "")
        return f"probe-{PROBE_PROMPT_VERSION}{flags}:{self.profile.signature}"

    @property
    def meter(self) -> Any:
        return getattr(self.adapter, "meter", None)

    def prompt(self, silent: Silent, entities: list[Confirmed], schema: Any = None) -> tuple[str, str]:
        known = {e.id: e for e in entities}
        lines = [f"- {eid} ({known[eid].type}) : {known[eid].name}" for eid in silent.entities if eid in known]
        user = "Entités :\n" + "\n".join(lines)
        if not self.with_relations or schema is None:
            return PROBE_SYSTEM, user + "\n\nPhrase :\n" + silent.sentence
        types = {known[eid].type for eid in silent.entities if eid in known}
        relations = [f"- {name} : {'|'.join(r.from_)} → {'|'.join(r.to)} ({(r.labels or {}).get('fr', name)})"
                     for name, r in sorted(schema.relations.items())
                     if any(_is_a(schema, t, r.from_) for t in types) and any(_is_a(schema, t, r.to) for t in types)]
        return (PROBE_SYSTEM + PROBE_RELATIONS_RULE,
                user + "\n\nRelations connues :\n" + ("\n".join(relations) or "- (aucune)")
                + "\n\nPhrase :\n" + silent.sentence)

    def ask(self, silent: Silent, entities: list[Confirmed], schema: Any = None) -> list[Fact]:
        system, user = self.prompt(silent, entities, schema)
        silent.answer = self.adapter.complete(system, user, probe_schema())["relations"]
        return [Fact({"op": "add_relation", "from": r["subject"].strip(), "relation": r["relation"].strip(),
                      "to": r["object"].strip()}, silent.sentence, silent.passage, r.get("phrase", ""))
                for r in silent.answer if r["subject"].strip() in silent.entities and r["object"].strip() in silent.entities]


# ---------------------------------------------------------------------------
# Critique (C6) : un fait qui pose une question, jugé contre son passage (X-009, E-010, E-004)
# ---------------------------------------------------------------------------

CRITIC_PROMPT_VERSION = 2

# Catégories générales tirées des axes de test (axes-corpus.md), exemples pris hors des corpus.
CRITIC_SYSTEM = """Tu vérifies un fait proposé à partir de notes de jeu de rôle (français). Tu ne cherches pas d'autres faits :
tu dis seulement si le passage affirme celui-ci.

Verdict :
- supported : le passage affirme ce fait, explicitement, comme un état actuel du monde.
- not_supported : le fait n'est pas affirmé tel quel. En particulier : déduit d'une proximité ou d'une description
  (« au bord de », « près de », « traverse ») ; tiré d'un repère de temps (« avant la guerre », « depuis l'incendie ») ;
  passé révolu (« autrefois ») ; rumeur ou ouï-dire (« on dit que », « paraît que ») ; hypothèse ou idée (« et si ») ;
  opinion ou jugement vague (« pas fiable », « louche »).
- unsure : le passage le laisse entendre sans l'affirmer.
Un fait secret, caché aux joueurs ou réservé à plus tard reste un fait du monde : sa notoriété est une autre
question, qui ne te concerne pas. Une entité peut être désignée par un de ses autres noms (donnés entre crochets).
reason : quelques mots.
"""


def critic_schema() -> dict[str, Any]:
    return {"type": "object", "additionalProperties": False, "required": ["verdict", "reason"],
            "properties": {"verdict": {"type": "string", "enum": ["supported", "not_supported", "unsure"]},
                           "reason": {"type": "string"}}}


@dataclass
class Critic:
    """C6 : une question étroite par fait qui pose une question (pas les supports) ; il **met de côté** ce qu'il juge
    non soutenu, sans décider (choix 2 du chantier : l'auteur reprend un fait mis de côté en un geste)."""

    adapter: Any
    profile: Any

    @property
    def version(self) -> str:
        return f"critic-{CRITIC_PROMPT_VERSION}:{self.profile.signature}"

    @property
    def meter(self) -> Any:
        return getattr(self.adapter, "meter", None)

    def prompt(self, fact: Fact, passage: str, entities: list[Confirmed], schema: Any,
               other_names: dict[str, tuple[str, ...]] | None = None) -> tuple[str, str]:
        known = {e.id: e for e in entities}

        def name(eid: str) -> str:
            if eid not in known:
                return eid
            others = [n for n in (other_names or {}).get(eid, ()) if n != known[eid].name]
            return f"{known[eid].name} ({known[eid].type})" + (f" [{', '.join(others)}]" if others else "")

        d = fact.draft
        if d["op"] == "add_relation":
            r = schema.relations.get(d["relation"])
            label = (r.labels or {}).get("fr", d["relation"]) if r is not None else (fact.phrase or d["relation"])
            proposed = f"{name(d['from'])} — {label} — {name(d['to'])}"
        else:
            attr = d.get("attribute", "")
            definition = schema.attributes_of(known[d["entity"]].type).get(attr) \
                if d.get("entity") in known and known[d["entity"]].type in schema.types else None
            label = (definition.labels or {}).get("fr", attr) if definition is not None else attr
            proposed = f"{name(d['entity'])} — {label} : {d.get('value')}"
        return CRITIC_SYSTEM, f"Passage :\n{passage}\n\nFait proposé :\n{proposed}"

    def judge(self, fact: Fact, passage: str, entities: list[Confirmed], schema: Any,
              other_names: dict[str, tuple[str, ...]] | None = None) -> dict[str, Any]:
        system, user = self.prompt(fact, passage, entities, schema, other_names)
        return self.adapter.complete(system, user, critic_schema())


def evaluate_facts(finder: FactFinder, windows: list[Window], entities: dict[str, list[Confirmed]], gold_dir: Path,
                   context: ExtractionContext, state: Any, label: str, probe: RelationProbe | None = None,
                   forms: dict[str, dict[str, set[str]]] | None = None, critic: Critic | None = None) -> FactReport:
    """C5 sur chaque fenêtre, à entités données, comparé aux changements du gold qui relèvent de C5. Avec `probe`,
    chaque phrase muette (deux entités confirmées, aucun fait) reçoit ensuite une question ciblée (E-007). Avec
    `critic`, chaque fait qui pose une question (pas un support) est jugé contre son passage ; un fait non soutenu est
    mis de côté (X-009)."""
    oracle = OracleExtractor(Path(gold_dir))
    # Noms des entités nouvelles à l'échelle du lot : le conseil des marchands est nommé dans notes-baron et cité
    # dans lieux-de-valmont ; gold et faits trouvés doivent le désigner par le même nom normalisé (T-ING-07).
    gold_names = _names([d for w in windows for text in w.passage_texts.values()
                         for d in oracle.extract(w.doc_id, text).drafts])
    names = {**gold_names, **{e.id.split(":", 1)[1]: name_key(e.name)
                              for es in entities.values() for e in es if e.id.startswith("new:")}}
    critic_meter = critic.meter if critic is not None else None
    first_critic = len(critic_meter.calls) if critic_meter is not None else 0
    judged: list[tuple[Fact, dict[str, Any]]] = []
    meter = finder.meter
    first_call = len(meter.calls) if meter is not None else 0
    probe_meter = probe.meter if probe is not None else None
    first_probe = len(probe_meter.calls) if probe_meter is not None else 0
    silents: list[Silent] = []

    def run(window: Window) -> list[Fact]:
        with meter.label(window.doc_id) if meter is not None else nullcontext():
            facts = finder.find(window, entities.get(window.doc_id, []), context.schema, state)
        if probe is not None:
            for s in silent_sentences(window, facts, (forms or {}).get(window.doc_id, {}), probe.by_pair):
                silents.append(s)
                with probe_meter.label(f"{window.doc_id} p{s.passage}") if probe_meter is not None else nullcontext():
                    facts += check_facts(probe.ask(s, entities.get(window.doc_id, []), context.schema),
                                         entities.get(window.doc_id, []), context.schema, state, finder.rejected)
        if critic is None:
            return facts
        kept = []
        for f in facts:
            if f.passage is None or is_support(key(f.draft, names), state):
                kept.append(f)  # le critique ne juge que ce qui pose une question
                continue
            with critic_meter.label(f"{window.doc_id} p{f.passage}") if critic_meter is not None else nullcontext():
                verdict = critic.judge(f, window.passage_texts[f.passage], entities.get(window.doc_id, []),
                                       context.schema, {e.id: e.names for e in context.entities})
            judged.append((f, verdict))
            if verdict.get("verdict") != "not_supported":
                kept.append(f)
        return kept

    with ThreadPoolExecutor(max_workers=4) as pool:
        found = list(pool.map(run, windows))
    report = FactReport(finder.version + (f"+{probe.version}" if probe is not None else "")
                        + (f"+{critic.version}" if critic is not None else ""), label, [],
                        prompts={w.doc_id: len(entities.get(w.doc_id, [])) for w in windows})
    report.judged = judged
    if critic_meter is not None:
        report.critic_calls = critic_meter.calls[first_critic:]
    report.silent = silents
    report.rejected = list(finder.rejected)
    if probe_meter is not None:
        report.probe_calls = probe_meter.calls[first_probe:]
    for window, facts in zip(windows, found):
        expected_by_passage = {i: oracle.extract(window.doc_id, text) for i, text in window.passage_texts.items()}
        report.unplaced += [f for f in facts if f.passage is None]
        for index, ex in sorted(expected_by_passage.items()):  # tous les passages : un fait en trop compte partout
            optional = {_key(d, gold_names, context.schema) for i, d in enumerate(ex.drafts)
                        if i in ex.optional and _in_scope(d)}
            expected = {_key(d, gold_names, context.schema) for d in ex.drafts if _in_scope(d)} - optional
            p = PassageFacts(window.doc_id, index, expected,
                             {_key(f.draft, names, context.schema) for f in facts if f.passage == index},
                             optional)
            p.supports = {k for k in p.expected | p.found if is_support(k, state)}
            report.passages.append(p)
    if meter is not None:
        report.calls = meter.calls[first_call:]
    return report
