from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import pytest

from repoinsight.analyzers.base import AnalysisContext
from repoinsight.analyzers.catalog import RULE_CATALOG
from repoinsight.analyzers.maintenance import ANALYZER
from repoinsight.git import GitCommit, GitHistory
from repoinsight.models import (
    AnalyzerResult,
    Completeness,
    Finding,
    GitSummary,
    Metric,
    Severity,
    SourceKind,
)

ContextFactory = Callable[..., AnalysisContext]
OBSERVED = datetime(2026, 8, 24, 12, 0, tzinfo=UTC)


def _history(
    authored_at: tuple[datetime, ...],
    *,
    completeness: Completeness = Completeness.AVAILABLE,
    contributor_count: int = 1,
) -> GitHistory:
    commits = tuple(
        GitCommit(
            revision=f"{index + 1:040x}",
            authored_at=value,
            author_identity=f"author-{index % max(contributor_count, 1)}",
        )
        for index, value in enumerate(authored_at)
    )
    return GitHistory(
        summary=GitSummary(
            available=True,
            completeness=completeness,
            head_revision=commits[-1].revision,
            branch="main",
            commits_considered=len(commits),
            contributor_count=contributor_count,
            first_commit_at=min(authored_at),
            latest_commit_at=max(authored_at),
            limitations=("History is bounded",) if completeness is Completeness.PARTIAL else (),
        ),
        commits=commits,
    )


def _unavailable_history() -> GitHistory:
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
            limitations=("Git metadata unavailable",),
        ),
        commits=(),
    )


def _findings(result: AnalyzerResult, rule_id: str) -> list[Finding]:
    return [finding for finding in result.findings if finding.rule_id == rule_id]


def _metrics(result: AnalyzerResult) -> dict[str, Metric]:
    return {metric.id: metric for metric in result.metrics}


@pytest.mark.parametrize(
    ("age_days", "triggered"),
    [
        pytest.param(364, False, id="newer"),
        pytest.param(365, False, id="exact-cutoff"),
        pytest.param(366, True, id="strictly-older"),
    ],
)
def test_stale_history_uses_strict_365_day_cutoff(
    context_factory: ContextFactory,
    age_days: int,
    triggered: bool,
) -> None:
    result = ANALYZER.analyze(
        context_factory(
            git_history=_history((OBSERVED - timedelta(days=age_days),)),
            observed_at=OBSERVED,
        )
    )

    assert bool(_findings(result, "RI-HIST-001")) is triggered
    assert _metrics(result)["maintenance.newest_commit_age_days"].value == age_days


def test_activity_window_is_inclusive_and_future_commits_are_ignored(
    context_factory: ContextFactory,
) -> None:
    lower = OBSERVED - timedelta(days=180)
    low_activity = ANALYZER.analyze(
        context_factory(
            git_history=_history((lower, OBSERVED + timedelta(days=1)), contributor_count=2),
            observed_at=OBSERVED,
        )
    )
    assert len(_findings(low_activity, "RI-HIST-002")) == 1
    assert _metrics(low_activity)["maintenance.commits_in_activity_window"].value == 1
    assert _metrics(low_activity)["maintenance.newest_commit_age_days"].value == 0

    enough_activity = ANALYZER.analyze(
        context_factory(
            git_history=_history((lower, OBSERVED), contributor_count=2),
            observed_at=OBSERVED,
        )
    )
    assert _findings(enough_activity, "RI-HIST-002") == []
    assert _metrics(enough_activity)["maintenance.commits_in_activity_window"].value == 2


@pytest.mark.parametrize(
    ("age_days", "triggered"),
    [pytest.param(179, False, id="below"), pytest.param(180, True, id="exact")],
)
def test_single_contributor_rule_uses_inclusive_repository_age_boundary(
    context_factory: ContextFactory,
    age_days: int,
    triggered: bool,
) -> None:
    result = ANALYZER.analyze(
        context_factory(
            git_history=_history((OBSERVED - timedelta(days=age_days),)),
            observed_at=OBSERVED,
        )
    )
    assert bool(_findings(result, "RI-HIST-003")) is triggered


def test_partial_history_limitation_is_remote_only_and_zero_impact(
    context_factory: ContextFactory,
) -> None:
    partial = _history((OBSERVED - timedelta(days=10),), completeness=Completeness.PARTIAL)
    remote = ANALYZER.analyze(
        context_factory(
            git_history=partial,
            source_kind=SourceKind.GITHUB,
            observed_at=OBSERVED,
        )
    )
    local = ANALYZER.analyze(
        context_factory(
            git_history=partial,
            source_kind=SourceKind.LOCAL,
            observed_at=OBSERVED,
        )
    )

    finding = _findings(remote, "RI-HIST-004")[0]
    assert finding.severity is Severity.INFO
    assert finding.score_impact == 0.0
    assert "limitation" in finding.limitations[0].casefold()
    assert _findings(local, "RI-HIST-004") == []


def test_unavailable_git_emits_zero_impact_finding_and_null_evidence_metrics(
    context_factory: ContextFactory,
) -> None:
    result = ANALYZER.analyze(
        context_factory(git_history=_unavailable_history(), observed_at=OBSERVED)
    )
    finding = _findings(result, "RI-HIST-005")[0]
    metrics = _metrics(result)

    assert finding.severity is Severity.INFO
    assert finding.score_impact == 0.0
    assert result.status.completeness is Completeness.UNAVAILABLE
    assert metrics["maintenance.git_available"].value is None
    assert metrics["maintenance.git_available"].completeness is Completeness.UNAVAILABLE
    assert metrics["maintenance.repository_age_days"].value is None
    assert metrics["maintenance.history_completeness"].value == "unavailable"


def test_maintenance_disabled_rule_metrics_catalog_and_stable_order(
    context_factory: ContextFactory,
) -> None:
    result = ANALYZER.analyze(
        context_factory(
            git_history=_unavailable_history(),
            observed_at=OBSERVED,
            config_overrides={"rules": {"disabled": ["RI-HIST-005"]}},
        )
    )
    assert _findings(result, "RI-HIST-005") == []
    expected_ids = {
        "maintenance.git_available",
        "maintenance.history_completeness",
        "maintenance.repository_age_days",
        "maintenance.newest_commit_age_days",
        "maintenance.commits_in_activity_window",
        "maintenance.contributor_count",
    }
    assert [metric.id for metric in result.metrics] == sorted(expected_ids)
    assert all(
        metric.provenance and metric.analyzer_id == "maintenance" for metric in result.metrics
    )
    assert [finding.rule_id for finding in result.findings] == sorted(
        finding.rule_id for finding in result.findings
    )
    catalog = {rule.id: rule for rule in RULE_CATALOG}
    for finding in result.findings:
        rule = catalog[finding.rule_id]
        assert finding.title == rule.title
        assert finding.remediation == rule.remediation
        assert finding.limitations[0] == rule.limitations
