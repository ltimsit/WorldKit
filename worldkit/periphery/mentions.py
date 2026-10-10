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

# Variante A (X-003) : exemple volontairement pris hors de Valmont, pour ne pas régler le prompt sur le corpus.
SHORT_FORMS_RULE = """5. Relève aussi chaque forme plus courte ou chaque désignation d'une entité déjà relevée, à chaque fois
   qu'elle est employée : un prénom seul (« Marianne » pour « Marianne Ostrel »), une fonction (« le capitaine »).
   Une entrée par forme, même si l'entité est déjà relevée sous une autre forme.
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
    struck: tuple[tuple[int, int], ...] = ()     # portions barrées (~~…~~) : corrigées par l'auteur (E-009)

    def passage_at(self, position: int) -> int | None:
        return next((i for i, start, end in self.passages if start <= position < end), None)

    def is_struck(self, start: int, end: int) -> bool:
        return any(s <= start and end <= e for s, e in self.struck)


def document_window(path: str | Path) -> Window:
    return window_of(read_document(path))


def window_of(doc: Any) -> Window:
    """La fenêtre d'une version de document : son titre, puis ses passages, chacun à sa place."""
    text = f"# {doc.title}\n\n" if doc.title else ""
    spans = []
    for p in doc.passages:
        start = len(text)
        text += p.text
        spans.append((p.index, start, len(text)))
        text += "\n\n"
    text = text.rstrip()
    struck = tuple((m.start(), m.end()) for m in re.finditer(r"~~.+?~~", text, re.DOTALL))
    return Window(doc.doc_id, text, tuple(spans), {p.index: p.text for p in doc.passages}, struck)


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


def known_mentions(window: Window, entities: tuple[KnownEntity, ...],
                   titles: dict[str, list[str]] | None = None) -> list[Mention]:
    """C1a : les noms et alias connus, trouvés tels quels (sans modèle) ; et « le <titre> » quand ce titre est
    porté aujourd'hui par une seule entité (« le baron » : Odon). Un titre partagé (« le roi ») n'est pas cherché."""
    found = []
    for e in entities:
        for name in e.names:
            for form in {name, re.sub(r"^(?:(?:les|le|la)\s+|l['’]\s*)", "", name, flags=re.IGNORECASE)}:
                for start in _occurrences(window.text, form):
                    if window.is_struck(start, start + len(form.strip())):
                        continue  # texte barré : corrigé par l'auteur (E-009)
                    found.append(Mention(window.text[start:start + len(form.strip())], start,
                                         window.passage_at(start), e.type, "known", entity=e.id, rule="exact"))
    types = {e.id: e.type for e in entities}
    for title, holders in (titles or {}).items():
        if len(holders) != 1:
            continue
        for form in (f"le {title}", f"la {title}", f"l'{title}", f"l’{title}"):
            for start in _occurrences(window.text, form):
                found.append(Mention(window.text[start:start + len(form)], start, window.passage_at(start),
                                     types.get(holders[0]), "known", entity=holders[0], rule="title"))
    return _keep_longest(found)


STOPWORDS = {"de", "du", "des", "la", "le", "les", "l", "d", "et", "von", "van", "of", "the"}


