"""Pipeline d'ingestion par le service (cadre d'interface I-PIP-01, I-LLM-01 ; décisions I4).

- `pipeline.estimate` (calcul) : ce qu'E4 coûterait — passages absents du cache pour cet extracteur.
- `pipeline.run` (calcul) : étapes de x à y (au plus E9) ; entrée injectée à n'importe quelle étape (artefact
  d'une exécution enregistrée, ou artefact saisi) ; l'artefact de chaque étape est enregistré et réinjectable ;
  avec un modèle, rien n'est appelé sans `confirm` (estimation d'abord), au plus `max_calls` appels.
- `pipeline.save` (écriture) : reprend un artefact à partir d'E4 — l'extraction est **relue, jamais rappelée** —,
  refait E3 et E5 à E8 contre la cible, enregistre le lot (E9+), puis, sur demande, E10 à E12. C'est ce que rejoue
  la promotion d'un bac (I-SBX-01) : aucun nouvel appel au modèle.
- `runs.artifact` (consultation) et `runs.diff` (consultation) : comparer deux exécutions étape par étape.
"""

from __future__ import annotations

import json
import threading
import time
from typing import Any, Literal

from pydantic import Field

from worldkit.core.schema import Issue, IssueCode, Severity

from .registry import Output, Params, operation
from .session import Context

Stage = Literal["E1", "E2", "E3", "E4", "E5", "E6", "E7", "E8", "E9", "E9+", "E10", "E11", "E12"]


def _S() -> Any:
    from worldkit.ingest import stages
    return stages


def extractor_of(oracle: str | None, profile: str | None, llm_config: str | None) -> Any:
    from pathlib import Path
    from worldkit.periphery.extraction import OracleExtractor
    if oracle:
        return OracleExtractor(Path(oracle))
    from worldkit.periphery.llm import load_config, make_adapter
    from worldkit.periphery.llm_extractor import LLMExtractor
    prof = load_config(llm_config).profile(profile, "extraction")
    return LLMExtractor(make_adapter(prof), prof)


def max_calls_of(value: int | None, llm_config: str | None) -> int:
    if value is not None:
        return value
    from worldkit.periphery.llm import load_config
    return load_config(llm_config).max_calls_per_run


def stage_indicators(stage: str, art: Any) -> dict[str, Any]:
    """Indicateurs propres à chaque étape (cadre d'interface §6)."""
    passages = [p for d in art.live() for p in d.passages]
    tags: dict[str, int] = {}

    def count(values: list[str]) -> dict[str, int]:
        out: dict[str, int] = {}
        for v in values:
            out[v] = out.get(v, 0) + 1
        return out
    c = art.counters
    if stage == "E1":
        return {"documents": len(art.documents), "obsolete": sum(1 for d in art.documents if d.obsolete)}
    if stage == "E2":
        return {"passages": len(passages)}
    if stage == "E3":
        return {"natures": count([p.nature or "?" for p in passages]),
                "unchanged": sum(1 for p in passages if p.unchanged), "removed": c.removed}
    if stage == "E4":
        return {"extracted": c.extracted, "cached": c.cached, "unchanged": c.unchanged, "capped": c.capped,
                "errors": len(c.errors), "llm_calls": c.llm_calls,
                "drafts": sum(len((p.extraction or {}).get("drafts", [])) for p in passages),
                "claims": sum(len((p.extraction or {}).get("claims", [])) for p in passages)}
    if stage == "E5":
        return {"drafts": sum(len(p.drafts or []) for p in passages)}
    if stage == "E6":
        return {"retained": len(art.raw), "awaiting_nature": sum(1 for r in art.raw if r["awaiting"]),
                "flags": count([f for p in passages for f in p.flags])}
    if stage == "E7":
        return {"items": len(art.items), "new_entities": sum(1 for e in art.new_entities if e.get("own")),
                "reused_entities": sum(1 for e in art.new_entities if not e.get("own"))}
    if stage == "E8":
        for q in art.qualified:
            for t in q["tags"]:
                tags[t] = tags.get(t, 0) + 1
        return {"qualified": len(art.qualified), "by_tag": tags}
    if stage in ("E9", "E9+"):
        for pr in art.proposals:
            for q in pr["items"]:
                for t in q["tags"]:
                    tags[t] = tags.get(t, 0) + 1
        return {"proposals": len(art.proposals), "supports": len(art.supports), "remembered": c.remembered,
                "by_tag": tags, "written": art.written}
    if stage == "E10":
        return {"decisions": len(art.decided), "ok": sum(1 for d in art.decided if d.get("ok"))}
    if stage == "E11":
        return {"applied": len(art.applied)}
    if stage == "E12":
        return {"signals": len(art.views.get("signals", [])), "pages": len(art.views.get("pages", []))}
    return {}


