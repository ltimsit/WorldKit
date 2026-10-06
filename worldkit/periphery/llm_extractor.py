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

PROMPT_VERSION = "3"

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

# Formes réduites du méta (décision J8), traduites de façon déterministe : `sheet_values` (valeurs d'une
# entité dans un système) et `schema_constraint` (bornes d'un attribut d'une catégorie de système).
OPS = ["create_entity", "set_attribute", "unset_attribute", "add_value", "remove_value",
       "add_relation", "remove_relation", "close_entity", "set_visibility", "sheet_values", "schema_constraint"]
_FIELDS = ["op", "entity", "type", "attribute", "value", "from", "relation", "to", "target", "visibility",
           "system", "min", "max"]
_PAIR = {"type": "object", "additionalProperties": False, "required": ["attribute", "value"],
         "properties": {"attribute": {"type": "string"}, "value": {"type": "string"}}}


def _nullable(t: str) -> dict[str, Any]:
    return {"anyOf": [{"type": t}, {"type": "null"}]}


CHANGE_SCHEMA: dict[str, Any] = {
    "type": "object", "additionalProperties": False, "required": [*_FIELDS, "values"],
    "properties": {"op": {"type": "string", "enum": OPS}, **{f: _nullable("string") for f in _FIELDS[1:]},
                   "values": {"anyOf": [{"type": "array", "items": _PAIR}, {"type": "null"}]}},
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
12. Méta : une information de règles de jeu (PV, niveau, caractéristiques, capacités d'un système) n'est PAS
   un fait du monde ; n'écris jamais une valeur de système dans un attribut du monde.
   - Valeurs d'une entité dans un système : op = sheet_values, entity = identifiant de l'entité du monde,
     system = identifiant du système, values = paires {attribute, value} avec les attributs du système
     (une paire par valeur d'un attribut à valeurs multiples ; une capacité connue par son identifiant).
   - Règle générale d'un système (« toute créature a entre 1 et 10 PV ») : op = schema_constraint, system,
     type = catégorie du système, attribute, min, max.
13. Un passage qui ne nomme pas son sujet parle du sujet du document (son titre est donné).
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
    def meter(self) -> Any:
        """Compteur d'usage de l'adaptateur (None si l'adaptateur n'en a pas)."""
        return getattr(self.adapter, "meter", None)

    @property
    def version(self) -> str:
        digest = hashlib.sha256((SYSTEM + json.dumps(OUTPUT_SCHEMA, sort_keys=True)).encode()).hexdigest()[:8]
        return f"llm-{PROMPT_VERSION}:{self.profile.signature}:{digest}"

    def prompt(self, passage_text: str, context: ExtractionContext) -> tuple[str, str]:
        system = SYSTEM + "\n" + describe_schema(context.schema)  # stable pour un monde : cacheable
        for sid, schema in sorted(context.systems.items()):
            system += f"\n\nSystème de règles « {sid} » — catégories :\n" + describe_schema(schema)
        known = "\n".join(f"- {e.id} ({e.type}) : {' / '.join(e.names)}" for e in context.entities) or "- (aucune)"
        voice = f"in_world (énonciateur : {context.speaker})" if context.voice == "in_world" else "author"
        document = f"Document : {context.document}\n\n" if context.document else ""
        user = (f"Entités connues (identifiant, type : noms) :\n{known}\n\n"
                f"{document}Énonciation : {voice}\n\nPassage :\n{passage_text}")
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
    return _coerce_def(value, schema.attributes_of(entity_type).get(attribute))


def _system_attribute(system: Schema | None, attribute: str) -> Any:
    for name in sorted(system.types) if system is not None else ():
        a = system.attributes_of(name).get(attribute)
        if a is not None:
            return a
    return None


def _coerce_def(value: str, attr: Any) -> Any:
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


def _int(v: str | None) -> int | None:
    try:
        return int(v) if v is not None else None
    except ValueError:
        return None


def meta_draft(change: dict[str, Any], systems: dict[str, Schema]) -> dict[str, Any]:
    """Formes réduites du méta → brouillons (décision J8). `sheet_values` reste réduit : M9 le traduit
    contre l'état (catégorie, identifiant, fiche existante)."""
    system = change.get("system")
    schema = systems.get(system or "")
    if change["op"] == "schema_constraint":
        bounds = {k: _int(change.get(k)) for k in ("min", "max")}
        return {"op": "schema_set_type", "scope": system, "type": change.get("type"),
                "attribute": change.get("attribute"), "constraint": {k: v for k, v in bounds.items() if v is not None}}
    values: dict[str, Any] = {}
    for pair in change.get("values") or []:
        attr = _system_attribute(schema, pair["attribute"])
        v = _coerce_def(pair["value"], attr)
        if attr is None and _int(v) is not None:
            v = _int(v)  # attribut hors système (« Constitution 13 ») : une valeur de fiche chiffrée reste un entier
        if attr is not None and attr.type.is_list:
            values.setdefault(pair["attribute"], []).append(v)
        else:
            values[pair["attribute"]] = v
    return {"op": "sheet_values", "of": change.get("entity"), "system": system, "values": values}


def to_draft(change: dict[str, Any], schema: Schema, types: dict[str, str],
             systems: dict[str, Schema] | None = None) -> dict[str, Any]:
    op = change["op"]
    if op in ("sheet_values", "schema_constraint"):
        return meta_draft(change, systems or {})
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
    drafts = tuple(to_draft(c, schema, types, context.systems) for c in raw["changes"])
    claims = tuple({"text": c["text"], "claimed": to_draft(c["claimed"], schema, types) if c.get("claimed") else None,
                    "speaker": None} for c in raw["claims"])
    return Extraction(drafts, frozenset(), claims, ("attribution",) if raw["attribution"] else ())