def short_forms(window: Window, mentions: list[Mention], entities: tuple[KnownEntity, ...], schema: Any,
                person_types: tuple[str, ...] = ("Character",), anywhere: bool = False) -> list[Mention]:
    """Variante B (sans modèle) : les mots d'un nom de personne repérée (« Odon » dans « Odon de Brume ») sont
    cherchés dans la fenêtre, sauf un mot qui est lui-même un nom connu (« Brume ») ou qui appartient au nom de
    plusieurs personnes (« Jehan » pour Jehan Marcastel et Jehan Leblond : homonymes). Recherche sensible à la casse :
    un mot à majuscule. Avec `anywhere` (choix 40 du chantier), toute personne connue est cherchée, même absente de la
    fenêtre en entier (« Ysolde » sans « Ysolde Marcastel ») : la forme trouvée est **à vérifier** (`check_of`), un
    alias la rend sûre. Heuristique : `person_types` dépend du schéma du monde (ici le schéma de Valmont)."""
    def is_person(t: str | None) -> bool:
        return t is not None and any(t in schema.types and schema.is_subtype(t, p) for p in person_types)

    known_keys = {name_key(n) for e in entities for n in e.names}
    people: dict[str, str] = {}  # identifiant → nom de référence
    for e in entities:
        if is_person(e.type) and e.names:
            people[e.id] = e.names[0]
    for m in mentions:
        if m.entity and is_person(m.type) and m.entity not in people:
            people[m.entity] = m.text
    words: dict[str, set[str]] = {}
    for eid, name in people.items():
        for w in re.findall(r"[^\W\d_][\w’'-]*", name):
            if len(w) >= 3 and w[0].isupper() and w.casefold() not in STOPWORDS and name_key(w) not in known_keys:
                words.setdefault(w, set()).add(eid)
    found = []
    types = {e.id: e.type for e in entities}
    for w, owners in words.items():
        if len(owners) != 1 or not (anywhere or any(m.entity in owners for m in mentions)):
            continue  # mot partagé, ou personne absente de la fenêtre
        eid = next(iter(owners))
        for start in (m.start() for m in re.finditer(r"(?<![\w-])" + re.escape(w) + r"(?![\w-])", window.text)):
            if window.is_struck(start, start + len(w)):
                continue  # texte barré : corrigé par l'auteur (E-009)
            if not any(k.start <= start and start + len(w) <= k.end for k in mentions + found):
                found.append(Mention(w, start, window.passage_at(start), next(
                    (m.type for m in mentions if m.entity == eid), types.get(eid)), "short", entity=eid,
                    rule="short"))
    return found


_ARTICLE = re.compile(r"^(?:(?:les|le|la)\s+|l['’]\s*)", re.IGNORECASE)


def check_of(m: Mention, names: tuple[str, ...]) -> str | None:
    """Pourquoi une mention sans modèle est **à vérifier** (signal sans décision, X-012) : `short`, forme courte d'un
    nom de personne (choix 40) ; `case`, casse différente du nom connu, article mis à part (« une brume épaisse »
    pour Brume, « corbelle » dans des notes brouillon : homographe possible). Sinon None."""
    if m.rule == "short":
        return "short"
    if m.rule == "exact" and _ARTICLE.sub("", m.text).strip() not in {_ARTICLE.sub("", n).strip() for n in names}:
        return "case"
    return None


@dataclass
class MentionFinder:
    """C1b : une question au modèle, sur toute la fenêtre, sans la liste des entités connues."""

    adapter: Any
    profile: Any
    short_forms: bool = False  # variante A : une consigne de plus sur les formes courtes

    @property
    def version(self) -> str:
        return f"mentions-{PROMPT_VERSION}{'+sf' if self.short_forms else ''}:{self.profile.signature}"

    @property
    def system(self) -> str:
        return SYSTEM + SHORT_FORMS_RULE if self.short_forms else SYSTEM

    @property
    def meter(self) -> Any:
        return getattr(self.adapter, "meter", None)

    def prompt(self, window: Window, context: ExtractionContext) -> tuple[str, str]:
        schema = context.schema
        lines = [f"- {name} : {(schema.types[name].labels or {}).get('fr', name)}" for name in sorted(schema.types)]
        return self.system, "Types du monde :\n" + "\n".join(lines) + "\n\nTexte :\n" + window.text

    def find(self, window: Window, context: ExtractionContext) -> list[Mention]:
        system, user = self.prompt(window, context)
        raw = self.adapter.complete(system, user, output_schema(sorted(context.schema.types)))
        found = []
        for m in raw["mentions"]:
            # La forme sans article initial aussi : « le conseil des marchands » se lit « au conseil des marchands »
            bare = re.sub(r"^(?:(?:les|le|la)\s+|l['’]\s*)", "", m["text"].strip(), flags=re.IGNORECASE)
            starts: dict[int, str] = {}
            for form in (m["text"].strip(), bare):
                for start in _occurrences(window.text, form):
                    if not window.is_struck(start, start + len(form)):  # E-009
                        starts.setdefault(start, form)
            for start, form in starts.items():
                found.append(Mention(window.text[start:start + len(form)], start, window.passage_at(start),
                                     m["type"], "model", m["confidence"], m.get("reason") or ""))
            struck_only = any(_occurrences(window.text, f) for f in (m["text"].strip(), bare))
            if not starts and not struck_only:  # texte réécrit par le modèle : gardé, sans position
                found.append(Mention(m["text"], -1, None, m["type"], "model", m["confidence"], m.get("reason") or ""))
        return found


