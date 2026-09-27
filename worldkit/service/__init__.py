"""Couche de service (cadre d'interface §8, jalon I1) : opérations nommées, résultats de forme commune,
exécutions enregistrées, bacs à sable. L'interface, la ligne de commande et les tests passent par elle."""

from . import ops as _ops  # noqa: F401 — enregistre les opérations
from . import pipeline as _pipeline  # noqa: F401 — opérations du pipeline (I4)
from .registry import REGISTRY, Operation, Output, Params, describe
from .result import IssueView, Result
from .session import WORLD, Session, parse_target

__all__ = ["REGISTRY", "IssueView", "Operation", "Output", "Params", "Result", "Session", "WORLD", "describe",
           "parse_target"]
