"""Vues du wiki (M10) : branche + point + filtre, calculées, jamais stockées (R-VUE-01).

Notoriété effective (R-NOT-03, R-NOT-04, T-ING-15) : un fait n'est public que s'il est déclaré
public et que toutes les entités qu'il mentionne le sont ; la levée de propagation
(`propagation_lifted`) l'affiche sans révéler l'entité non publique. Le filtre public traite le
non qualifié comme secret.

Identité (R-IDT-01 à 05) : un doublon (`duplicate`) est une seule entité dans toutes les vues ;
une révélation (`revelation`) consolide les pages dans les vues où elle est visible, et laisse
les entités distinctes ailleurs.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum

from worldkit.core.projection.state import Fact, State, mentioned_entities
from worldkit.core.schema import Issue, IssueCode, Severity, Visibility
from worldkit.core.schema.changes import WORLD_SCOPE

_RANK = {Visibility.SECRET: 0, Visibility.UNQUALIFIED: 1, Visibility.PUBLIC: 2}


class Filter(StrEnum):
    AUTHOR = "author"  # tout
    PLAYER = "player"  # public seulement (R-NOT-03)


# ---------------------------------------------------------------------------
# Notoriété
# ---------------------------------------------------------------------------

def entity_visibility(state: State, entity: str) -> Visibility:
    rec = state.entities.get(entity)
    return rec.visibility if rec else Visibility.UNQUALIFIED


def effective_visibility(fact: Fact, state: State) -> Visibility:
    """Notoriété déclarée, plafonnée par celle des entités mentionnées (R-NOT-04)."""
    levels = [fact.visibility] + [entity_visibility(state, e) for e in mentioned_entities(fact, state)]
    return min(levels, key=_RANK.__getitem__)


def fact_visible(fact: Fact, state: State, flt: Filter) -> bool:
    if flt is Filter.AUTHOR:
        return True
    if effective_visibility(fact, state) is Visibility.PUBLIC:
        return True
    return fact.visibility is Visibility.PUBLIC and fact.propagation_lifted


def entity_visible(state: State, entity: str, flt: Filter) -> bool:
    return flt is Filter.AUTHOR or entity_visibility(state, entity) is Visibility.PUBLIC


def masked_public_facts(state: State) -> list[Issue]:
    """R-NOT-07 : faits déclarés publics, masqués par une entité non publique, sans levée."""
    out = []
    for f in sorted(state.facts.values(), key=lambda f: repr(f.id)):
        if f.visibility is Visibility.PUBLIC and not f.propagation_lifted \
                and effective_visibility(f, state) is not Visibility.PUBLIC:
            hidden = [e for e in mentioned_entities(f, state) if entity_visibility(state, e) is not Visibility.PUBLIC]
            out.append(Issue(IssueCode.MASKED_PUBLIC_FACT,
                             f"fait déclaré public masqué en vue publique par {', '.join(hidden)} : "
                             "qualifier l'entité ou lever la propagation", "R-NOT-07", Severity.WARNING,
                             _fact_label(f)))
    return out


def _fact_label(f: Fact) -> str:
    return f"{f.name}({f.subject}, {f.target})" if f.kind == "rel" else f"{f.subject}.{f.name}"


# ---------------------------------------------------------------------------
# Identités
# ---------------------------------------------------------------------------

def _groups(state: State, kinds: set[str], flt: Filter) -> dict[str, list[str]]:
    """Composantes connexes des liens same_as visibles des genres donnés : entité → membres triés."""
    parent: dict[str, str] = {}

    def find(x: str) -> str:
        while parent.get(x, x) != x:
            x = parent[x]
        return x

    for f in state.facts.values():
        if f.kind == "rel" and f.name == "same_as" and f.same_as_kind in kinds and f.target is not None:
            if "duplicate" in kinds or fact_visible(f, state, flt):
                a, b = find(f.subject), find(f.target)
                if a != b:
                    parent[max(a, b)] = min(a, b)
    groups: dict[str, list[str]] = {}
    for e in list(parent):
        groups.setdefault(find(e), []).append(e)
    out: dict[str, list[str]] = {}
    for root, members in groups.items():
        full = sorted(set(members) | {root})
        for m in full:
            out[m] = full
    return out


def representative(state: State, members: list[str]) -> str:
    """Le plus ancien des doublons représente le groupe (R-IDT-04)."""
    present = [m for m in members if m in state.entities] or members
    return min(present, key=lambda m: (state.entities[m].created_seq if m in state.entities else 0, m))


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class AttributeLine:
    entity: str
    name: str
    value: object
    visibility: Visibility  # effective
    provenance: str
    fact: tuple = ()        # identifiant du fait affiché
    redefined_later: bool = False  # R-VUE-03


@dataclass(frozen=True)
class RelationLine:
    direction: str          # "out" : entité → autre ; "in" : autre → entité
    relation: str
    entity: str             # membre de la page concerné
    other: str | None       # None : entité non publique (propagation levée)
    visibility: Visibility
    provenance: str
    fact: tuple = ()
    redefined_later: bool = False  # R-VUE-03


@dataclass(frozen=True)
class IdentityLine:
    other: str
    kind: str
    visibility: Visibility
    provenance: str


@dataclass(frozen=True)
class ClaimLine:
    claim: str
    text: str
    visibility: Visibility | None           # héritée du document (R-NOT-05)
    qualification: str | None               # true | false | undetermined, si visible dans la vue
    qualification_visibility: Visibility | None
    provenance: str


@dataclass(frozen=True)
class SheetSummary:
    sheet: str
    system: str
    category: str
    attributes: list[AttributeLine]


@dataclass(frozen=True)
class EntityPage:
    id: str
    members: list[str]      # entités consolidées sur la page (doublons, révélations visibles)
    type: str
    title: str
    closed: bool
    visibility: Visibility
    attributes: list[AttributeLine] = field(default_factory=list)
    relations: list[RelationLine] = field(default_factory=list)
    identities: list[IdentityLine] = field(default_factory=list)
    sheets: list[SheetSummary] = field(default_factory=list)
    claims: list[ClaimLine] = field(default_factory=list)
    drafts: list[str] = field(default_factory=list)     # pistes ouvertes : J6
    documents: list[str] = field(default_factory=list)  # documents sources (R-VUE-02)


@dataclass(frozen=True)
class View:
    state: State
    filter: Filter
    # Documents sources par entité, avec leur notoriété (R-VUE-02, R-NOT-02) : fournis par l'ingestion,
    # que le noyau ne connaît pas.
    sources: Mapping[str, list[tuple[str, Visibility]]] = field(default_factory=dict)
    # Clés réécrites par une redéfinition après le point de la vue (R-VUE-03) : fournies par le monde.
    redefined: frozenset = frozenset()

    def _redefined(self, fid: tuple) -> bool:
        return bool(self.redefined) and any(v == fid and k in self.redefined for k, v in self.state.occupancy.items())

    def _duplicates(self) -> dict[str, list[str]]:
        return _groups(self.state, {"duplicate"}, self.filter)

    def canonical(self, entity: str) -> str:
        dup = self._duplicates().get(entity)
        return representative(self.state, dup) if dup else entity

    def entity_ids(self) -> list[str]:
        """Entités du monde ayant une page dans cette vue (doublons regroupés)."""
        ids = set()
        for eid, rec in self.state.entities.items():
            if rec.scope == WORLD_SCOPE and rec.sheet is None and entity_visible(self.state, eid, self.filter):
                ids.add(self.canonical(eid))
        return sorted(ids)

    def display(self, entity: str) -> str | None:
        """Nom affiché d'une entité, ou None si elle n'est pas visible dans la vue."""
        if not entity_visible(self.state, entity, self.filter):
            return None
        return self.canonical(entity)

    def title(self, entity: str) -> str:
        fact = self.state.facts.get(("attr", entity, "name"))
        if fact is not None and fact_visible(fact, self.state, self.filter):
            return str(fact.value)
        return entity

    def page(self, entity: str) -> EntityPage | None:
        s, flt = self.state, self.filter
        if entity not in s.entities:
            return None
        entity = self.canonical(entity)
        if not entity_visible(s, entity, flt):
            return None
        members = set(self._duplicates().get(entity, [entity]))
        revealed = _groups(s, {"revelation"}, flt).get(entity, [])
        members |= {m for m in revealed if entity_visible(s, m, flt)}
        members = {m for m in members if m in s.entities}
        rec = s.entities[entity]

        attributes, relations, identities = [], [], []
        touching = {f.id: f for m in members for f in s.facts_of(m)}  # un fait entre deux membres : une fois
        for f in sorted(touching.values(), key=lambda f: repr(f.id)):
            if not fact_visible(f, s, flt):
                continue
            vis = effective_visibility(f, s) if flt is Filter.PLAYER else f.visibility
            if f.kind in ("attr", "value"):
                if f.subject in members:
                    attributes.append(AttributeLine(f.subject, f.name, f.value, vis, f.established_by, f.id,
                                                    self._redefined(f.id)))
            elif f.name == "same_as":
                ends = [f.subject, f.target or ""]
                peer = next((e for e in ends if e != entity), ends[0])
                identities.append(IdentityLine(peer, f.same_as_kind or "", vis, f.established_by))
            else:
                if f.subject in members:
                    other = f.target or ""
                    relations.append(RelationLine("out", f.name, f.subject, self.display(other), vis,
                                                  f.established_by, f.id, self._redefined(f.id)))
                if f.target in members:
                    relations.append(RelationLine("in", f.name, f.target or "", self.display(f.subject), vis,
                                                  f.established_by, f.id, self._redefined(f.id)))

        sheets = []
        for sid, srec in sorted(s.entities.items()):
            if srec.sheet is not None and srec.sheet.of in members and entity_visible(s, sid, flt):
                lines = [AttributeLine(sid, f.name, f.value, f.visibility, f.established_by, f.id)
                         for f in s.facts_of(sid) if f.kind != "rel" and fact_visible(f, s, flt)]
                sheets.append(SheetSummary(sid, srec.sheet.system, srec.sheet.category, lines))

        documents = sorted({doc for m in members for doc, vis in self.sources.get(m, [])
                            if flt is Filter.AUTHOR or vis is Visibility.PUBLIC})
        return EntityPage(entity, sorted(members), rec.type, self.title(entity), rec.closed,
                          rec.visibility, attributes, relations, identities, sheets, self.claims_of(members),
                          documents=documents)

    def claims_of(self, members: set[str]) -> list[ClaimLine]:
        """Affirmations dont l'énonciateur est sur la page (R-DOC-06, R-DOC-07, R-NOT-05)."""
        s, flt = self.state, self.filter
        out = []
        for cid, c in sorted(s.claims.items()):
            if c.get("speaker") not in members:
                continue
            vis = Visibility(c["visibility"]) if c.get("visibility") else Visibility.UNQUALIFIED
            if flt is Filter.PLAYER and vis is not Visibility.PUBLIC:
                continue
            q = s.qualifications.get(cid)
            qvis = Visibility(q["visibility"]) if q and q.get("visibility") else Visibility.UNQUALIFIED
            shown = q is not None and (flt is Filter.AUTHOR or qvis is Visibility.PUBLIC)
            out.append(ClaimLine(cid, c.get("text") or cid, vis, q["value"] if shown else None,
                                 qvis if shown else None, c["established_by"]))
        return out