def similar_mentions(window: Window, entities: tuple[KnownEntity, ...], existing: list[Mention]) -> list[Mention]:
    """Signal sans modèle (X-012) : une suite de mots qui **ressemble** à un nom connu sans l'être (« la chuute »,
    « Brme ») devient une mention **douteuse**, avec le candidat ; jamais rattachée d'office : « brume » au sens de
    brouillard ressemble aussi à Brume. Une portion déjà couverte par une autre mention est ignorée."""
    from .matching import LINK, fold, similarity
    words = [(m.start(), m.end()) for m in re.finditer(r"[^\W\d_][\w'’-]*", window.text)]
    found: list[Mention] = []
    for e in entities:
        for name in e.names:
            target = fold(name)
            size = len(target.split())
            if len(target) < 4:
                continue
            for i in range(len(words) - size + 1):
                start, end = words[i][0], words[i + size - 1][1]
                span = window.text[start:end]
                if fold(span) == target or window.is_struck(start, end):
                    continue
                if any(m.start < end and start < m.end for m in existing + found):
                    continue
                if similarity(span, name) >= LINK and fold(span)[:1] == target[:1]:
                    found.append(Mention(span, start, window.passage_at(start), e.type, "similar", "doubt",
                                         rule="doubt", candidates=(e.id,)))
    return found


def merge(known: list[Mention], found: list[Mention]) -> list[Mention]:
    """C1 : toutes les portions connues sont gardées. Une portion du modèle est écartée si elle est contenue dans
    une portion connue (« Chute » dans « la Chute ») ; elle est gardée si elle en contient une : les mentions
    s'imbriquent (« baron de Brume » désigne Odon, « Brume » désigne la ville)."""
    placed = _keep_longest([m for m in found if m.start >= 0])
    unplaced = [m for m in found if m.start < 0]
    kept = [m for m in placed if not any(k.start <= m.start and m.end <= k.end for k in known)]
    return sorted(known + kept, key=lambda m: (m.start, -(m.end - m.start))) + unplaced


def _compatible(schema: Any, entity_type: str, mention_type: str | None) -> bool:
    return mention_type is None or schema.is_subtype(entity_type, mention_type) \
        or schema.is_subtype(mention_type, entity_type)


