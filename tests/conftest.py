from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest

from repoinsight.analyzers.base import AnalysisContext
from repoinsight.config import load_config
from repoinsight.git import GitHistory
from repoinsight.inventory import InventoryResult, build_inventory
from repoinsight.models import Completeness, GitSummary, SourceKind
from repoinsight.python_index import PythonIndex, build_python_index

ContextFactory = Callable[..., AnalysisContext]


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--benchmark-target",
        action="store_true",
        default=False,
        help="run and enforce the opt-in 100,000-line performance target",
    )


def unavailable_git() -> GitHistory:
    return GitHistory(
        summary=GitSummary(
            available=False,
            completeness=Completeness.UNAVAILABLE,
            head_revision=None,
            branch=None,
            commits_considered=0,
            contributor_count=0,
            first_commit_at=None,
            latest_commit_at=None,
            limitations=("Git history unavailable in test context",),
        ),
        commits=(),
    )


@pytest.fixture
def context_factory(tmp_path: Path) -> ContextFactory:
    sequence = 0

    def make_context(
        files: Mapping[str, str] | None = None,
        *,
        config_overrides: Mapping[str, object] | None = None,
        inventory_completeness: Completeness | None = None,
        index_completeness: Completeness | None = None,
        git_history: GitHistory | None = None,
        source_kind: SourceKind = SourceKind.LOCAL,
        observed_at: datetime = datetime(2026, 8, 24, 12, 0, tzinfo=UTC),
    ) -> AnalysisContext:
        nonlocal sequence
        sequence += 1
        root = tmp_path / f"repo-{sequence}"
        root.mkdir()
        for relative, text in (files or {}).items():
            path = root / Path(relative)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8", newline="\n")
        config = load_config(root, None, config_overrides or {})
        inventory: InventoryResult = build_inventory(root, config)
        if inventory_completeness is not None:
            inventory = replace(inventory, completeness=inventory_completeness)
        python_index: PythonIndex = build_python_index(inventory)
        if index_completeness is not None:
            python_index = replace(python_index, completeness=index_completeness)
        return AnalysisContext(
            inventory=inventory,
            python_index=python_index,
            git_history=git_history or unavailable_git(),
            config=config,
            source_kind=source_kind,
            observed_at=observed_at,
        )

    return make_context