class _Stages:
    """Exécute des étapes en mesurant chacune et en enregistrant son artefact."""

    def __init__(self, ctx: Context) -> None:
        self.ctx = ctx
        self.summary: list[dict[str, Any]] = []

    def after(self, stage: str, art: Any, started: float) -> None:
        S = _S()
        entry = {"stage": stage, "name": S.STAGE_NAMES[stage], "duration_ms": round((time.perf_counter() - started) * 1000, 1),
                 "indicators": stage_indicators(stage, art)}
        self.summary.append(entry)
        if self.ctx.run_id is not None:
            self.ctx.session.runs.save_artifact(self.ctx.run_id, stage, art.to_json())
        self.ctx.report(stage, {"completed": [s["stage"] for s in self.summary]})


def _load_art(ctx: Context, input_run: int | None, input_stage: str | None, artifact: dict[str, Any] | None) -> Any:
    S = _S()
    if artifact is not None:
        return S.PipelineArt.model_validate(artifact)
    if input_run is None:
        return None
    _, text = ctx.session.runs.artifact(input_run, input_stage)
    return S.PipelineArt.model_validate_json(text)


class DocsParams(Params):
    batch_id: str = Field(description="identifiant du lot")
    documents: list[str] = Field(default_factory=list, description="fichiers ; sinon ceux du lot dans `batches`")
    batches: str | None = Field(None, description="batches.yaml")
    batch: str | None = Field(None, description="lot déclaré dans batches.yaml (défaut : batch_id)")
    branch: str | None = None
    oracle: str | None = Field(None, description="dossier gold/ : extracteur oracle")
    profile: str | None = Field(None, description="profil de modèle (worldkit-llm.yaml) : extracteur LLM")
    llm_config: str | None = None

    def paths(self) -> list[str]:
        from worldkit.ingest.batch import batch_documents
        if self.documents:
            return list(self.documents)
        if self.batches:
            return [str(p) for p in batch_documents(self.batches, self.batch or self.batch_id)]
        return []


@operation("pipeline.estimate", "compute", DocsParams,
           "coût d'une extraction : passages absents du cache pour cet extracteur (E1 à E3, sans appel)",
           ("I-LLM-01", "T-ING-09"),
           example={"batch_id": "b4", "batches": "corpus/valmont-v1/valmont/docs/batches.yaml", "profile": "sonnet"})
def pipeline_estimate(ctx: Context, p: DocsParams) -> Output:
    S = _S()
    assert ctx.world is not None
    extractor = extractor_of(p.oracle, p.profile, p.llm_config)
    run = S.Run(ctx.world, extractor)
    art = S.run_range(run, S.start(ctx.world, p.batch_id, p.branch), "E1", "E3", p.paths())
    missing = S.missing_from_cache(run, art)
    passages = sum(1 for d in art.live() for q in d.passages if not q.unchanged)
    model = getattr(getattr(extractor, "profile", None), "model", None)
    calls = 0 if extractor.version.startswith("oracle") else len(missing)
    return Output({"extractor": extractor.version, "model": model, "passages": passages, "calls": calls,
                   "cached": passages - len(missing), "max_calls": max_calls_of(None, p.llm_config),
                   "missing": [f"{d} p{i}" for d, i in missing]}, [], {"calls": calls, "passages": passages})


class RunParams(DocsParams):
    from_: Stage = Field("E1", alias="from", description="première étape")
    to: Stage = Field("E9", description="dernière étape (au plus E9 : l'écriture passe par pipeline.save)")
    input: int | None = Field(None, description="exécution dont on reprend l'artefact")
    input_stage: str | None = Field(None, description="étape de l'artefact repris (défaut : la dernière)")
    artifact: dict[str, Any] | None = Field(None, description="ou un artefact saisi (JSON ou YAML)")
    confirm: bool = Field(False, description="autoriser les appels au modèle estimés")
    max_calls: int | None = Field(None, description="plafond d'appels (défaut : max_calls_per_run)")


@operation("pipeline.run", "compute", RunParams,
           "étapes du pipeline de x à y (au plus E9), sans rien écrire ; artefacts enregistrés et réinjectables",
           ("I-PIP-01", "I-LLM-01", "T-ING-09"),
           example={"batch_id": "b4", "batches": "corpus/valmont-v1/valmont/docs/batches.yaml",
                    "oracle": "corpus/valmont-v1/valmont/gold", "from": "E1", "to": "E9"})
