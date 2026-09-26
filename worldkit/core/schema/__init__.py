"""M1 `schema` : méta-schéma, validateur, clés de fait, vérification (cadre technique §3, jalon J1).

Fonctions pures, déterministes, sans appel à un LLM (T-ARC-01).
"""

from .changes import Change, SheetBinding, Visibility, parse_change, parse_changes
from .check import EditCheck, StateSnapshot, apply_schema_change, check_change, check_conformity, check_edit
from .context import EntityInfo, SchemaContext, qualify
from .issues import Issue, IssueCode, Severity, has_errors
from .keys import FactKey, UnknownRelation, fact_keys, format_key
from .metaschema import AttributeDef, Cardinality, RelationDef, Schema, SchemaKind, TypeDef
from .validate import SchemaError, build_schema, check_schema, load_schema, read_yaml, validate_schema

__all__ = [
    "AttributeDef", "Cardinality", "Change", "EditCheck", "EntityInfo", "FactKey", "Issue", "IssueCode",
    "RelationDef", "Schema", "SchemaContext", "SchemaError", "SchemaKind", "Severity", "SheetBinding",
    "StateSnapshot", "TypeDef", "UnknownRelation", "Visibility", "apply_schema_change", "build_schema",
    "check_change", "check_conformity", "check_edit", "check_schema", "fact_keys", "format_key",
    "has_errors", "load_schema", "parse_change", "parse_changes", "qualify", "read_yaml", "validate_schema",
]
