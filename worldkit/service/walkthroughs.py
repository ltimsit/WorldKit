"""Parcours d'acceptation exécutables (cadre d'interface I-ACC-01 ; décisions I5).

- Un parcours du corpus (`walkthroughs.yaml`) s'exécute **pas à pas** dans un monde d'acceptation neuf, créé
  depuis `world.yaml` et enregistré comme un bac (origine `acceptance:<parcours>`, jamais promouvable) ; ses
  **prérequis** (`requires`) sont rejoués d'abord, dans l'ordre.
- Chaque verbe `do:` se traduit en opérations du service (décision I5 : verbes lisibles, identifiants réels,
  actions du service). Les appels ne sont pas enregistrés un à un : le parcours entier est une exécution.
- Chaque attendu est soit une phrase (« non structuré », à vérifier à l'œil), soit `{text, checks}` : des
  vérifications typées (`fact`, `no_fact`, `pending`, `proposal`, `support`, `signal`, `page`, `branch`, `step`,
  `call`), chacune avec une branche, un point et un filtre facultatifs.
- pytest et l'interface appellent le même exécuteur (`walkthrough.run`).
"""

from __future__ import annotations

import glob as globlib
import json
from pathlib import Path
from typing import Any

import yaml
from pydantic import Field

from worldkit.core.schema import Issue, IssueCode, Severity

from .registry import Output, Params, operation
from .session import Context, Session

CORPUS = "corpus/valmont-v1"


def load_walkthroughs(corpus: str | Path = CORPUS) -> dict[str, dict[str, Any]]:
    path = Path(corpus) / "valmont" / "walkthroughs" / "walkthroughs.yaml"
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    return {w["id"]: w for w in raw["walkthroughs"]}


def chain_of(walkthroughs: dict[str, dict[str, Any]], wid: str) -> list[str]:
    """Le parcours et ses prérequis, prérequis d'abord, chacun une fois."""
    out: list[str] = []

    def visit(w: str, stack: tuple[str, ...]) -> None:
        if w in stack:
            raise ValueError(f"prérequis circulaires : {' → '.join((*stack, w))}")
        if w not in walkthroughs:
            raise KeyError(f"parcours inconnu : {w}")
        for r in walkthroughs[w].get("requires", []) or []:
            visit(r, (*stack, w))
        if w not in out:
            out.append(w)
    visit(wid, ())
    return out


def _get(obj: Any, path: str | list[Any] | None) -> Any:
    """Chemin dans un résultat : `output.page.title` ou `[output, flagged, "doc p6"]` ; index entiers permis."""
    if path is None:
        return obj
    parts = path if isinstance(path, list) else path.split(".")
    for part in parts:
        if isinstance(obj, list):
            obj = obj[int(part)]
        elif isinstance(obj, dict):
            obj = obj[part]
        else:
            obj = getattr(obj, part)
    return obj


