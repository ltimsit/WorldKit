"""Couche « descriptions » (J9 ; R-NTE-01 à R-NTE-05 ; chantier §10.6, choix 43 à 48) : ce que le texte dit des
entités sans que ce soit un fait — un portrait, un jugement, une habitude, une ambiance.

Une question au modèle sur la fenêtre (chantier §6.5), à entités confirmées, avec les facettes de leurs types et les
faits déjà gardés (à ne pas répéter : notes et faits complémentaires, R-NTE-05). Puis des contrôles sans modèle :

- la citation (`text`) est recopiée du texte, sinon la bribe est écartée (provenance vérifiable, jamais inventée) ;
- sujets et mentions sont des entités confirmées ; une mention qui est aussi un sujet reste un sujet ;
- la facette est commune aux types des sujets, sinon `other` (R-NTE-04) ;
- une rumeur ou une note de travail ne donne pas de note (énonciation sans modèle, X-010) ;
- une bribe qui ne fait que répéter la valeur d'un fait gardé (« apothicaire » pour le titre) est écartée ;
- deux bribes identiques (mêmes sujets, même facette, même texte plié) n'en font qu'une.

La périphérie ne fait que proposer (T-ARC-03) : l'auteur garde, corrige ou retire dans l'atelier.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .facts import Confirmed, _locate, enunciation
from .mentions import Window

NOTES_PROMPT_VERSION = 1

# Exemples volontairement pris hors des corpus (X-003) : on ne règle pas le prompt sur Valmont ni sur Corbelle.
SYSTEM = """Tu relèves, dans des notes de jeu de rôle (français), ce que le texte dit des entités données sans que ce soit
un fait déjà connu : leur apparence, leur caractère, leurs habitudes, leur histoire, une ambiance.

Règles :
1. text : un extrait du texte qui décrit l'entité, recopié exactement (de quelques mots à une phrase). N'invente
   rien, ne résume pas, ne reformule pas.
2. subjects : les identifiants des entités que l'extrait décrit (une ou plusieurs, à égalité : « le forgeron et
   sa fille se querellent sans cesse » décrit les deux). mentions : celles qu'il nomme sans les décrire.
3. facet : une des facettes données pour le type des sujets ; « other » si aucune ne convient.
4. short : les caractéristiques que l'extrait donne, en formes courtes « aspect : valeur » (« un forgeron bourru
   aux bras couverts de suie » : caractère : bourru · bras : couverts de suie) ; rien s'il n'y en a pas.
5. Ne relève pas ce que disent déjà les faits donnés, ni une rumeur (« on dit que »), ni une note de travail de
   l'auteur (« TODO », « idée : »).
