"""Mesures T2 par le service (cadre d'interface I-VUE-09 ; décisions I6 ; T-ING-19, T-TST-01).

- `eval.run` (calcul) : un extracteur contre le gold, sur des lots ; avec un modèle, estimation exacte des appels
  (passages absents du cache, plus les répétitions de stabilité), rien sans confirmation, refus au-delà du plafond
  plutôt qu'une mesure partielle qui fausserait les chiffres (I-LLM-01). Le résultat garde le détail par passage.
- `eval.history` (consultation) : les mesures enregistrées, les plus récentes d'abord.
- `eval.compare` (consultation) : deux mesures côte à côte, par opération puis passage par passage (décision I6).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import Field

from worldkit.core.schema import Issue, IssueCode, Severity

from .registry import Output, Params, operation
from .session import Context


def readable(key: Any) -> str:
    """Un changement de la mesure (paires champ, valeur) sous une forme lisible."""
    try:
        return " ".join(f"{k}={v}" for k, v in key)
    except (TypeError, ValueError):
        return str(key)


class EvalParams(Params):
    batches: str = Field("corpus/valmont-v1/valmont/docs/batches.yaml", description="batches.yaml")
    batch: list[str] = Field(default_factory=list, description="lots mesurés (défaut : tous)")
    oracle: str = Field("corpus/valmont-v1/valmont/gold", description="dossier gold/ (la référence)")
    profile: str | None = Field(None, description="profil de modèle mesuré (défaut : l'oracle lui-même)")
    llm_config: str | None = None
    repeat: int = Field(1, ge=1, le=3, description="2 : mesurer la stabilité (deux appels par passage)")
    confirm: bool = False
    max_calls: int | None = None
    no_cache: bool = False


def _documents(p: EvalParams) -> tuple[list[str], list[list[Path]]]:
    import yaml
    from worldkit.ingest.batch import batch_documents
    declared = yaml.safe_load(Path(p.batches).read_text(encoding="utf-8"))["batches"]
    batches = p.batch or [b["id"] for b in declared]
    return batches, [batch_documents(p.batches, b) for b in batches]


def _estimate(extractor: Any, cached: Any, gold_dir: Path, groups: list[list[Path]], repeat: int) -> tuple[int, int]:
    """(appels, passages mesurés) : passages annotés hors cache, plus les répétitions qui contournent le cache."""
    from worldkit.ingest.declaration import fingerprint, read_document
    from worldkit.periphery.evaluation import _gold_index
    gold = _gold_index(gold_dir)
    known = set(getattr(cached, "_known", {})) if cached is not None else set()
    measured = missing = 0
    for group in groups:
        for path in group:
            doc = read_document(path)
            for passage in doc.passages:
                if any(passage.text.startswith(g["starts_with"]) for g in gold.get(doc.doc_id, [])):
                    measured += 1
                    if fingerprint(passage.text) not in known:
                        missing += 1
    if extractor.version.startswith("oracle"):
        return 0, measured
    return missing + (repeat - 1) * measured, measured


@operation("eval.run", "compute", EvalParams,
           "mesure T2 d'un extracteur contre le gold (coût contrôlé), détail par opération et par passage",
           ("T-ING-19", "T-TST-01", "I-LLM-01"),
           example={"batch": ["b4"], "oracle": "corpus/valmont-v1/valmont/gold"})
def eval_run(ctx: Context, p: EvalParams) -> Output:
    from worldkit.ingest.batch import CachedExtractor, extraction_context, schema_fingerprint
    from worldkit.periphery.evaluation import evaluate
    from worldkit.periphery.extraction import OracleExtractor
    from .pipeline import extractor_of, max_calls_of
    assert ctx.world is not None
    gold_dir = Path(p.oracle)
    batches, groups = _documents(p)
    state = ctx.world.state()
    extractor = extractor_of(None if p.profile else p.oracle, p.profile, p.llm_config)
    cached = None if p.no_cache or extractor.version.startswith("oracle") else \
        CachedExtractor(extractor, ctx.world, schema_fingerprint(state))
    calls, measured = _estimate(extractor, cached if not p.no_cache else None, gold_dir, groups, p.repeat)
    model = getattr(getattr(extractor, "profile", None), "model", None)
    estimate = {"calls": calls, "passages": measured, "model": model, "extractor": extractor.version}
    if calls:
        cap = max_calls_of(p.max_calls, p.llm_config)
        estimate["max_calls"] = cap
        if calls > cap:
            return Output({"estimate": estimate}, [Issue(IssueCode.EDIT_RULE, f"{calls} appel(s) estimé(s), au-delà du "
                                                         f"plafond {cap} : réduire les lots ou relever max_calls (une "
                                                         "mesure partielle fausserait les chiffres)", "I-LLM-01")],
                          {"estimated_calls": calls})
        if not p.confirm:
            return Output({"estimate": estimate}, [Issue(IssueCode.EDIT_RULE, f"{calls} appel(s) au modèle {model} : "
                                                         "confirmer pour lancer la mesure", "I-LLM-01",
                                                         Severity.WARNING)], {"estimated_calls": calls},
                          status="pending")
    ctx.report("eval", {"passages": measured, "calls": calls})
    report = evaluate(cached or extractor, OracleExtractor(gold_dir), gold_dir, groups,
                      extraction_context(ctx.world, state), p.repeat, state)
    if cached is not None:
        cached.flush()
    summary = report.summary()
    passages = []
    for r in report.passages:
        passages.append({"doc": r.doc, "index": r.index, "missed": sorted(readable(k) for k in r.expected - r.found),
                         "extra": sorted(readable(k) for k in r.extra),
                         "optional": sorted(readable(k) for k in r.found & r.optional),
                         "found": sorted(readable(k) for k in r.found), "expected": sorted(readable(k) for k in r.expected),
                         "supports": sorted(readable(k) for k in r.supports), "traps": r.traps,
                         "attribution_ok": r.attribution_ok, "claims": [r.claims_found, r.claims_expected],
                         "stability": r.stability, "error": r.error, "seconds": round(r.seconds, 1),
                         "first_only": sorted(readable(k) for k in r.found - (r.variant or r.found)),
                         "second_only": sorted(readable(k) for k in (r.variant or r.found) - r.found),
                         "usage": r.usage})
    value = {"extractor": report.extractor, "model": model, "batches": batches, "repeat": p.repeat,
             "summary": summary, "passages": passages, "estimate": estimate}
    issues = [Issue(IssueCode.EDIT_RULE, f"{x['doc']} p{x['index']} : piège tombé ({t})", "T-TST-01", Severity.WARNING)
              for x in passages for t in x["traps"]]
    if report.all_failed:
        issues.insert(0, Issue(IssueCode.EDIT_RULE, "toutes les extractions ont échoué, la mesure ne vaut rien : "
                                                    f"{report.passages[0].error[:200]}", "T-ING-17"))
    return Output(value, issues, {"precision": summary["precision"], "recall": summary["recall"],
                                  "questions_precision": summary["questions"]["precision"],
                                  "questions_recall": summary["questions"]["recall"],
                                  "traps": summary["traps_fallen"], "passages": summary["passages"],
                                  "calls": calls,
                                  **({k: summary["usage"][k] for k in ("input_tokens", "cost", "over_budget")}
                                     if "usage" in summary else {})})


class HistoryParams(Params):
    limit: int = 50


@operation("eval.history", "read", HistoryParams, "mesures T2 enregistrées, les plus récentes d'abord", ("T-TST-01",),
           needs_world=False)
def eval_history(ctx: Context, p: HistoryParams) -> Output:
    rows = []
    for rec in ctx.session.runs.runs(limit=p.limit, operation="eval.run"):
        if rec.status != "ok":
            continue
        r = ctx.session.runs.result(rec.id)
        o = r.output or {}
        s = o.get("summary", {})
        rows.append({"run": rec.id, "created": rec.created, "target": rec.target, "extractor": o.get("extractor"),
                     "model": o.get("model"), "batches": o.get("batches"), "repeat": o.get("repeat"),
                     "precision": s.get("precision"), "recall": s.get("recall"), "questions": s.get("questions"),
                     "traps": s.get("traps_fallen"), "errors": s.get("errors"), "stability": s.get("stability"),
                     "seconds": s.get("seconds"), "passages": s.get("passages"), "calls": (o.get("estimate") or {}).get("calls"),
                     "usage": s.get("usage")})
    return Output(rows, [], {"measures": len(rows)})


class CompareMeasures(Params):
    a: int
    b: int


@operation("eval.compare", "read", CompareMeasures,
           "deux mesures côte à côte : chiffres, par opération, puis passage par passage", ("T-TST-01",),
           needs_world=False)
def eval_compare(ctx: Context, p: CompareMeasures) -> Output:
    ra, rb = ctx.session.runs.result(p.a), ctx.session.runs.result(p.b)
    oa, ob = ra.output or {}, rb.output or {}
    if "summary" not in oa or "summary" not in ob:
        raise ValueError("comparer deux mesures terminées (eval.run)")
    pa = {(x["doc"], x["index"]): x for x in oa["passages"]}
    pb = {(x["doc"], x["index"]): x for x in ob["passages"]}
    passages = []
    for key in sorted(set(pa) | set(pb)):
        x, y = pa.get(key), pb.get(key)
        fa, fb = set(x["found"]) if x else set(), set(y["found"]) if y else set()
        expected = set((x or y)["expected"])
        if fa == fb and (x or {}).get("traps") == (y or {}).get("traps"):
            continue
        passages.append({"doc": key[0], "index": key[1], "expected": sorted(expected),
                         "only_a": sorted(fa - fb), "only_b": sorted(fb - fa),
                         "a_right": sorted((fa - fb) & expected), "b_right": sorted((fb - fa) & expected),
                         "traps_a": (x or {}).get("traps", []), "traps_b": (y or {}).get("traps", [])})
    ops = sorted(set(oa["summary"].get("per_op", {})) | set(ob["summary"].get("per_op", {})))
    per_op = [{"op": op, "a": oa["summary"]["per_op"].get(op), "b": ob["summary"]["per_op"].get(op)} for op in ops]
    return Output({"a": {"run": p.a, "extractor": oa.get("extractor"), "model": oa.get("model"), "summary": oa["summary"]},
                   "b": {"run": p.b, "extractor": ob.get("extractor"), "model": ob.get("model"), "summary": ob["summary"]},
                   "per_op": per_op, "passages": passages}, [], {"passages_differing": len(passages)})
