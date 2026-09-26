"""Validateur unique des schémas de monde et des systèmes de règles (R-SCH-02, T-SCH-01).

Deux passes : la forme (modèles pydantic du méta-schéma), puis les contrôles
croisés (références déclarées, types noyau, héritage, symétrie, identifiants).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from .core_elements import CORE_RELATIONS, CORE_TYPES
from .issues import Issue, IssueCode, Severity, has_errors
from .metaschema import Cardinality, Schema, SchemaKind, ScalarKind


class SchemaError(ValueError):
    """Schéma rejeté ; porte la liste des signalements."""

    def __init__(self, issues: list[Issue], source: str = "") -> None:
        self.issues = issues
        head = f"schéma rejeté{f' ({source})' if source else ''}"
        super().__init__(head + "\n" + "\n".join(f"  {i}" for i in issues))


# R-SCH-07 — heuristique retenue : ASCII et casse conventionnelle, sans dictionnaire.
_TYPE_IDENT = re.compile(r"[A-Z][A-Za-z0-9]*")
_MEMBER_IDENT = re.compile(r"[a-z][a-z0-9]*(?:_[a-z0-9]+)*")


def validate_schema(doc: Any) -> list[Issue]:
    """Rend les signalements d'un schéma (vide si le schéma est valide)."""
    return _parse(doc)[1]


def build_schema(doc: Any, source: str = "") -> Schema:
    schema, issues = _parse(doc)
    if schema is None or has_errors(issues):
        raise SchemaError(issues, source)
    return schema


def load_schema(path: str | Path) -> Schema:
    path = Path(path)
    return build_schema(read_yaml(path), source=str(path))


def read_yaml(path: str | Path) -> Any:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


# --- Première passe : la forme ---

def _parse(doc: Any) -> tuple[Schema | None, list[Issue]]:
    if not isinstance(doc, dict):
        return None, [Issue(IssueCode.MALFORMED_SCHEMA, "un schéma est un dictionnaire YAML", "T-SCH-01")]
    try:
        schema = Schema.model_validate(doc)
    except ValidationError as e:
        return None, [_from_pydantic(err) for err in e.errors()]
    return schema, check_schema(schema)


def _from_pydantic(err: Any) -> Issue:
    loc = tuple(str(p) for p in err["loc"])
    # Une cardinalité inconnue relève de R-SCH-01 ; le reste de la forme, de T-SCH-01.
    rule = "R-SCH-01" if "cardinality" in loc else "T-SCH-01"
    kind = err["type"]
    if kind == "value_error":
        msg = str(err["ctx"]["error"])
    elif kind == "enum":
        expected = str(err["ctx"]["expected"]).replace(" or ", ", ")
        msg = f"valeur « {err['input']} » inconnue ; attendu : {expected}"
    elif kind == "extra_forbidden":
        msg = "clé inconnue du méta-schéma"
    elif kind == "missing":
        msg = "champ requis manquant"
    else:
        msg = f"forme invalide ({err['msg']})"
    return Issue(IssueCode.MALFORMED_SCHEMA, msg, rule, path=".".join(loc))


# --- Seconde passe : contrôles croisés ---

def check_schema(s: Schema) -> list[Issue]:
    issues: list[Issue] = []

    def add(code: IssueCode, msg: str, rule: str, path: str) -> None:
        issues.append(Issue(code, msg, rule, path=path))

    for name in s.types:
        if name in CORE_TYPES:
            add(IssueCode.CORE_TYPE_DECLARED,
                f"« {name} » est un type noyau de la plateforme ; un schéma ne déclare que des types diégétiques",
                "R-NOY-01", f"types.{name}")
    for name in s.relations:
        if name in CORE_RELATIONS:
            add(IssueCode.CORE_TYPE_DECLARED,
                f"« {name} » est une relation noyau de la plateforme ; elle ne peut pas être redéclarée",
                "R-NOY-01", f"relations.{name}")

    # Héritage : parent déclaré, pas de cycle, pas de redéfinition d'un attribut hérité.
    acyclic = True
    for name, t in s.types.items():
        if t.extends is not None and t.extends not in s.types:
            add(IssueCode.UNDECLARED_REFERENCE,
                f"le type parent « {t.extends} » n'est pas déclaré", "R-SCH-01", f"types.{name}.extends")
    for name in s.types:
        seen: list[str] = []
        current: str | None = name
        while current is not None and current in s.types:
            if current in seen:
                acyclic = False
                add(IssueCode.INHERITANCE_CYCLE,
                    f"cycle d'héritage : {' → '.join(seen + [current])}", "R-SCH-01", f"types.{name}.extends")
                break
            seen.append(current)
            current = s.types[current].extends
    if acyclic:
        for name, t in s.types.items():
            inherited = s.attributes_of(t.extends) if t.extends else {}
            for attr in t.attributes:
                if attr in inherited:
                    add(IssueCode.INHERITED_ATTRIBUTE_REDEFINED,
                        f"l'attribut « {attr} » est déjà hérité de « {t.extends} »",
                        "T-SCH-01", f"types.{name}.attributes.{attr}")

    for name, t in s.types.items():
        for attr, a in t.attributes.items():
            if a.type.kind is ScalarKind.REF and a.type.ref_target not in s.types:
                add(IssueCode.UNDECLARED_REFERENCE,
                    f"l'attribut référence le type « {a.type.ref_target} », non déclaré",
                    "R-SCH-01", f"types.{name}.attributes.{attr}.type")

    for name, r in s.relations.items():
        for end, targets in (("from", r.from_), ("to", r.to)):
            for t in targets:
                if t not in s.types:
                    add(IssueCode.UNDECLARED_REFERENCE,
                        f"la relation cite le type « {t} », non déclaré", "R-SCH-01", f"relations.{name}.{end}")
        if r.symmetric and set(r.from_) != set(r.to):
            add(IssueCode.ASYMMETRIC_SYMMETRIC_RELATION,
                "une relation symétrique doit avoir les mêmes types en from et en to",
                "R-SCH-01", f"relations.{name}")
        if r.symmetric and r.cardinality in (Cardinality.ONE_TO_MANY, Cardinality.MANY_TO_ONE):
            add(IssueCode.ASYMMETRIC_SYMMETRIC_RELATION,
                f"une relation symétrique ne peut pas être {r.cardinality} : "
                "attendu one_to_one ou many_to_many", "R-SCH-01", f"relations.{name}.cardinality")

    if s.kind is SchemaKind.WORLD:
        issues.extend(_identifier_checks(s))
    return issues


def _identifier_checks(s: Schema) -> list[Issue]:
    """R-SCH-07 : identifiants de monde en anglais, vérifiés par une heuristique de forme."""
    out: list[Issue] = []

    def bad(ident: str, expected: str, path: str) -> None:
        out.append(Issue(
            IssueCode.NON_ENGLISH_IDENTIFIER,
            f"identifiant « {ident} » : attendu {expected} en ASCII (identifiants en anglais, libellés via labels)",
            "R-SCH-07", path=path,
        ))

    for name, t in s.types.items():
        if not _TYPE_IDENT.fullmatch(name):
            bad(name, "PascalCase", f"types.{name}")
        for attr in t.attributes:
            if not _MEMBER_IDENT.fullmatch(attr):
                bad(attr, "snake_case", f"types.{name}.attributes.{attr}")
    for name in s.relations:
        if not _MEMBER_IDENT.fullmatch(name):
            bad(name, "snake_case", f"relations.{name}")
    return out


__all__ = ["SchemaError", "build_schema", "check_schema", "load_schema", "read_yaml", "validate_schema", "Severity"]
