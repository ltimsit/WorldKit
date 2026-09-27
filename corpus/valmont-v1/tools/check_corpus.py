#!/usr/bin/env python3
"""Vérification de cohérence du corpus synthétique Valmont v1.

Ce n'est PAS le noyau : c'est un contrôle du corpus lui-même, pour s'assurer que
la vérité structurée, les schémas et les annotations gold sont cohérents entre eux.

Contrôles :
  1. Tous les fichiers YAML se chargent.
  2. Les éditions de base n'utilisent que des types, attributs et relations déclarés
     (sauf les exceptions documentées : counterpart_of, relations noyau).
  3. Les entités citées existent au moment où elles sont citées.
  4. Les attributs list[...] ne sont modifiés que par add_value / remove_value.
  5. Aucune collision de clé de fait dans l'état de base (R-FAI-05).
  6. Gold : chaque outcome « support » correspond à un fait de l'état de base (ou d'une
     édition antérieure du parcours), chaque « out_of_schema » est réellement hors schéma,
     chaque « anomaly » entre réellement en collision avec l'état.
  7. Les passages annotés existent dans les documents (starts_with).
"""
import pathlib, re, sys
import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent
V = ROOT / "valmont"
CORE_RELATIONS = {"same_as", "concerns", "asserts", "has_sheet", "conforms_to", "counterpart_of"}
errors, notes = [], []

def err(msg): errors.append(msg)

# ---------- 1. chargement ----------
def load(p):
    try:
        return yaml.safe_load(p.read_text(encoding="utf-8"))
    except Exception as e:
        err(f"YAML invalide : {p.relative_to(ROOT)} : {e}")
        return None

all_yaml = {p: load(p) for p in ROOT.rglob("*.yaml")}

# ---------- schémas ----------
def schema_index(doc):
    types = {}
    for name, t in (doc.get("types") or {}).items():
        types[name] = t
    def attrs(tname):
        out = {}
        t = types.get(tname)
        while t is not None:
            for a, d in (t.get("attributes") or {}).items():
                out.setdefault(a, d)
            t = types.get(t.get("extends")) if t.get("extends") else None
        return out
    def ancestors(tname):
        seen = []
        while tname:
            seen.append(tname)
            tname = (types.get(tname) or {}).get("extends")
        return seen
    return {"types": types, "attrs": attrs, "ancestors": ancestors,
            "relations": doc.get("relations") or {}}

world = schema_index(all_yaml[V / "schema.yaml"])
systems = {
    "system-a": schema_index(all_yaml[V / "systems/system-a.yaml"]),
    "system-b": schema_index(all_yaml[V / "systems/system-b.yaml"]),
}

def as_list(x):
    return x if isinstance(x, list) else [x]

# ---------- état simulé ----------
entities = {}    # id -> (scope, type, sheet_system)
facts = {}       # key -> value
def fact_key(ch, scope_schema):
    op = ch["op"]
    if op in ("set_attribute", "unset_attribute"):
        return ("attr", ch["entity"], ch["attribute"])
    if op in ("add_value", "remove_value"):
        return ("attr", ch["entity"], ch["attribute"], ch["value"])
    if op in ("add_relation", "remove_relation"):
        rel = ch["relation"]
        d = scope_schema["relations"].get(rel, {})
        card = d.get("cardinality", "many_to_many")
        a, b = ch["from"], ch["to"]
        if d.get("symmetric"):
            a, b = sorted([a, b])
        if card == "one_to_many":
            return ("rel", rel, "to", b)
        if card == "many_to_one":
            return ("rel", a, rel, "from")
        if card == "one_to_one":
            return ("rel", rel, "to", b)   # simplification : la clé côté cible suffit ici
        return ("rel", a, rel, b)
    return None

def schema_for(entity_id):
    if entity_id in entities:
        scope, etype, sheet_sys = entities[entity_id]
        if sheet_sys:
            return systems[sheet_sys], entities[entity_id]
        if scope != "world":
            return systems[scope], entities[entity_id]
    return world, entities.get(entity_id)