def pipeline_run(ctx: Context, p: RunParams) -> Output:
    S = _S()
    assert ctx.world is not None
    first, last = p.from_, p.to
    if S.STAGES.index(last) > S.STAGES.index("E9"):
        raise ValueError("pipeline.run s'arrête au plus à E9 : l'enregistrement du lot passe par pipeline.save")
    if S.STAGES.index(first) > S.STAGES.index(last):
        raise ValueError(f"{first} vient après {last}")
    issues: list[Issue] = []
    if first == "E1":
        art = S.start(ctx.world, p.batch_id, p.branch)
    else:
        art = _load_art(ctx, p.input, p.input_stage, p.artifact)
        if art is None:
            raise ValueError(f"commencer à {first} demande un artefact : `input` (exécution) ou `artifact`")
        expected = S.STAGES[S.STAGES.index(first) - 1]
        if art.stage != expected and S.STAGES.index(art.stage) < S.STAGES.index(expected):
            raise ValueError(f"l'artefact s'arrête à {art.stage} : il faut au moins {expected} pour commencer à {first}")
        head = ctx.world.state(art.branch)
        if art.base.get("seq") != head.seq:
            issues.append(Issue(IssueCode.STALE_EDIT, f"base de l'artefact au rang {art.base.get('seq')}, tête de "
                                f"{art.branch} au rang {head.seq} : les étapes suivantes lisent la tête",
                                "T-ING-06", Severity.WARNING))
    needs_extractor = S.STAGES.index(first) <= S.STAGES.index("E4") <= S.STAGES.index(last)
    if needs_extractor and not (p.oracle or p.profile):
        raise ValueError("E4 demande un extracteur nommé : `oracle` (dossier gold/) ou `profile` (modèle)")
    extractor = extractor_of(p.oracle, p.profile, p.llm_config) if (p.oracle or p.profile) else None
    cancel = ctx.cancel or threading.Event()
    run = S.Run(ctx.world, extractor, None, lambda stage, info: ctx.report(stage, info), cancel)
    stages = _Stages(ctx)
    estimate = None
    for stage in S.STAGES[S.STAGES.index(first):S.STAGES.index(last) + 1]:
        if cancel.is_set():
            issues.append(Issue(IssueCode.EDIT_RULE, f"arrêt demandé avant {stage}", "I-OBJ-05", Severity.WARNING))
            break
        if stage == "E4":
            if extractor is None:
                raise ValueError("E4 demande un extracteur : `oracle` ou `profile`")
            if not extractor.version.startswith("oracle"):
                missing = S.missing_from_cache(run, art)
                run.max_calls = max_calls_of(p.max_calls, p.llm_config)
                estimate = {"calls": min(len(missing), run.max_calls), "missing": len(missing),
                            "max_calls": run.max_calls, "model": extractor.profile.model}
                if missing and not p.confirm:
                    return Output({"estimate": estimate, "stages": stages.summary, "final_stage": art.stage},
                                  issues + [Issue(IssueCode.EDIT_RULE, f"{len(missing)} passage(s) à envoyer au "
                                                  f"modèle {extractor.profile.model} (plafond {run.max_calls}) : "
                                                  "confirmer pour lancer", "I-LLM-01", Severity.WARNING)],
                                  {"estimated_calls": estimate["calls"]}, status="pending")
        started = time.perf_counter()
        art = S.run_range(run, art, stage, stage, p.paths() if stage == "E1" else None)
        stages.after(stage, art, started)
    c = art.counters
    if c.capped:
        issues.append(Issue(IssueCode.EDIT_RULE, f"plafond atteint : {c.capped} passage(s) non extrait(s), repris à la "
                            "relance", "I-LLM-01", Severity.WARNING))
    for where, error in c.errors.items():
        issues.append(Issue(IssueCode.EDIT_RULE, f"{where} : erreur d'extraction ({error[:160]})", "T-ING-17",
                            Severity.WARNING))
    value = {"batch_id": art.batch_id, "branch": art.branch, "base": art.base, "extractor": art.extractor,
             "from": first, "to": last, "final_stage": art.stage, "stages": stages.summary, "estimate": estimate,
             "flagged": art.flagged(), "proposals": [pr["id"] for pr in art.proposals]}
    return Output(value, issues, {"stages": len(stages.summary), "llm_calls": c.llm_calls, "extracted": c.extracted,
                                  "cached": c.cached, "proposals": len(art.proposals)})


