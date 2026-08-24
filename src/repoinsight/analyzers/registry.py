"""Explicit version 1 analyzer registry."""

from __future__ import annotations

from collections.abc import Sequence

from ..models import Category
from .base import Analyzer
from .catalog import RULE_IDS
from .documentation import ANALYZER as DOCUMENTATION_ANALYZER
from .maintainability import ANALYZER as MAINTAINABILITY_ANALYZER
from .maintenance import ANALYZER as MAINTENANCE_ANALYZER
from .repository_hygiene import ANALYZER as REPOSITORY_HYGIENE_ANALYZER
from .security import ANALYZER as SECURITY_ANALYZER
from .testing import ANALYZER as TESTING_ANALYZER

BUILTIN_ANALYZERS: tuple[Analyzer, ...] = (
    MAINTAINABILITY_ANALYZER,
    TESTING_ANALYZER,
    DOCUMENTATION_ANALYZER,
    SECURITY_ANALYZER,
    REPOSITORY_HYGIENE_ANALYZER,
    MAINTENANCE_ANALYZER,
)

_EXPECTED = (
    (
        "maintainability",
        Category.MAINTAINABILITY,
        ("python-ast", "python-tokens", "static-reference-index"),
    ),
    (
        "testing",
        Category.TESTING,
        ("inventory", "static-manifest-text", "static-ci-text"),
    ),
    (
        "documentation",
        Category.DOCUMENTATION,
        ("inventory", "python-ast", "readme-text"),
    ),
    (
        "security-hygiene",
        Category.SECURITY_HYGIENE,
        ("inventory", "python-ast", "static-manifest-text", "redaction"),
    ),
    (
        "repository-hygiene",
        Category.REPOSITORY_HYGIENE,
        ("inventory", "static-metadata-text"),
    ),
    ("maintenance", Category.MAINTENANCE, ("git-history", "clock")),
)
_EXPECTED_RULE_IDS = (
    tuple(f"RI-MAINT-{index:03}" for index in range(1, 10)),
    tuple(f"RI-TEST-{index:03}" for index in range(1, 7)),
    tuple(f"RI-DOC-{index:03}" for index in range(1, 7)),
    tuple(f"RI-SEC-{index:03}" for index in range(1, 8)),
    tuple(f"RI-REPO-{index:03}" for index in range(1, 9)),
    tuple(f"RI-HIST-{index:03}" for index in range(1, 6)),
)


def validate_registry(analyzers: Sequence[Analyzer]) -> None:
    """Reject any registry drift from the six built-in version 1 analyzers."""
    observed = tuple(
        (item.metadata.id, item.metadata.category, item.metadata.capabilities) for item in analyzers
    )
    if observed != _EXPECTED:
        raise ValueError("analyzer registry order, categories, or capabilities do not match v1")
    if any(item.metadata.version != "1.0.0" for item in analyzers):
        raise ValueError("all analyzer versions must be 1.0.0")
    owned: list[str] = []
    for analyzer in analyzers:
        owned.extend(analyzer.metadata.rule_ids)
    if len(owned) != len(set(owned)):
        raise ValueError("analyzer rule ownership must be unique")
    if set(owned) != RULE_IDS:
        raise ValueError("analyzer rule ownership must exactly cover the v1 catalog")
    if tuple(item.metadata.rule_ids for item in analyzers) != _EXPECTED_RULE_IDS:
        raise ValueError("analyzer rule assignment must match the v1 category packs")


validate_registry(BUILTIN_ANALYZERS)

__all__ = ["BUILTIN_ANALYZERS", "validate_registry"]
