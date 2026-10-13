"""Profils de modèles vus et choisis depuis l'interface (I-LLM-02) : `llm.profiles` les liste avec le routage
effectif par tâche ; `llm.route` fixe le profil par défaut des tâches dans `worldkit-llm.yaml` (T-LLM-01).

Le choix par défaut vit dans le fichier, pas dans le navigateur : la ligne de commande et l'interface lisent le
même. Chaque lancement qui appelle un modèle peut encore prendre un autre profil pour lui seul (`profile`).
"""

from __future__ import annotations

from pydantic import Field

from worldkit.core.schema import Issue, IssueCode

from .registry import Output, Params, operation
from .session import Context


class LLMProfiles(Params):
    llm_config: str | None = None


def _describe(config) -> dict:
    from worldkit.periphery.llm import routing
    return {"profiles": [{"name": p.name, "adapter": p.adapter, "model": p.model, "signature": p.signature}
                         for p in sorted(config.profiles.values(), key=lambda p: p.name)],
            "tasks": routing(config)}


@operation("llm.profiles", "read", LLMProfiles, "profils de modèles et profil effectif de chaque tâche",
           ("T-LLM-01", "I-LLM-02"), needs_world=False)
def llm_profiles(ctx: Context, p: LLMProfiles) -> Output:
    from worldkit.periphery.llm import LLMError, load_config
    try:
        config = load_config(p.llm_config)
    except LLMError as e:
        return Output(None, [Issue(IssueCode.EDIT_RULE, str(e), "T-LLM-01")])
    out = _describe(config)
    return Output(out, [], {"profiles": len(out["profiles"])})


class LLMRoute(Params):
    profile: str = Field(description="profil à donner aux tâches")
    tasks: list[str] | None = Field(None, description="tâches visées (défaut : toutes : extraction, mentions, "
                                                       "facts, notes)")
    llm_config: str | None = None


@operation("llm.route", "admin", LLMRoute, "fixer le profil par défaut des tâches (worldkit-llm.yaml)",
           ("T-LLM-01", "I-LLM-02"), needs_world=False, example={"profile": "qwen3-4b"})
def llm_route(ctx: Context, p: LLMRoute) -> Output:
    from worldkit.periphery.llm import TASKS, LLMError, write_routing
    try:
        config = write_routing({t: p.profile for t in (p.tasks or TASKS)}, p.llm_config)
    except LLMError as e:
        return Output(None, [Issue(IssueCode.EDIT_RULE, str(e), "I-LLM-02")])
    return Output(_describe(config), [], {"tasks": len(p.tasks or TASKS)})