class SaveParams(Params):
    input: int | None = Field(None, description="exécution de pipeline.run dont on reprend l'artefact")
    input_stage: str | None = None
    artifact: dict[str, Any] | None = None
    to: Stage = Field("E9+", description="E9+ (enregistrer), jusqu'à E12")
    decisions: list[dict[str, Any]] = Field(default_factory=list,
                                            description="E10 : [{action: accept, proposal: …}, {action: nature, …}]")
    branch: str | None = None


@operation("pipeline.save", "write", SaveParams,
           "enregistrer un lot depuis un artefact (extraction relue, E3 et E5 à E8 refaits contre la cible), "
           "puis E10 à E12 sur demande", ("I-PIP-01", "T-ING-01", "I-SBX-01"))
def pipeline_save(ctx: Context, p: SaveParams) -> Output:
    S = _S()
    assert ctx.world is not None
    art = _load_art(ctx, p.input, p.input_stage, p.artifact)
    if art is None:
        raise ValueError("donner `input` (exécution de pipeline.run) ou `artifact`")
    if S.STAGES.index(art.stage) < S.STAGES.index("E4"):
        raise ValueError(f"l'artefact s'arrête à {art.stage} : l'extraction (E4) est nécessaire pour enregistrer")
    if S.STAGES.index(p.to) < S.STAGES.index("E9+"):
        raise ValueError("pipeline.save va au moins jusqu'à E9+ (enregistrer)")
    head = ctx.world.state(p.branch or ctx.world.reference_branch)
    art.branch = head.branch
    art.base = {"branch": head.branch, "seq": head.seq, "schema_rev": head.schema_rev}
    art.raw, art.items, art.qualified, art.proposals, art.supports, art.states = [], [], [], [], [], {}
    art.decisions = list(p.decisions)
    run = S.Run(ctx.world, None, None, lambda stage, info: ctx.report(stage, info), ctx.cancel or threading.Event())
    stages = _Stages(ctx)
    for stage in ["E3", "E5", "E6", "E7", "E8", "E9+", "E10", "E11", "E12"]:
        if S.STAGES.index(stage) > S.STAGES.index(p.to):
            break
        if stage == "E10" and not art.decisions:
            continue
        started = time.perf_counter()
        art = S.STEP[stage](run, art)
        stages.after(stage, art, started)
    from worldkit.ingest.batch import report_of
    report = report_of(art)
    value = {"batch": art.batch_id, "base": art.base, "stages": stages.summary, "proposals": [q.id for q in report.proposals],
             "new_entities": [e.id for e in report.new_entities], "flagged": report.flagged, "decided": art.decided,
             "applied": art.applied, "views": art.views}
    issues = [Issue(IssueCode.EDIT_RULE, f"{d.get('proposal') or d.get('document')} : {', '.join(d.get('issues', []))}",
                    "R-PRI-04") for d in art.decided if not d.get("ok")]
    return Output(value, issues, {"proposals": len(report.proposals), "supports": len(report.supports),
                                  "decisions": len(art.decided), "applied": len(art.applied)})


class ArtifactParams(Params):
    id: int
    stage: str | None = None


@operation("runs.artifact", "read", ArtifactParams, "l'artefact d'une étape d'une exécution de pipeline",
           ("I-PIP-01",), needs_world=False)
def runs_artifact(ctx: Context, p: ArtifactParams) -> Output:
    stage, text = ctx.session.runs.artifact(p.id, p.stage)
    return Output({"run": p.id, "stage": stage, "stages": ctx.session.runs.artifact_stages(p.id),
                   "artifact": json.loads(text)})


class DiffParams(Params):
    a: int = Field(description="première exécution")
    b: int = Field(description="seconde exécution")


