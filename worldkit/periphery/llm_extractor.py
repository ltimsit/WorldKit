"""Extracteur LLM (M7) avec résolution des mentions (M8), derrière l'adaptateur unique (T-LLM-01).

Le modèle reçoit le schéma de monde, les entités connues (identifiant, type, noms) et le passage ;
il rend une sortie **typée** (schéma JSON imposé) : changements, affirmations, attribution. Il
rattache chaque mention à une entité connue ou propose `new:étiquette`. Il ne qualifie rien :
collisions, hors schéma, supports, dépendances restent l'affaire du noyau (T-ARC-03, T-ING-17).

Version de l'extracteur = profil (adaptateur, modèle, effort) + empreinte du prompt : changer de
modèle ou de prompt invalide le cache d'extraction (T-ING-09).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from worldkit.core.schema import Schema
from worldkit.core.schema.metaschema import ScalarKind

from .extraction import Extraction, ExtractionContext
from .llm.adapters import LLMAdapter, LLMError, Profile

PROMPT_VERSION = "2"

# Champs utiles de chaque opération : les autres sont ignorés (le modèle remplit parfois `type` partout).
OP_FIELDS: dict[str, tuple[str, ...]] = {
    "create_entity": ("entity", "type"),
    "set_attribute": ("entity", "attribute", "value"),
    "unset_attribute": ("entity", "attribute"),
    "add_value": ("entity", "attribute", "value"),
    "remove_value": ("entity", "attribute", "value"),
    "add_relation": ("from", "relation", "to"),
    "remove_relation": ("from", "relation", "to"),
    "close_entity": ("entity",),
    "set_visibility": ("target",),
}

OPS = ["create_entity", "set_attribute", "unset_attribute", "add_value", "remove_value",
       "add_relation", "remove_relation", "close_entity", "set_visibility"]
_FIELDS = ["op", "entity", "type", "attribute", "value", "from", "relation", "to", "target", "visibility"]


def _nullable(t: str) -> dict[str, Any]:
    return {"anyOf": [{"type": t}, {"type": "null"}]}


CHANGE_SCHEMA: dict[str, Any] = {
    "type": "object", "additionalProperties": False, "required": _FIELDS,
    "properties": {"op": {"type": "string", "enum": OPS}, **{f: _nullable("string") for f in _FIELDS[1:]}},
}

OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object", "additionalProperties": False, "required": ["changes", "claims", "attribution"],
    "properties": {
        "changes": {"type": "array", "items": CHANGE_SCHEMA},
        "claims": {"type": "array", "items": {
            "type": "object", "additionalProperties": False, "required": ["text", "claimed"],
            "properties": {"text": {"type": "string"}, "claimed": {"anyOf": [CHANGE_SCHEMA, {"type": "null"}]}}}},
        "attribution": {"type": "boolean"},
    },
}

SYSTEM = """Tu extrais des faits structurés de notes de jeu de rôle (français) pour un wiki de monde.
Tu ne décides rien : tu rapportes ce que le passage affirme, un outil vérifie ensuite chaque changement.

Règles :
1. Un changement par fait affirmé par le passage, rien d'autre. N'invente pas, ne déduis pas au-delà du texte.
2. Utilise les identifiants du schéma (types, attributs, relations en anglais). Si le fait ne correspond à
   aucune relation ou aucun attribut déclaré, propose quand même un identifiant anglais en snake_case
   (ex. vassal_of) : l'outil le signalera comme hors schéma.
3. Entités : reprends l'identifiant d'une entité connue quand la mention la désigne, y compris par un autre
   nom, un titre ou un pronom. Pour une entité nouvelle, crée-la (create_entity avec son type, puis
   set_attribute name) sous l'identifiant « new:<étiquette-en-minuscules> », et réutilise cet identifiant.
   Un nom qui désigne une entité connue n'est PAS une entité nouvelle : c'est un autre nom (add_value aliases).
   Ne crée pas d'entité pour un lieu générique (« les collines », « la vallée »).
4. Attributs à valeurs multiples (list[...]) : add_value, une valeur par changement. Attribut simple : set_attribute.
   Relation : add_relation avec from, relation, to.
5. Un fait passé révolu (« régnait autrefois ») ne décrit pas l'état actuel : n'en fais pas un fait actuel.
6. Indice de notoriété (« en secret », « nul ne sait ») : ajoute un changement set_visibility distinct, avec
   target (« a relation b » pour une relation, « entité.attribut » pour un attribut) et visibility = secret.
7. Paroles rapportées entre guillemets ou rumeurs (« murmure-t-on ») : attribution = true, aucun fait.
8. Si l'énonciation est « in_world », le passage est la voix d'un document du monde : ne produis AUCUN
   changement ; mets chaque affirmation dans claims (text : l'affirmation reformulée brièvement ;
   claimed : le changement revendiqué s'il est exprimable avec le schéma, sinon null).
9. Valeurs : reprends les mots du texte, en français, sous leur forme la plus courte (« régent », pas
   « régent de Brume » ; « capitale », pas « capital » ; « taverne » pour une taverne). Ne traduis jamais une valeur.
10. N'extrais que les faits du monde : pas d'entité pour un nom commun incident (un serment, une séance,
   une halle) ; pas de relation qui n'est pas dite (« depuis la Chute » ne dit pas que quelqu'un y a participé).
