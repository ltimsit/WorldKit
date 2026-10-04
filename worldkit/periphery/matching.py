"""Ressemblance de noms pour le recoupement (C2) : comparer sans réécrire (chantier ingestion, E-008).

Plutôt qu'une règle par cas observé, un **score** tiré d'indices généraux, puis trois issues (rattachée, doute,
nouvelle) selon deux seuils :

- **pliage** pour comparer (le texte n'est jamais réécrit) : casse, article initial, accents, ponctuation et trait
  d'union, abréviations usuelles (« st » → saint) ;
- **Jaro-Winkler** sur les formes pliées : fautes de frappe (« Marcastell », « Ostrell ») ;
- **inclusion de mots** : une forme dont les mots pleins sont contenus dans l'autre (« Odon » dans « Odon de
  Brume », « la guilde » dans « la Guilde des Bateliers »), le score croissant avec la part couverte ;
- **sigle** (« GdB ») et **prénom suivi d'une initiale** (« Jehan L. »).

La compatibilité de type et l'unicité du meilleur candidat sont vérifiées par l'appelant (`Resolver`). Les mesures
de distance viennent de RapidFuzz, déterministe.
"""

from __future__ import annotations

import re
import unicodedata

from rapidfuzz.distance import JaroWinkler

from worldkit.ingest.declaration import name_key

ABBREVIATIONS = {"st": "saint", "ste": "sainte", "sts": "saints", "stes": "saintes", "mt": "mont"}
STOPWORDS = {"de", "du", "des", "d", "la", "le", "les", "l", "et", "au", "aux", "en", "of", "the"}

# Seuils provisoires, réglés sur Valmont et Corbelle (X-007), à vérifier sur un corpus qu'ils n'ont pas vu.
LINK = 0.90    # au-dessus, et seul candidat à ce niveau : rattachée
DOUBT = 0.80   # entre les deux : doute, laissé à l'auteur
MARGIN = 0.04  # écart minimal avec le second candidat pour rattacher


def fold(text: str) -> str:
    """Forme de comparaison : sans casse, article initial, accents, ponctuation ; abréviations développées."""
    key = unicodedata.normalize("NFKD", name_key(text))
    key = "".join(c for c in key if not unicodedata.combining(c))
    key = re.sub(r"[’'\-.,;:!?()«»\"]", " ", key)
    return " ".join(ABBREVIATIONS.get(w, w) for w in key.split())


def _content(words: list[str]) -> list[str]:
    return [w for w in words if w not in STOPWORDS]


def _inclusion(a: str, b: str) -> float:
    """Les mots pleins de la forme la plus courte sont tous dans l'autre : 0,85 à 1 selon la part couverte."""
    wa, wb = _content(a.split()), _content(b.split())
    if not wa or not wb:
        return 0.0
    short, long = (wa, wb) if len(wa) <= len(wb) else (wb, wa)
    if not set(short) <= set(long):
        return 0.0
    return 0.85 + 0.15 * len(short) / len(long)


def _acronym(mention: str, name: str) -> float:
    """« GdB » : les lettres du sigle sont les initiales des mots du nom (avec ou sans les petits mots)."""
    m = mention.strip().replace(".", "")
    if " " in m or not 2 <= len(m) <= 6 or not m.isalpha() or not any(c.isupper() for c in m):
        return 0.0
    words = fold(name).split()
    every = "".join(w[0] for w in words)
    content = "".join(w[0] for w in _content(words))
    capitals = "".join(c for c in m if c.isupper()).lower()
    return 0.95 if m.lower() in (every, content) or capitals == content else 0.0


def _initial(mention: str, name: str) -> float:
    """« Jehan L. » : mêmes premiers mots, puis l'initiale du mot suivant du nom."""
    tokens = mention.replace(".", " ").split()
    if len(tokens) < 2 or len(tokens[-1]) != 1 or not tokens[-1].isalpha():
        return 0.0
    head, initial = fold(" ".join(tokens[:-1])).split(), tokens[-1].lower()
    words = fold(name).split()
    rest = _content(words[len(head):]) if words[:len(head)] == head else []
    return 0.95 if rest and rest[0].startswith(initial) else 0.0


def similarity(mention: str, name: str) -> float:
    """Score de ressemblance entre une mention et un nom connu (0 à 1)."""
    a, b = fold(mention), fold(name)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    initial = _initial(mention, name)
    ends_with_initial = re.search(r"\s[^\W\d_]\.?$", mention.strip()) is not None
    # « Jehan L. » : l'initiale finale n'est pas l'article « l' » ; l'inclusion de mots ne s'applique pas
    inclusion = 0.0 if ends_with_initial else _inclusion(a, b)
    return max(JaroWinkler.normalized_similarity(a, b), inclusion, _acronym(mention, name), initial)


def best_matches(mention: str, candidates: dict[str, list[str]]) -> list[tuple[float, str]]:
    """Candidats triés par score décroissant : (score, identifiant), un score par entité (son meilleur nom)."""
    scored = [(max(similarity(mention, n) for n in names), eid) for eid, names in candidates.items() if names]
    return sorted(scored, key=lambda s: (-s[0], s[1]))


def decide(scored: list[tuple[float, str]]) -> tuple[str | None, tuple[str, ...]]:
    """Trois issues : (identifiant, ()) rattachée ; (None, candidats) doute ; (None, ()) nouvelle."""
    if not scored or scored[0][0] < DOUBT:
        return None, ()
    first, second = scored[0], scored[1] if len(scored) > 1 else (0.0, "")
    if first[0] >= LINK and first[0] - second[0] >= MARGIN:
        return first[1], ()
    return None, tuple(eid for s, eid in scored if s >= DOUBT)
