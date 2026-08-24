"""Explicit analyzer contracts, registry, and stable version 1 catalog."""

from .base import AnalysisContext, Analyzer, Applicability, run_analyzers
from .catalog import RULE_CATALOG, RULE_IDS
from .registry import BUILTIN_ANALYZERS, validate_registry

__all__ = [
    "BUILTIN_ANALYZERS",
    "RULE_CATALOG",
    "RULE_IDS",
    "AnalysisContext",
    "Analyzer",
    "Applicability",
    "run_analyzers",
    "validate_registry",
]