class Runner:
    def __init__(self, session: Session, corpus: str | Path, target: str) -> None:
        self.s = session
        self.corpus = Path(corpus)
        self.valmont = self.corpus / "valmont"
        self.target = target
        self.steps: list[dict[str, Any]] = []   # étapes du parcours en cours (pour `check: step`)

    # --- appels ---

    def call(self, op: str, params: dict[str, Any], expect_refused: bool = False) -> dict[str, Any]:
        r = self.s.call(op, params, self.target, record=False)
        ok = (r.status == "refused" or r.status == "error") if expect_refused else r.status in ("ok", "pending")
        return {"op": op, "params": params, "status": r.status, "ok": ok, "output": r.output,
                "issues": [{"code": i.code, "rule": i.rule, "message": i.message, "path": i.path} for i in r.issues]}

    def path(self, p: str) -> str:
        return str(self.valmont / p)

    # --- étapes ---

    def step(self, spec: dict[str, Any]) -> dict[str, Any]:
        verb = spec["do"]
        handler = getattr(self, f"do_{verb}", None)
        if handler is None:
            return {"do": verb, "ok": False, "calls": [], "detail": f"verbe non exécutable : {verb}"}
        calls = handler(spec)
        return {"do": verb, "ok": all(c["ok"] for c in calls), "calls": calls,
                "detail": "; ".join(f"{c['op']} → {c['status']}" for c in calls)}

    def do_load_world(self, spec: dict[str, Any]) -> list[dict[str, Any]]:
        return []  # le monde d'acceptation est créé depuis world.yaml au départ

    def do_apply_edits(self, spec: dict[str, Any]) -> list[dict[str, Any]]:
        raw = yaml.safe_load(Path(self.path(spec["file"])).read_text(encoding="utf-8"))
        return [self.call("edit.apply", {"edit": e}) for e in raw["edits"]]

    def do_apply_edit(self, spec: dict[str, Any]) -> list[dict[str, Any]]:
        return [self.call("edit.apply", {"edit": spec["edit"]}, bool(spec.get("expect_rejected")))]

    def do_set_point(self, spec: dict[str, Any]) -> list[dict[str, Any]]:
        return [self.call("point.set", {k: v for k, v in (("name", spec["name"]), ("branch", spec.get("branch")))
                                        if v is not None})]

    def do_create_branch(self, spec: dict[str, Any]) -> list[dict[str, Any]]:
        return [self.call("branch.create", {"name": spec["name"], "point": spec.get("from")})]

    def do_ingest_batch(self, spec: dict[str, Any]) -> list[dict[str, Any]]:
        batch_id = spec["batch"] + (f".{spec['as']}" if spec.get("as") else "")
        return [self.call("ingest.batch", {"batch_id": batch_id, "batch": spec["batch"],
                                           "batches": self.path("docs/batches.yaml"), "oracle": self.path("gold")})]

    def do_load_scenarios(self, spec: dict[str, Any]) -> list[dict[str, Any]]:
        return [self.call("scenario.load", {"files": [self.path(f) for f in spec["files"]]})]

    def do_load_drafts(self, spec: dict[str, Any]) -> list[dict[str, Any]]:
        return [self.call("drafts.load", {"file": self.path(spec["file"])})]

    def do_play(self, spec: dict[str, Any]) -> list[dict[str, Any]]:
        params = {"playthrough": spec["playthrough"], "file": self.path("scenarios/playthroughs.yaml")}
        for k in ("id", "branch", "version", "confirmations", "free"):
            if k in spec:
                params[k] = spec[k]
        return [self.call("scenario.play", params)]

    def do_transpose(self, spec: dict[str, Any]) -> list[dict[str, Any]]:
        """Transposer un scénario vers une branche, c'est y jouer un déroulé (§5.3 ter)."""
        params: dict[str, Any] = {"playthrough": spec["playthrough_like"], "file": self.path("scenarios/playthroughs.yaml"),
                                  "branch": spec["to"], "id": spec.get("id", f"{spec['playthrough_like']}-{spec['to']}")}
        for k in ("version", "confirmations", "free"):
            if k in spec:
                params[k] = spec[k]
        return [self.call("scenario.play", params)]

    def do_retroactive_redefinition(self, spec: dict[str, Any]) -> list[dict[str, Any]]:
        base = {"changes": spec["changes"], "anchor": spec["anchor_after"]}
        if spec.get("on"):
            base["source"] = spec["on"]
        calls = [self.call("redefine.preview", base)]
        start = {k: v for k, v in base.items()}
        calls.append(self.call("replay.start", start))
        replay_id = (calls[-1]["output"] or {}).get("replay", {}).get("id") if calls[-1]["output"] else None
        for d in spec.get("decisions", []) or []:
            calls.append(self.call("replay.decide", {"id": replay_id, "action": d["action"],
                                                     **({"changes": d["changes"]} if d.get("changes") else {})}))
        return calls

    def do_decide(self, spec: dict[str, Any]) -> list[dict[str, Any]]:
        calls = []
        for d in spec["decisions"]:
            refused = bool(d.get("expect_refused"))
            action = d.get("action")
            if "all" in d:  # toutes les propositions en attente d'un lot
                listed = self.s.call("review.list", {"batch": d["batch"]}, self.target, record=False)
                ids = [p["id"] for p in (listed.output or {}).get("proposals", [])]
                if d["all"] == "abandon":
                    calls.append(self.call("review.abandon", {"proposals": ids, "reason": d.get("reason")}))
                else:
                    calls.append(self.call("review.accept", {"proposals": ids}))
            elif action == "accept":
                params = {"proposals": [d["proposal"]]}
                for k in ("keep", "drop_optional", "reason"):
                    if k in d:
                        params[k] = d[k]
                calls.append(self.call("review.accept", params, refused))
            elif action == "refuse":
                params = {"proposals": [d["proposal"]], **({"changes": d["changes"]} if "changes" in d else {})}
                calls.append(self.call("review.refuse", params, refused))
            elif action == "choose":
                calls.append(self.call("review.choose", {"proposal": d["proposal"]}, refused))
            elif action == "adapt":
                calls.append(self.call("review.adapt", {"proposal": d["proposal"], "changes": d["changes"],
                                                        "replace": bool(d.get("replace"))}, refused))
            elif action == "qualify":
                calls.append(self.call("review.qualify", {"target": d.get("target") or d["proposal"],
                                                          "value": str(d["value"]).lower(),
                                                          **({"visibility": d["visibility"]} if d.get("visibility") else {})},
                                       refused))
            elif action == "promote":
                calls.append(self.call("review.promote", {"proposal": d["proposal"],
                                                          **({"visibility": d["visibility"]} if d.get("visibility") else {})},
                                       refused))
            elif action == "abandon":
                calls.append(self.call("review.abandon", {"proposals": [d["proposal"]], "reason": d.get("reason")}))
            elif action == "dismiss":
                calls.append(self.call("review.dismiss", {"document": d["document"], "passage": d["passage"]}))
            elif action == "nature":
                calls.append(self.call("review.nature", {"document": d["document"], "passage": d["passage"],
                                                         "decision": d.get("decision", "accept")}))
            elif action == "leave_pending":
                calls.append({"op": "(aucune)", "params": d, "status": "pending", "ok": True, "output": None, "issues": []})
            else:
                calls.append({"op": f"({action})", "params": d, "status": "error", "ok": False, "output": None,
                              "issues": [{"code": "unknown_action", "rule": "I-ACC-01", "message": f"action inconnue : {action}",
                                          "path": ""}]})
        return calls

    def do_validate_schema(self, spec: dict[str, Any]) -> list[dict[str, Any]]:
        files = spec["files"]
        paths = sorted(globlib.glob(str(self.corpus / files))) if isinstance(files, str) else \
            [str(self.corpus / f) for f in files]
        return [self.call("schema.validate", {"file": f}, bool(spec.get("expect_rejected"))) for f in paths]

    # --- vérifications ---

    def check(self, c: dict[str, Any]) -> tuple[bool, str]:
        kind = c.get("check")
        fn = getattr(self, f"check_{kind}", None)
        if fn is None:
            return False, f"vérification inconnue : {kind}"
        try:
            return fn(c)
        except (KeyError, IndexError, ValueError, TypeError, AttributeError) as e:
            return False, f"{type(e).__name__} : {e}"

    def world(self) -> Any:
        return self.s.open(self.target)

    def _state(self, c: dict[str, Any]) -> Any:
        w = self.world()
        try:
            return w.state(c.get("branch"), c.get("point"))
        finally:
            w.close()

    def check_fact(self, c: dict[str, Any]) -> tuple[bool, str]:
        state = self._state(c)
        fid = tuple(c["id"])
        fact = state.facts.get(fid)
        if fact is None:
            return False, f"fait absent : {fid}"
        if "value" in c and fact.value != c["value"]:
            return False, f"valeur {fact.value!r}, attendu {c['value']!r}"
        if "visibility" in c and str(fact.visibility) != c["visibility"]:
            return False, f"notoriété {fact.visibility}, attendu {c['visibility']}"
        return True, f"{fid} = {fact.value!r} [{fact.visibility}]"

    def check_no_fact(self, c: dict[str, Any]) -> tuple[bool, str]:
        fid = tuple(c["id"])
        present = fid in self._state(c).facts
        return (not present), ("présent" if present else "absent, comme attendu")

    def check_pending(self, c: dict[str, Any]) -> tuple[bool, str]:
        w = self.world()
        try:
            rec = w.store.edit(c["edit"])
        finally:
            w.close()
        if str(rec.status) != c.get("status", "pending"):
            return False, f"statut {rec.status}"
        if "needs_recheck" in c and rec.needs_recheck != c["needs_recheck"]:
            return False, f"à revérifier = {rec.needs_recheck}"
        return True, f"{c['edit']} {rec.status}, à revérifier = {rec.needs_recheck}"

    def check_proposal(self, c: dict[str, Any]) -> tuple[bool, str]:
        r = self.s.call("review.show", {"proposal": c["id"]}, self.target, record=False)
        if not r.ok:
            return False, "; ".join(i.message for i in r.issues)
        o = r.output
        tags = sorted({t for ch in o["changes"] for t in ch["tags"]})
        if "status" in c and o["status"] != c["status"]:
            return False, f"statut {o['status']}"
        missing = [t for t in c.get("tags", []) if t not in tags]
        if missing:
            return False, f"étiquettes {tags}, manque {missing}"
        forbidden = [t for t in c.get("no_tags", []) if t in tags]
        if forbidden:
            return False, f"étiquettes interdites présentes : {forbidden}"
        return True, f"{c['id']} {o['status']} {tags}"

    def check_support(self, c: dict[str, Any]) -> tuple[bool, str]:
        w = self.world()
        try:
            rows = w.store.conn.execute("SELECT fact_key FROM supports").fetchall()
        finally:
            w.close()
        keys = {json.dumps(json.loads(k)) for (k,) in rows}
        wanted = json.dumps(c["key"])
        ok = (wanted in keys) == c.get("present", True)
        return ok, ("soutenu" if wanted in keys else "sans support")

    def check_signal(self, c: dict[str, Any]) -> tuple[bool, str]:
        r = self.s.call("state.check", {k: c[k] for k in ("branch", "point") if k in c}, self.target, record=False)
        found = [i for i in r.issues if i.code == c["code"] and ("path" not in c or i.path == c["path"])
                 and ("rule" not in c or i.rule == c["rule"])]
        want = c.get("present", True)
        return bool(found) == want, (f"{len(found)} signalement(s) {c['code']}" if found else f"aucun {c['code']}")

    def check_page(self, c: dict[str, Any]) -> tuple[bool, str]:
        params = {"entity": c["entity"], "filter": c.get("filter", "author"),
                  **{k: c[k] for k in ("branch", "point") if k in c}}
        r = self.s.call("wiki.page", params, self.target, record=False)
        if not r.ok:
            return c.get("exists", True) is False, "; ".join(i.message for i in r.issues)
        text = r.output["markdown"]
        missing = [t for t in c.get("contains", []) if t not in text]
        present = [t for t in c.get("absent", []) if t in text]
        if missing or present:
            return False, f"manque {missing}, présent à tort {present}"
        return True, "page conforme"

    def check_branch(self, c: dict[str, Any]) -> tuple[bool, str]:
        w = self.world()
        try:
            status = w.store.branch_status(c["id"])
            ref = w.reference_branch
        finally:
            w.close()
        if "status" in c and status != c["status"]:
            return False, f"statut {status}"
        if "reference" in c and (ref == c["id"]) != c["reference"]:
            return False, f"branche de référence : {ref}"
        return True, f"{c['id']} {status}{' (référence)' if ref == c['id'] else ''}"

    def check_step(self, c: dict[str, Any]) -> tuple[bool, str]:
        index = c.get("step", len(self.steps)) - 1
        step = self.steps[index]
        call = step["calls"][c.get("call", -1)] if step["calls"] else None
        if call is None:
            return False, "étape sans appel"
        if "status" in c and call["status"] != c["status"]:
            return False, f"statut {call['status']}"
        if "rule" in c and not any(i["rule"] == c["rule"] for i in call["issues"]):
            return False, f"aucun signalement {c['rule']}"
        if "path" in c:
            value = _get(call, c["path"])
            if "equals" in c and value != c["equals"]:
                return False, f"{value!r} ≠ {c['equals']!r}"
            if "contains" in c and c["contains"] not in value:
                return False, f"{c['contains']!r} absent de {value!r}"
        return True, f"étape {index + 1} : {call['op']} → {call['status']}"

    def check_call(self, c: dict[str, Any]) -> tuple[bool, str]:
        r = self.s.call(c["op"], c.get("params", {}), self.target, record=False)
        value = _get(r.model_dump(mode="json"), c.get("path"))
        if "equals" in c and value != c["equals"]:
            return False, f"{value!r} ≠ {c['equals']!r}"
        if "contains" in c and c["contains"] not in value:
            return False, f"{c['contains']!r} absent"
        return True, f"{c['op']} : {value!r}"[:200]

    # --- un parcours ---

    def run(self, w: dict[str, Any], with_checks: bool) -> dict[str, Any]:
        self.steps = []
        for spec in w.get("steps", []) or []:
            self.steps.append(self.step(spec))
        expects = []
        for e in w.get("expect", []) or []:
            if isinstance(e, str) or not with_checks:
                expects.append({"text": e if isinstance(e, str) else e.get("text", ""), "status": "unstructured",
                                "checks": []})
                continue
            results = []
            for c in e.get("checks", []):
                ok, detail = self.check(c)
                results.append({"check": c, "ok": ok, "detail": detail})
            status = "unstructured" if not results else "passed" if all(r["ok"] for r in results) else "failed"
            expects.append({"text": e.get("text", ""), "status": status, "checks": results})
        return {"id": w["id"], "title": w.get("title", ""), "milestone": w.get("milestone"),
                "steps": self.steps, "expects": expects,
                "steps_ok": all(s["ok"] for s in self.steps),
                "passed": sum(1 for e in expects if e["status"] == "passed"),
                "failed": sum(1 for e in expects if e["status"] == "failed"),
                "unstructured": sum(1 for e in expects if e["status"] == "unstructured")}