11. Les champs inutilisés d'un changement valent null. value est toujours une chaîne.
"""


def describe_schema(schema: Schema) -> str:
    lines = ["Types d'entités (attributs) :"]
    for name, t in sorted(schema.types.items()):
        attrs = ", ".join(f"{a} ({d.type}{', requis' if d.required else ''})"
                          for a, d in sorted(schema.attributes_of(name).items()))
        parent = f" [sous-type de {t.extends}]" if t.extends else ""
        lines.append(f"- {name}{parent} : {attrs}")
    lines.append("Relations (from → to, cardinalité) :")
    for name, r in sorted(schema.relations.items()):
        sym = ", symétrique" if r.symmetric else ""
        lines.append(f"- {name} : {'|'.join(r.from_)} → {'|'.join(r.to)} ({r.cardinality}{sym})")
    return "\n".join(lines)


@dataclass
class LLMExtractor:
    adapter: LLMAdapter
    profile: Profile
    retries: int = 1

    @property
    def concurrency(self) -> int:
        """Appels simultanés (option `concurrency` du profil, 4 par défaut)."""
        return int(self.profile.options.get("concurrency", 4))

    @property
    def version(self) -> str:
        digest = hashlib.sha256((SYSTEM + json.dumps(OUTPUT_SCHEMA, sort_keys=True)).encode()).hexdigest()[:8]
        return f"llm-{PROMPT_VERSION}:{self.profile.signature}:{digest}"

    def prompt(self, passage_text: str, context: ExtractionContext) -> tuple[str, str]:
        system = SYSTEM + "\n" + describe_schema(context.schema)  # stable pour un monde : cacheable
        known = "\n".join(f"- {e.id} ({e.type}) : {' / '.join(e.names)}" for e in context.entities) or "- (aucune)"
        voice = f"in_world (énonciateur : {context.speaker})" if context.voice == "in_world" else "author"
        user = (f"Entités connues (identifiant, type : noms) :\n{known}\n\n"
                f"Énonciation : {voice}\n\nPassage :\n{passage_text}")
        return system, user

    def extract(self, doc_id: str, passage_text: str, context: ExtractionContext | None = None) -> Extraction:
        if context is None:
            raise LLMError("l'extracteur LLM a besoin du contexte (schéma, entités connues)")
        system, user = self.prompt(passage_text, context)
        last: Exception | None = None
        for _ in range(self.retries + 1):
            try:
                raw = self.adapter.complete(system, user, OUTPUT_SCHEMA)
                return to_extraction(raw, context.schema, context)
            except (LLMError, KeyError, TypeError, ValueError) as e:  # T-ING-17 : relancée, jamais proposée
                last = e
        raise LLMError(f"extraction impossible après {self.retries + 1} essai(s) : {last}")


def _coerce(value: str | None, attribute: str | None, entity_type: str | None, schema: Schema) -> Any:
    """La sortie donne des chaînes ; l'attribut déclaré dit s'il faut un entier ou un booléen."""
    if value is None or attribute is None or entity_type is None or entity_type not in schema.types:
        return value
    attr = schema.attributes_of(entity_type).get(attribute)
    if attr is None:
        return value
    if attr.type.kind is ScalarKind.INTEGER:
        try:
            return int(value)
        except ValueError:
            return value
    if attr.type.kind is ScalarKind.BOOLEAN:
        return value.strip().lower() in ("true", "vrai", "oui", "yes")
    return value


def to_draft(change: dict[str, Any], schema: Schema, types: dict[str, str]) -> dict[str, Any]:
    op = change["op"]
    out: dict[str, Any] = {"op": op}
    if op in ("add_relation", "remove_relation") and change.get("from") is None and change.get("entity"):
        change = {**change, "from": change["entity"]}  # sujet mis dans `entity` par le modèle
    for f in OP_FIELDS.get(op, ()):
        if f != "value" and change.get(f) is not None:
            out[f] = change[f]
    if op == "set_visibility":
        out["value"] = change.get("visibility") or "secret"
    elif "value" in OP_FIELDS.get(op, ()) and change.get("value") is not None:
        out["value"] = _coerce(change["value"], change.get("attribute"), types.get(change.get("entity", "")), schema)
    return out


def to_extraction(raw: dict[str, Any], schema: Schema, context: ExtractionContext) -> Extraction:
    types = {e.id: e.type for e in context.entities}
    types.update({c["entity"]: c["type"] for c in raw["changes"] if c["op"] == "create_entity" and c.get("entity")})
    drafts = tuple(to_draft(c, schema, types) for c in raw["changes"])
    claims = tuple({"text": c["text"], "claimed": to_draft(c["claimed"], schema, types) if c.get("claimed") else None,
                    "speaker": None} for c in raw["claims"])
    return Extraction(drafts, frozenset(), claims, ("attribution",) if raw["attribution"] else ())