def check_change(ch, where, apply=True):
    op = ch["op"]
    scope = ch.get("scope", "world")
    if op == "create_entity":
        eid, etype = ch["entity"], ch["type"]
        if etype == "Sheet":
            sh = ch["sheet"]
            if sh["of"] not in entities: err(f"{where} : fiche d'une entité inconnue {sh['of']}")
            if sh["category"] not in systems[sh["system"]]["types"]:
                err(f"{where} : catégorie {sh['category']} absente de {sh['system']}")
            if apply: entities[eid] = ("world", sh["category"], sh["system"])
        else:
            sch = world if scope == "world" else systems[scope]
            if etype not in sch["types"]: err(f"{where} : type {etype} non déclaré ({scope})")
            if apply: entities[eid] = (scope, etype, None)
        return
    if op in ("close_entity", "delete_entity"):
        if ch["entity"] not in entities: err(f"{where} : {op} sur entité inconnue {ch['entity']}")
        return
    if op in ("set_attribute", "unset_attribute", "add_value", "remove_value"):
        eid = ch["entity"]
        if eid not in entities:
            err(f"{where} : entité inconnue {eid}"); return
        sch, (esc, etype, _) = schema_for(eid)
        attrs = sch["attrs"](etype)
        a = ch["attribute"]
        if a not in attrs:
            err(f"{where} : attribut {etype}.{a} non déclaré"); return
        is_list = str(attrs[a]["type"]).startswith("list[")
        if is_list and op in ("set_attribute", "unset_attribute"):
            err(f"{where} : {op} interdit sur l'attribut multiple {a}")
        if not is_list and op in ("add_value", "remove_value"):
            err(f"{where} : {op} sur un attribut simple {a}")
        if op == "set_attribute" and attrs[a]["type"] == "integer":
            v = ch["value"]; mn = attrs[a].get("min"); mx = attrs[a].get("max")
            if (mn is not None and v < mn) or (mx is not None and v > mx):
                notes.append(f"{where} : {eid}.{a}={v} hors bornes (non-conformité attendue ?)")
        k = fact_key(ch, sch)
        if apply and op in ("set_attribute", "add_value"):
            if op == "set_attribute" and k in facts and facts[k] != ch["value"]:
                err(f"{where} : collision {k} ({facts[k]} / {ch['value']})")
            facts[k] = ch["value"]
        return
    if op in ("add_relation", "remove_relation"):
        rel = ch["relation"]
        for end in ("from", "to"):
            ref = ch[end]
            if ":" in str(ref):   # référence vers un élément de système
                continue
            if ref not in entities: err(f"{where} : {end} inconnu {ref}")
        if rel in CORE_RELATIONS:
            return
        d = world["relations"].get(rel)
        if d is None:
            err(f"{where} : relation {rel} non déclarée"); return
        for end in ("from", "to"):
            etype = entities.get(ch[end], (None, None, None))[1]
            allowed = as_list(d[end])
            if etype and not set(world["ancestors"](etype)) & set(allowed):
                err(f"{where} : {rel}.{end} n'accepte pas {etype}")
        k = fact_key(ch, world)
        if apply and op == "add_relation":
            val = (ch["from"], ch["to"])
            if k in facts and facts[k] != val:
                err(f"{where} : collision {k} ({facts[k]} / {val})")
            facts[k] = val
        return
    if op.startswith("schema_") or op in ("set_visibility", "qualify_claim", "add_claim", "set_document_obsolete"):
        return
    err(f"{where} : opération inconnue {op}")

# ---------- 2-5. éditions de base ----------
base = all_yaml[V / "edits/base.yaml"]
for ed in base["edits"]:
    for i, ch in enumerate(ed["changes"]):
        check_change(ch, f"base {ed['id']}#{i}")
base_facts = dict(facts)
base_entities = dict(entities)

# ---------- 6. gold ----------
def resolve(ref):
    if isinstance(ref, str) and ref.startswith(("new:", "pending:")):
        return None
    return ref

def gold_key(ch):
    op = ch["op"]
    if op not in ("set_attribute", "add_value", "add_relation"):
        return None, None
    ids = [ch.get("entity"), ch.get("from"), ch.get("to")]
    if any(isinstance(x, str) and x.startswith(("new:", "pending:")) for x in ids if x):
        return None, None
    ent = ch.get("entity") or ch.get("from")
    if ent not in entities: return None, None
    sch, info = schema_for(ent)
    if op == "add_relation":
        if ch["relation"] not in sch["relations"] and ch["relation"] not in CORE_RELATIONS:
            return "out_of_schema", None
        return fact_key(ch, world), (ch["from"], ch["to"])
    etype = info[1]
    if ch["attribute"] not in sch["attrs"](etype):
        return "out_of_schema", None
    return fact_key(ch, sch), ch.get("value")

# Faits acceptés avant certains lots dans les parcours (pour les supports attendus).
facts_by_batch_extra = {
    "b3": {("attr", "veilleurs", "vows", "silence"): "silence"},
}

for p in sorted((V / "gold").glob("*.yaml")):
    g = all_yaml[p]
    docfile = None
    for cand in (V / "docs").rglob("*.md"):
        head = cand.read_text(encoding="utf-8").split("---")[1]
        meta = yaml.safe_load(head)
        if meta.get("id") == g["document"] and (f".v{g['version']}" in cand.name or ".v" not in cand.name):
            docfile = cand
    if not docfile:
        err(f"{p.name} : document {g['document']} v{g['version']} introuvable"); continue
    body = docfile.read_text(encoding="utf-8").split("---", 2)[2]
    paras = [x.strip() for x in re.split(r"\n\s*\n", body) if x.strip() and not x.strip().startswith("#")]
    for ps in g.get("passages") or []:
        idx = ps["index"]
        if idx > len(paras) or not paras[idx - 1].startswith(ps["starts_with"]):
            err(f"{p.name} p{idx} : ne commence pas par « {ps['starts_with']} »")
        for ch in ps.get("changes") or []:
            oc = ch.get("outcome")
            if g["batch"] in ("b7",):   # b7 suppose des décisions antérieures (conseil créé)
                continue
            k, v = gold_key(ch)
            if oc == "out_of_schema" and k not in ("out_of_schema",) and ch["op"] in ("set_attribute", "add_relation", "add_value"):
                if not any(str(ch.get(x, "")).startswith("new:") for x in ("entity", "from", "to")):
                    err(f"{p.name} p{idx} : marqué out_of_schema mais déclaré dans le schéma")
            if oc == "support" and k and k != "out_of_schema":
                known = dict(base_facts); known.update(facts_by_batch_extra.get(g["batch"], {}))
                if known.get(k) != v:
                    err(f"{p.name} p{idx} : support attendu mais {k} vaut {known.get(k)!r} (≠ {v!r})")
            if oc == "anomaly" and k and k != "out_of_schema":
                if k not in base_facts or base_facts[k] == v:
                    err(f"{p.name} p{idx} : anomalie attendue mais pas de collision sur {k}")

# ---------- rapport ----------
print(f"Entités de base : {len(base_entities)} ; faits de base : {len(base_facts)}")
for n in notes: print("NOTE   ", n)
for e in errors: print("ERREUR ", e)
print("OK" if not errors else f"{len(errors)} erreur(s)")
sys.exit(1 if errors else 0)