def _elements(stage: str, art: dict[str, Any]) -> dict[str, Any]:
    """Éléments comparables d'un artefact à une étape, identifiés par passage et par contenu."""
    def passage_key(d: dict[str, Any], p: dict[str, Any]) -> str:
        return f"{d['doc_id']} p{p['index']}"
    out: dict[str, Any] = {}
    docs = art.get("documents", [])
    if stage in ("E1", "E2", "E3"):
        for d in docs:
            out[f"document {d['doc_id']}"] = {"obsolete": d["obsolete"], "axes": d["axes"]}
            for p in d.get("passages", []):
                out[passage_key(d, p)] = {"fingerprint": p["fingerprint"], "nature": p.get("nature"),
                                          "unchanged": p.get("unchanged")}
    elif stage in ("E4", "E5"):
        field_ = "extraction" if stage == "E4" else "drafts"
        for d in docs:
            for p in d.get("passages", []):
                value = p.get(field_)
                if stage == "E4" and value is not None:
                    value = {"drafts": value.get("drafts", []), "claims": value.get("claims", []),
                             "flags": value.get("flags", [])}
                for i, x in enumerate((value or {}).get("drafts", []) if stage == "E4" else (value or [])):
                    out[f"{passage_key(d, p)} · {json.dumps(x, sort_keys=True, ensure_ascii=False)}"] = True
                if stage == "E4" and value is not None:
                    for c in value["claims"]:
                        out[f"{passage_key(d, p)} · affirmation « {c.get('text')} »"] = True
                    out[f"{passage_key(d, p)} · drapeaux"] = sorted(value["flags"])
    elif stage == "E6":
        for r in art.get("raw", []):
            out[f"{r['doc_id']} p{r['passage']} · {json.dumps(r['draft'], sort_keys=True, ensure_ascii=False)}"] = \
                {"awaiting": r["awaiting"], "optional": r["optional"]}
        for d in docs:
            for p in d.get("passages", []):
                if p.get("flags"):
                    out[f"{passage_key(d, p)} · drapeaux"] = sorted(p["flags"])
    elif stage == "E7":
        for it in art.get("items", []):
            out[f"{it['doc_id']} p{it['passage']} · {json.dumps(it['change'], sort_keys=True, ensure_ascii=False)}"] = True
        for e in art.get("new_entities", []):
            out[f"entité nouvelle {e['id']}"] = {"type": e["type"], "name": e.get("name"), "own": e.get("own")}
    elif stage == "E8":
        for q in art.get("qualified", []):
            it = q["item"]
            out[f"{it['doc_id']} p{it['passage']} · {json.dumps(it['change'], sort_keys=True, ensure_ascii=False)}"] = \
                sorted(q["tags"])
    elif stage in ("E9", "E9+"):
        for pr in art.get("proposals", []):
            out[f"proposition {pr['id']}"] = {"subject": pr["subject"], "kind": pr["kind"],
                                              "changes": [json.dumps(q["item"]["change"], sort_keys=True,
                                                                     ensure_ascii=False) for q in pr["items"]],
                                              "tags": sorted({t for q in pr["items"] for t in q["tags"]})}
        out["supports"] = len(art.get("supports", []))
    else:
        out[stage] = {k: art.get(k) for k in ("decided", "applied", "views")}
    return out


@operation("runs.diff", "read", DiffParams, "deux exécutions de pipeline comparées étape par étape",
           ("I-PIP-01", "I-PRI-05"), needs_world=False)
def runs_diff(ctx: Context, p: DiffParams) -> Output:
    runs = ctx.session.runs
    sa, sb = runs.artifact_stages(p.a), runs.artifact_stages(p.b)
    ra, rb = runs.result(p.a), runs.result(p.b)
    summaries = {}
    for which, r in (("a", ra), ("b", rb)):
        for s in (r.output or {}).get("stages", []) if isinstance(r.output, dict) else []:
            summaries.setdefault(s["stage"], {})[which] = s
    stages = []
    for stage in [s for s in sa if s in sb]:
        a = _elements(stage, json.loads(runs.artifact(p.a, stage)[1]))
        b = _elements(stage, json.loads(runs.artifact(p.b, stage)[1]))
        only_a = sorted(k for k in a if k not in b)
        only_b = sorted(k for k in b if k not in a)
        changed = sorted(k for k in a if k in b and a[k] != b[k])
        stages.append({"stage": stage, "same": not (only_a or only_b or changed), "only_a": only_a, "only_b": only_b,
                       "changed": [{"key": k, "a": a[k], "b": b[k]} for k in changed],
                       "indicators": {w: summaries.get(stage, {}).get(w, {}).get("indicators") for w in ("a", "b")},
                       "duration_ms": {w: summaries.get(stage, {}).get(w, {}).get("duration_ms") for w in ("a", "b")}})
    first_diff = next((s["stage"] for s in stages if not s["same"]), None)
    return Output({"a": p.a, "b": p.b, "stages": stages, "first_difference": first_diff,
                   "only_in_a": [s for s in sa if s not in sb], "only_in_b": [s for s in sb if s not in sa]},
                  [], {"compared": len(stages), "different": sum(1 for s in stages if not s["same"])})