class WalkthroughList(Params):
    corpus: str = CORPUS


@operation("walkthrough.list", "read", WalkthroughList, "parcours d'acceptation : prérequis, étapes, attendus structurés",
           ("I-ACC-01",), needs_world=False)
def walkthrough_list(ctx: Context, p: WalkthroughList) -> Output:
    wts = load_walkthroughs(p.corpus)
    out = []
    for wid, w in wts.items():
        expects = w.get("expect", []) or []
        verbs = {s["do"] for s in w.get("steps", []) or []}
        executable = all(hasattr(Runner, f"do_{v}") for v in verbs) and not any(
            "decisions" in s and any(isinstance(d, dict) and "proposal" in d and "/" in str(d["proposal"])
                                     for d in s["decisions"]) for s in w.get("steps", []) or [])
        out.append({"id": wid, "title": w.get("title"), "milestone": w.get("milestone"),
                    "requires": w.get("requires", []), "steps": len(w.get("steps", []) or []),
                    "expects": len(expects), "structured": sum(1 for e in expects if isinstance(e, dict)),
                    "executable": executable})
    return Output(out, [], {"walkthroughs": len(out), "executable": sum(1 for w in out if w["executable"]),
                            "structured": sum(1 for w in out if w["structured"])})


class WalkthroughRun(Params):
    id: str
    corpus: str = CORPUS
    keep: bool = Field(True, description="garder le monde d'acceptation (consultable comme un bac)")