"""


def output_schema() -> dict[str, Any]:
    short = {"type": "object", "additionalProperties": False, "required": ["aspect", "value"],
             "properties": {"aspect": {"type": "string"}, "value": {"type": "string"}}}
    note = {"type": "object", "additionalProperties": False,
            "required": ["subjects", "mentions", "facet", "text", "short"],
            "properties": {"subjects": {"type": "array", "items": {"type": "string"}},
                           "mentions": {"type": "array", "items": {"type": "string"}},
                           "facet": {"type": "string"}, "text": {"type": "string"},
                           "short": {"type": "array", "items": short}}}
    return {"type": "object", "additionalProperties": False, "required": ["notes"],
            "properties": {"notes": {"type": "array", "items": note}}}


@dataclass
class NoteDraft:
    """Une bribe proposée : le brouillon `add_note` (sans identifiant ni source : l'ingestion les pose) et son
    passage."""

    draft: dict[str, Any]
    passage: int | None


def common_facets(schema: Any, types: list[str]) -> list[str]:
    """Facettes communes aux types des sujets ; `other` toujours (R-NTE-04)."""
    sets = [list(schema.facets_of(t)) if t in schema.types else ["other"] for t in types]
    if not sets:
        return ["other"]
    common = [f for f in sets[0] if all(f in s for s in sets[1:])]
    return common or ["other"]


def check_notes(raw: list[dict[str, Any]], window: Window, entities: list[Confirmed], schema: Any,
                kept_values: dict[str, set[str]], rejected: list[tuple[dict[str, Any], str]]) -> list[NoteDraft]:
    """Contrôles sans modèle (voir le module) ; les bribes écartées vont dans `rejected`, avec la raison."""
    from .matching import fold
    types = {e.id: e.type for e in entities}
    out: list[NoteDraft] = []
    seen: set[tuple[Any, ...]] = set()
    for n in raw:
        text = str(n.get("text", "")).strip()
        passage = _locate(window, text) if text else None
        if passage is None:
            rejected.append((n, "citation introuvable dans le texte"))
            continue
        voice = enunciation(window.passage_texts.get(passage, ""))
        if voice is not None:
            rejected.append((n, "rumeur ou paroles rapportées" if voice == "attribution" else "note de travail"))
            continue
        subjects = sorted({s.strip() for s in n.get("subjects", []) if s.strip() in types})
        if not subjects:
            rejected.append((n, "aucun sujet parmi les entités confirmées"))
            continue
        mentions = sorted({m.strip() for m in n.get("mentions", []) if m.strip() in types} - set(subjects))
        if any(fold(text) in kept_values.get(s, set()) for s in subjects):
            rejected.append((n, "déjà dit par un fait gardé"))
            continue
        facets = common_facets(schema, [types[s] for s in subjects])
        facet = n.get("facet") if n.get("facet") in facets else "other"
        key = (tuple(subjects), facet, fold(text))
        if key in seen:
            continue
        seen.add(key)
        short = [{"aspect": str(x["aspect"]).strip(), "value": str(x["value"]).strip()}
                 for x in n.get("short", []) if str(x.get("aspect", "")).strip() and str(x.get("value", "")).strip()]
        draft = {"op": "add_note", "subjects": subjects, "facet": facet, "text": text,
                 **({"mentions": mentions} if mentions else {}), **({"short": short} if short else {})}
        out.append(NoteDraft(draft, passage))
    return out


@dataclass
class NoteFinder:
    """La couche « descriptions » : une question au modèle sur la fenêtre."""

    adapter: Any
    profile: Any
    rejected: list[tuple[dict[str, Any], str]] = field(default_factory=list)

    @property
    def version(self) -> str:
        return f"notes-{NOTES_PROMPT_VERSION}:{self.profile.signature}"

    @property
    def meter(self) -> Any:
        return getattr(self.adapter, "meter", None)

    def prompt(self, window: Window, entities: list[Confirmed], schema: Any, known: list[str]) -> tuple[str, str]:
        lines = []
        for e in sorted(entities, key=lambda e: e.id):
            facets = schema.facets_of(e.type) if e.type in schema.types else {"other": None}
            labels = ", ".join(f"{f} ({(d.labels or {}).get('fr', f)})" if d is not None else f
                               for f, d in facets.items())
            lines.append(f"- {e.id} ({e.type}) : {e.name} — facettes : {labels}")
        user = ("Entités (identifiant, type : nom — facettes) :\n" + "\n".join(lines)
                + "\n\nFaits déjà connus (ne pas les répéter) :\n" + ("\n".join(f"- {k}" for k in known) or "- (aucun)")
                + "\n\nTexte :\n" + window.text)
        return SYSTEM, user

    def find(self, window: Window, entities: list[Confirmed], schema: Any, known: list[str] | None = None,
             kept_values: dict[str, set[str]] | None = None) -> list[NoteDraft]:
        system, user = self.prompt(window, entities, schema, known or [])
        raw = self.adapter.complete(system, user, output_schema())
        return check_notes(raw.get("notes", []), window, entities, schema, kept_values or {}, self.rejected)
