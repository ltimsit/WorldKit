"""Forme canonique d'un état (JSON trié) : tête matérialisée (T-STO-01) et tests de déterminisme (T-ARC-01).

Deux états égaux ont exactement la même forme canonique.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any

from worldkit.core.schema import Schema, SheetBinding, Visibility

from .state import EntityRecord, Fact, State

# À incrémenter à chaque changement de forme : une tête en cache d'un autre format est ignorée
# et l'état est rejoué depuis le journal, qui seul fait foi (T-STO-01).
STATE_FORMAT = 3


class StaleFormat(ValueError):
    pass


def _tuplify(x: Any) -> Any:
    return tuple(_tuplify(i) for i in x) if isinstance(x, list) else x


def state_to_dict(state: State) -> dict[str, Any]:
    entities = []
    for e in sorted(state.entities.values(), key=lambda e: e.id):
        d = asdict(e)
        d["sheet"] = e.sheet.model_dump() if e.sheet else None
        entities.append(d)
    facts = []
    for f in sorted(state.facts.values(), key=lambda f: repr(f.id)):
        d = asdict(f)
        d["id"] = list(f.id)
        facts.append(d)
    return {
        "format": STATE_FORMAT,
        "branch": state.branch, "seq": state.seq, "schema_rev": state.schema_rev,
        "world": state.world.model_dump(mode="json", by_alias=True),
        "systems": {k: v.model_dump(mode="json", by_alias=True) for k, v in sorted(state.systems.items())},
        "sheet_requirements": {k: dict(sorted(v.items())) for k, v in sorted(state.sheet_requirements.items())},
        "entities": entities,
        "facts": facts,
        "occupancy": sorted(([list(k), list(v)] for k, v in state.occupancy.items()), key=repr),
        "claims": dict(sorted(state.claims.items())),
        "qualifications": dict(sorted(state.qualifications.items())),
        "obsolete_documents": dict(sorted(state.obsolete_documents.items())),
    }


def state_to_json(state: State) -> str:
    return json.dumps(state_to_dict(state), ensure_ascii=False, sort_keys=True, default=str)


def state_from_json(text: str) -> State:
    d = json.loads(text)
    if d.get("format") != STATE_FORMAT:
        raise StaleFormat(f"format d'état {d.get('format')} ≠ {STATE_FORMAT}")
    entities = {}
    for e in d["entities"]:
        sheet = SheetBinding.model_validate(e["sheet"]) if e["sheet"] else None
        entities[e["id"]] = EntityRecord(e["id"], e["type"], e["scope"], sheet, Visibility(e["visibility"]),
                                         e["closed"], e["established_by"], e["created_seq"])
    facts = {}
    for f in d["facts"]:
        fid = _tuplify(f["id"])
        facts[fid] = Fact(**{**f, "id": fid, "visibility": Visibility(f["visibility"])})
    return State(
        branch=d["branch"], seq=d["seq"], schema_rev=d["schema_rev"],
        world=Schema.model_validate(d["world"]),
        systems={k: Schema.model_validate(v) for k, v in d["systems"].items()},
        sheet_requirements=d["sheet_requirements"],
        entities=entities, facts=facts,
        occupancy={_tuplify(k): _tuplify(v) for k, v in d["occupancy"]},
        claims=d["claims"], qualifications=d["qualifications"], obsolete_documents=d["obsolete_documents"],
    )