@operation("walkthrough.run", "admin", WalkthroughRun,
           "exécuter un parcours et ses prérequis dans un monde d'acceptation neuf, attendus vérifiés",
           ("I-ACC-01",), needs_world=False, example={"id": "W15"})
def walkthrough_run(ctx: Context, p: WalkthroughRun) -> Output:
    wts = load_walkthroughs(p.corpus)
    order = chain_of(wts, p.id)
    box = ctx.session.create_acceptance(Path(p.corpus) / "valmont" / "world.yaml", p.id)
    runner = Runner(ctx.session, p.corpus, box.target)
    results = []
    for i, wid in enumerate(order):
        ctx.report(wid, {"done": i, "total": len(order)})
        results.append(runner.run(wts[wid], with_checks=(wid == p.id)))
    target = results[-1]
    broken = [r["id"] for r in results if not r["steps_ok"]]
    issues = [Issue(IssueCode.EDIT_RULE, f"{r['id']} : étape {i + 1} ({s['do']}) en échec — {s['detail']}", "I-ACC-01")
              for r in results for i, s in enumerate(r["steps"]) if not s["ok"]]
    issues += [Issue(IssueCode.EDIT_RULE, f"{p.id} : attendu non tenu — {e['text']}", "I-ACC-01")
               for e in target["expects"] if e["status"] == "failed"]
    if not p.keep:
        ctx.session.drop_sandbox(box.id)
    status = "refused" if broken or target["failed"] else "ok"
    return Output({"walkthrough": p.id, "chain": order, "sandbox": box.id if p.keep else None, "results": results},
                  issues, {"chain": len(order), "passed": target["passed"], "failed": target["failed"],
                           "unstructured": target["unstructured"], "broken_steps": len(issues) - target["failed"]},
                  status=status)


__all__ = ["Runner", "chain_of", "load_walkthroughs"]
_ = Severity
