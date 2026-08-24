from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from repoinsight.analyzers.base import AnalysisContext, Analyzer, run_analyzers
from repoinsight.analyzers.registry import BUILTIN_ANALYZERS
from repoinsight.application import AnalyzeService
from repoinsight.exit_codes import ExitCode
from repoinsight.models import AnalysisRequest, AnalyzerState, OutputFormat

FIXED_NOW = datetime(2026, 8, 24, 12, 0, tzinfo=UTC)
RAW_SECRET = "ghp_" + "abcdefghijklmnopqrstuvwxyz1234567890"


class ConstantMonotonic:
    def __call__(self) -> float:
        return 100.0


class RaisingAnalyzer:
    def __init__(self, wrapped: Analyzer) -> None:
        self.metadata = wrapped.metadata

    def applies(self, context):  # type: ignore[no-untyped-def]
        raise RuntimeError(f"repository-controlled {RAW_SECRET}")

    def analyze(self, context):  # type: ignore[no-untyped-def]
        raise AssertionError("unreachable")


def _request(root: Path, **overrides: object) -> AnalysisRequest:
    return AnalysisRequest(
        source=str(root),
        output_directory=root.parent / "reports",
        formats=(OutputFormat.JSON, OutputFormat.HTML),
        cli_overrides=overrides,
    )


def test_local_analysis_is_deterministic_with_injected_time(tmp_path: Path) -> None:
    root = tmp_path / "repository"
    root.mkdir()
    (root / "app.py").write_text("def hello():\n    return 'hello'\n", encoding="utf-8")
    service = AnalyzeService(now=lambda: FIXED_NOW, monotonic=ConstantMonotonic())

    first = service.analyze(_request(root))
    second = service.analyze(_request(root))

    assert first.report == second.report
    assert first.output_paths == (
        root.parent / "reports" / "repoinsight-report.json",
        root.parent / "reports" / "repoinsight-report.html",
    )
    assert first.exit_code is ExitCode.SUCCESS
    assert first.report.source.identity == str(root.resolve())
    assert first.report.run.elapsed_seconds == 0.0
    assert len(first.report.analyzer_status) == 6
    assert first.report.scorecard.overall_score is not None


def test_analyzer_failure_is_isolated_and_redacted_in_partial_report(tmp_path: Path) -> None:
    root = tmp_path / "repository"
    root.mkdir()
    (root / "app.py").write_text("value = 1\n", encoding="utf-8")
    analyzers = list(BUILTIN_ANALYZERS)
    analyzers[0] = RaisingAnalyzer(analyzers[0])
    service = AnalyzeService(
        analyzers=tuple(analyzers),
        now=lambda: FIXED_NOW,
        monotonic=ConstantMonotonic(),
    )

    outcome = service.analyze(_request(root))
    serialized = outcome.report.model_dump_json()
    failed = next(
        item for item in outcome.report.analyzer_status if item.analyzer_id == "maintainability"
    )

    assert failed.state is AnalyzerState.FAILED
    assert outcome.report.completeness.value == "partial"
    assert RAW_SECRET not in serialized
    assert outcome.exit_code is ExitCode.SUCCESS


def test_fail_under_uses_distinct_exit_code_and_equal_boundary_passes(tmp_path: Path) -> None:
    root = tmp_path / "repository"
    root.mkdir()
    (root / "app.py").write_text("value = 1\n", encoding="utf-8")
    service = AnalyzeService(now=lambda: FIXED_NOW, monotonic=ConstantMonotonic())
    baseline = service.analyze(_request(root))
    assert baseline.report.scorecard.overall_score is not None
    score = baseline.report.scorecard.overall_score

    equal = service.analyze(_request(root, **{"ci.fail_under": score}))
    below = service.analyze(_request(root, **{"ci.fail_under": min(score + 0.1, 100)}))

    assert equal.exit_code is ExitCode.SUCCESS
    assert below.exit_code is ExitCode.THRESHOLD_FAILED


def test_analysis_deadline_skips_remaining_analyzers(
    context_factory: Callable[..., AnalysisContext],
) -> None:
    context: AnalysisContext = context_factory({"app.py": "value = 1\n"})

    results = run_analyzers(context, monotonic=lambda: 2.0, deadline=1.0)

    assert len(results) == 6
    assert all(item.status.state is AnalyzerState.SKIPPED for item in results)
    assert all(item.status.message == "Analysis deadline reached" for item in results)
