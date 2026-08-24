from __future__ import annotations

import ast
from collections.abc import Callable
from dataclasses import FrozenInstanceError, replace

import pytest

from repoinsight.analyzers.base import AnalysisContext, Applicability, run_analyzers
from repoinsight.analyzers.registry import BUILTIN_ANALYZERS, validate_registry
from repoinsight.models import (
    AnalyzerMetadata,
    AnalyzerResult,
    AnalyzerState,
    AnalyzerStatus,
    Category,
    Completeness,
)

ContextFactory = Callable[..., AnalysisContext]

EXPECTED_REGISTRY = (
    (
        "maintainability",
        Category.MAINTAINABILITY,
        ("python-ast", "python-tokens", "static-reference-index"),
        9,
    ),
    (
        "testing",
        Category.TESTING,
        ("inventory", "static-manifest-text", "static-ci-text"),
        6,
    ),
    (
        "documentation",
        Category.DOCUMENTATION,
        ("inventory", "python-ast", "readme-text"),
        6,
    ),
    (
        "security-hygiene",
        Category.SECURITY_HYGIENE,
        ("inventory", "python-ast", "static-manifest-text", "redaction"),
        7,
    ),
    (
        "repository-hygiene",
        Category.REPOSITORY_HYGIENE,
        ("inventory", "static-metadata-text"),
        8,
    ),
    ("maintenance", Category.MAINTENANCE, ("git-history", "clock"), 5),
)


class StubAnalyzer:
    def __init__(
        self,
        metadata: AnalyzerMetadata,
        *,
        applicability: Applicability | None = None,
        failure: BaseException | None = None,
    ) -> None:
        self.metadata = metadata
        self._applicability = applicability or Applicability(True, Completeness.AVAILABLE)
        self._failure = failure
        self.analyze_calls = 0

    def applies(self, context: AnalysisContext) -> Applicability:
        del context
        return self._applicability

    def analyze(self, context: AnalysisContext) -> AnalyzerResult:
        del context
        self.analyze_calls += 1
        if self._failure is not None:
            raise self._failure
        return AnalyzerResult(
            metadata=self.metadata,
            status=AnalyzerStatus(
                analyzer_id=self.metadata.id,
                state=AnalyzerState.SUCCEEDED,
                completeness=Completeness.AVAILABLE,
                elapsed_seconds=999.0,
            ),
        )


def _stubs() -> tuple[StubAnalyzer, ...]:
    return tuple(StubAnalyzer(analyzer.metadata) for analyzer in BUILTIN_ANALYZERS)


def test_registry_has_exact_six_analyzers_metadata_capabilities_and_rule_ownership() -> None:
    validate_registry(BUILTIN_ANALYZERS)

    observed = tuple(
        (
            analyzer.metadata.id,
            analyzer.metadata.category,
            analyzer.metadata.capabilities,
            len(analyzer.metadata.rule_ids),
        )
        for analyzer in BUILTIN_ANALYZERS
    )
    assert observed == EXPECTED_REGISTRY
    assert {analyzer.metadata.version for analyzer in BUILTIN_ANALYZERS} == {"1.0.0"}
    owned = tuple(
        rule_id for analyzer in BUILTIN_ANALYZERS for rule_id in analyzer.metadata.rule_ids
    )
    assert len(owned) == len(set(owned)) == 41


def test_registry_rejects_order_changes_and_duplicate_ownership() -> None:
    with pytest.raises(ValueError, match="order"):
        validate_registry(tuple(reversed(BUILTIN_ANALYZERS)))

    stubs = list(_stubs())
    duplicate = stubs[1].metadata.model_copy(
        update={"rule_ids": (*stubs[1].metadata.rule_ids, stubs[0].metadata.rule_ids[0])}
    )
    stubs[1] = StubAnalyzer(duplicate)
    with pytest.raises(ValueError, match="ownership"):
        validate_registry(tuple(stubs))


def test_registry_rejects_rule_swaps_that_preserve_unique_catalog_union() -> None:
    stubs = list(_stubs())
    maintainability_rule = stubs[0].metadata.rule_ids[-1]
    testing_rule = stubs[1].metadata.rule_ids[0]
    stubs[0] = StubAnalyzer(
        stubs[0].metadata.model_copy(
            update={"rule_ids": (*stubs[0].metadata.rule_ids[:-1], testing_rule)}
        )
    )
    stubs[1] = StubAnalyzer(
        stubs[1].metadata.model_copy(
            update={"rule_ids": (maintainability_rule, *stubs[1].metadata.rule_ids[1:])}
        )
    )

    with pytest.raises(ValueError, match="assignment"):
        validate_registry(tuple(stubs))


def test_analysis_context_is_frozen_and_requires_aware_time_at_execution(
    context_factory: ContextFactory,
) -> None:
    context = context_factory({"source.py": "value = 1\n"})
    with pytest.raises(FrozenInstanceError):
        context.source_kind = context.source_kind  # type: ignore[misc]

    naive = replace(context, observed_at=context.observed_at.replace(tzinfo=None))
    with pytest.raises(ValueError, match="timezone-aware"):
        run_analyzers(naive, _stubs())