@dataclass
class Resolver:
    """C2 : recoupement déterministe avec l'état. Un doute (plusieurs candidats) est laissé à l'auteur."""

    entities: tuple[KnownEntity, ...]
    titles: dict[str, list[str]]  # titre normalisé → entités qui le portent aujourd'hui
    schema: Any
    linked: set[frozenset[str]] = field(default_factory=set)  # paires d'entités reliées par une relation

    @classmethod
    def from_state(cls, context: ExtractionContext, state: Any) -> Resolver:
        titles: dict[str, list[str]] = {}
        for e in context.entities:
            fact = state.facts.get(("attr", e.id, "title")) if state is not None else None
            if fact is not None:
                titles.setdefault(name_key(str(fact.value)), []).append(e.id)
        linked = {frozenset((f.subject, f.target)) for f in (state.facts.values() if state is not None else ())
                  if f.kind == "rel"}
        return cls(context.entities, titles, context.schema, linked)

    def designation(self, key: str) -> tuple[str | None, tuple[str, ...]] | None:
        """E-006 : « <mot> de <nom connu> » (« baron de Brume », « royaume de Valmont »). Rattachée à l'entité qui
        porte ce titre et est reliée à l'entité nommée, si elle est seule (« baron de Brume » : Odon, baron, gouverne
        Brume) ; sinon un doute, avec l'entité nommée pour indice, jamais une entité nouvelle. None : autre forme."""
        found = re.match(r"^(.+?)\s+(?:de|du|des|d['’])\s*(.+)$", key)
        if found is None:
            return None
        from .matching import best_matches, decide, fold
        head, tail = found.group(1), fold(found.group(2))
        named = [e.id for e in self.entities if tail in {fold(n) for n in e.names}]
        if not named:  # « port de Burme », « royaume de vaalmont » : le nom connu peut porter une faute (X-011)
            entity, _ = decide(best_matches(tail, {e.id: list(e.names) for e in self.entities}))
            named = [entity] if entity else []
        if len(named) != 1:
            return None
        holders = [h for h in self.titles.get(head, []) if frozenset((h, named[0])) in self.linked]
        if len(holders) == 1:
            return holders[0], ()
        return None, tuple(sorted(set(holders) | set(named)))

    def resolve(self, m: Mention) -> Mention:
        """Nom exact (forme pliée), titre unique, ressemblance (score, X-007), désignation (E-006) ; sinon doute ou
        entité nouvelle. Les entités nouvelles d'un lot sont regroupées ensuite (`cluster_new`)."""
        from .matching import best_matches, decide, fold
        if m.entity is not None:
            return m
        key = fold(m.text)
        compatible = [e for e in self.entities if _compatible(self.schema, e.type, m.type)]
        exact = [e for e in compatible if key in {fold(n) for n in e.names}]
        if len(exact) == 1:
            m.entity, m.rule = exact[0].id, "exact"
            return m
        if len(exact) > 1:
            m.rule, m.candidates = "ambiguous", tuple(sorted(e.id for e in exact))
            return m
        holders = [h for t, hs in self.titles.items() if fold(t) == key for h in hs]
        if len(holders) == 1:
            m.entity, m.rule = holders[0], "title"
            return m
        entity, doubtful = decide(best_matches(m.text, {e.id: list(e.names) for e in compatible}))
        if entity is not None:
            m.entity, m.rule = entity, "similar"
            return m
        designation = self.designation(name_key(m.text))
        if designation is not None:
            entity, hints = designation
            if entity is not None:
                m.entity, m.rule = entity, "designation"
            else:
                m.rule, m.candidates = "doubt", hints  # désignation d'une entité connue : à préciser par l'auteur
            return m
        if doubtful or len(holders) > 1:
            m.rule, m.candidates = "doubt", tuple(sorted(set(doubtful) | set(holders)))
            return m
        m.entity, m.rule = f"new:{name_key(m.text)}", "new"
        return m

    def cluster_new(self, mentions: list[Mention]) -> None:
        """Regroupe les entités nouvelles du lot qui se ressemblent (« Bertrand Ostrell », « Ostrel » : Bertrand
        Ostrel), indépendamment de l'ordre des documents (R-PRI-03) : la forme la plus longue d'abord, puis l'ordre
        alphabétique. Une forme ambiguë entre deux entités nouvelles devient un doute."""
        from .matching import best_matches, decide, fold
        news = sorted((m for m in mentions if m.rule == "new"), key=lambda m: (-len(fold(m.text)), fold(m.text)))
        clusters: dict[str, tuple[str | None, list[str]]] = {}  # identifiant → (type, formes)
        for m in news:
            pool = {cid: forms for cid, (t, forms) in clusters.items()
                    if t is None or m.type is None or _compatible(self.schema, t, m.type)}
            entity, doubtful = decide(best_matches(m.text, pool))
            if entity is not None:
                if entity != m.entity:
                    m.entity, m.rule = entity, "similar"
                clusters[entity][1].append(m.text)
            elif doubtful:
                m.entity, m.rule, m.candidates = None, "doubt", doubtful
            else:
                clusters.setdefault(m.entity, (m.type, []))[1].append(m.text)
        # Nom de référence d'un groupe : la forme la plus proche de toutes les autres (« Bertrand Ostrel » entre
        # « Bertrand Ostrell » et « Ostrel »), pas la plus longue, qui peut porter une faute.
        from .matching import similarity
        renamed = {}
        for cid, (_, forms) in clusters.items():
            best = max(sorted(set(forms)), key=lambda f: (sum(similarity(f, o) for o in forms), len(f)))
            renamed[cid] = f"new:{name_key(best)}"
        for m in mentions:
            if m.entity in renamed:
                m.entity = renamed[m.entity]


# ---------------------------------------------------------------------------
# Mesure contre les mentions du gold (X-002)
# ---------------------------------------------------------------------------