def test_run_analyzers_skips_non_applicable_analyzer_without_calling_analyze(
    context_factory: ContextFactory,
) -> None:
    context = context_factory()
    analyzers = list(_stubs())
    skipped = StubAnalyzer(
        analyzers[0].metadata,
        applicability=Applicability(
            False,
            Completeness.UNAVAILABLE,
            ("No parsed Python evidence is available",),
        ),
    )
    analyzers[0] = skipped

    result = run_analyzers(context, tuple(analyzers), monotonic=lambda: 4.0)[0]

    assert skipped.analyze_calls == 0
    assert result.status.state is AnalyzerState.SKIPPED
    assert result.status.completeness is Completeness.UNAVAILABLE
    assert result.status.elapsed_seconds == 0.0
    assert [(item.code, item.message) for item in result.limitations] == [
        ("analyzer-not-applicable", "No parsed Python evidence is available")
    ]


def test_run_analyzers_replaces_timing_and_preserves_registry_order(
    context_factory: ContextFactory,
) -> None:
    context = context_factory()
    analyzers = _stubs()
    ticks = iter(
        [
            0.0,
            0.25,
            1.0,
            1.25,
            2.0,
            2.25,
            3.0,
            3.25,
            4.0,
            4.25,
            5.0,
            5.25,
        ]
    )

    results = run_analyzers(context, analyzers, monotonic=lambda: next(ticks))

    assert [result.metadata.id for result in results] == [item[0] for item in EXPECTED_REGISTRY]
    assert [result.status.elapsed_seconds for result in results] == [0.25] * 6


def test_run_analyzers_isolates_and_redacts_ordinary_exceptions(
    context_factory: ContextFactory,
) -> None:
    raw_secret = "sk-" + "proj-" + "abcdefghijklmnopqrstuv"
    context = context_factory()
    analyzers = list(_stubs())
    analyzers[2] = StubAnalyzer(analyzers[2].metadata, failure=ValueError(raw_secret))

    results = run_analyzers(context, tuple(analyzers), monotonic=lambda: 0.0)

    assert results[2].status.state is AnalyzerState.FAILED
    assert results[2].status.completeness is Completeness.UNAVAILABLE
    assert results[3].status.state is AnalyzerState.SUCCEEDED
    assert [(item.code, item.message) for item in results[2].limitations] == [
        ("analyzer-failure", "Analyzer failed during static analysis")
    ]
    assert raw_secret not in results[2].model_dump_json()


@pytest.mark.parametrize("failure", [KeyboardInterrupt(), SystemExit(2)])
def test_run_analyzers_propagates_control_flow_base_exceptions(
    context_factory: ContextFactory,
    failure: BaseException,
) -> None:
    context = context_factory()
    analyzers = list(_stubs())
    analyzers[0] = StubAnalyzer(analyzers[0].metadata, failure=failure)

    with pytest.raises(type(failure)):
        run_analyzers(context, tuple(analyzers), monotonic=lambda: 0.0)


def test_all_builtin_analyzers_leave_complete_asts_unchanged(
    context_factory: ContextFactory,
) -> None:
    context = context_factory(
        {
            "src/module.py": (
                "import os\n\n"
                "def public(value: int) -> int:\n"
                "    if value:\n"
                "        return os.getpid()\n"
                "    return 0\n"
            ),
            "tests/test_module.py": "from src.module import public\nassert public(0) == 0\n",
        }
    )
    before = tuple(
        ast.dump(parsed.tree, include_attributes=True) for parsed in context.python_index.files
    )

    run_analyzers(context, monotonic=lambda: 0.0)

    after = tuple(
        ast.dump(parsed.tree, include_attributes=True) for parsed in context.python_index.files
    )
    assert after == before


def test_all_builtin_analyzers_complete_without_internal_failure_and_emit_52_metrics(
    context_factory: ContextFactory,
) -> None:
    context = context_factory(
        {
            "README.md": (
                "## Overview\nProject.\n## Installation\n`pip install project`\n"
                "## Usage\n```python\nimport project\n```\n"
            ),
            "pyproject.toml": "[project]\nname='project'\ndependencies=['click==8.1.8']\n",
            "src/project.py": "def public():\n    return 1\n",
            "tests/test_project.py": "import pytest\nfrom src.project import public\n",
        }
    )

    results = run_analyzers(context, monotonic=lambda: 0.0)

    assert all(result.status.state is not AnalyzerState.FAILED for result in results)
    assert len(results) == 6
    assert sum(len(result.metrics) for result in results) == 52


def test_builtin_results_are_identical_when_file_creation_order_changes(
    context_factory: ContextFactory,
) -> None:
    files = {
        "z.py": "# TODO: review\ndef _unused():\n    return 1\n",
        "tests/test_z.py": "import unittest\n",
        "README.md": "# Project\n",
    }
    forward = context_factory(files)
    reverse = context_factory(dict(reversed(tuple(files.items()))))

    first = run_analyzers(forward, monotonic=lambda: 0.0)
    second = run_analyzers(reverse, monotonic=lambda: 0.0)

    assert [result.model_dump_json() for result in first] == [
        result.model_dump_json() for result in second
    ]