GESTURES = {"keep": 1, "confirm": 1, "remove": 1, "change": 2, "add": 3}  # poids provisoires (chantier §9)


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
    # Une portion qui chevauche une mention appariée et désigne la même entité est la même mention
    # (« Mervin » dans « roi Mervin ») : ni bonne ni en trop.
    p.extra = [m for m in free if not any(h.entity is not None and h.entity == m.entity
                                          and m.start < h.end and h.start < m.end for _, h in p.matched)]


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
        # Un doute dont le bon choix est proposé (le candidat, ou « nouvelle » quand le gold attend une entité
        # nouvelle) se règle en un geste de confirmation (X-012).
        confirm = sum(1 for p in self.passages for s, m in p.matched if not p.resolved_ok(s, m) and m.rule == "doubt"
                      and (p.gold[s] in m.candidates or (not m.candidates and p.gold[s].startswith("new:"))))
        wrong = tp - ok - confirm
        gestures = {"keep": ok, "confirm": confirm, "remove": fp, "change": wrong, "add": fn}
        # Entités nouvelles proposées (une par nom normalisé dans le lot) : justes si le gold attend une entité
        # nouvelle à cet endroit ; fausses sinon, chacune une création à refuser en revue (E-006).
        proposed = {m.entity for p in self.passages for m in p.found if m.entity and m.entity.startswith("new:")}
        justified = {m.entity for p in self.passages for s, m in p.matched
                     if m.entity in proposed and p.gold[s].startswith(("new:", "pending:"))}
        doubts = sum(1 for p in self.passages for m in p.found if m.rule in ("doubt", "ambiguous"))
        return {
            "finder": self.finder, "passages": len(self.passages), "gold_mentions": gold,
            "c1": {"recall": round(tp / gold, 3) if gold else 0.0,
                   "precision": round(tp / (tp + fp), 3) if tp + fp else 0.0, "tp": tp, "fp": fp, "fn": fn,
                   "found_without_model": known_tp, "recall_without_model": round(known_tp / gold, 3) if gold else 0.0,
                   "unplaced": len(self.unplaced)},
            "c2": {"resolved_ok": ok, "of": tp, "accuracy": round(ok / tp, 3) if tp else 0.0, "rules": rules,
                   "new_proposed": len(proposed), "new_false": len(proposed - justified),
                   "false_new": sorted(e.split(":", 1)[1] for e in proposed - justified), "doubts": doubts},
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
                      context: ExtractionContext, state: Any, repeat: int = 1,
                      with_short_forms: bool = False, with_enunciation: bool = False,
                      with_signals: bool = False) -> MentionReport:
    """C1 (C1a, et C1b si `finder`) puis C2 sur chaque document, comparés aux mentions du gold ; avec
    `with_short_forms`, la variante B ajoute les formes courtes des personnes repérées ; avec `with_enunciation`,
    une note de travail de l'auteur ne propose aucune entité nouvelle (C4, X-010)."""
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
    label = (finder.version if finder is not None else "known-only") + ("+short" if with_short_forms else "")
    report = MentionReport(label, [])
    per_window = []
    for window, runs in zip(windows, model_runs):
        mentions = merge(known_mentions(window, context.entities, resolver.titles), runs[0] if runs else [])
        if with_signals:  # X-012 : signaler sans décider
            mentions = sorted(mentions + similar_mentions(window, context.entities, mentions), key=lambda m: m.start)
        for m in mentions:
            resolver.resolve(m)
        per_window.append(mentions)
    if with_enunciation:  # silence d'une note de travail : ni idée d'intrigue, ni TODO ne créent d'entité (AX-E1, E5)
        from .facts import enunciation
        per_window = [[m for m in ms if not (m.rule == "new" and m.passage is not None
                                             and enunciation(w.passage_texts.get(m.passage, "")) == "note")]
                      for w, ms in zip(windows, per_window)]
    resolver.cluster_new([m for ms in per_window for m in ms])  # entités nouvelles du lot (T-ING-07, R-PRI-03)
    if with_signals:  # X-012 : une entité nouvelle peu sûre (minuscules seules, une seule occurrence) est un doute
        everything = [m for ms in per_window for m in ms]
        for eid in {m.entity for m in everything if m.entity and m.entity.startswith("new:")}:
            forms = [m for m in everything if m.entity == eid]
            if len(forms) == 1 and not any(c.isupper() for c in forms[0].text):
                forms[0].entity, forms[0].rule, forms[0].candidates = None, "doubt", ()
    for window, runs, mentions in zip(windows, model_runs, per_window):
        if with_short_forms:
            mentions = sorted(mentions + short_forms(window, mentions, context.entities, context.schema),
                              key=lambda m: (m.start, -(m.end - m.start)))
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
