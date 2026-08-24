"""Git-history maintenance analyzer."""

from __future__ import annotations

from datetime import datetime, timedelta

from ..models import AnalyzerMetadata, AnalyzerResult, Category, Completeness, SourceKind
from ._shared import (
    is_rule_enabled,
    make_finding,
    make_limitation,
    make_metric,
    make_result,
)
from .base import AnalysisContext, Applicability


def _age_days(observed_at: datetime, value: datetime) -> int:
    return max(int((observed_at - value).total_seconds() // 86_400), 0)


class MaintenanceAnalyzer:
    metadata = AnalyzerMetadata(
        id="maintenance",
        version="1.0.0",
        category=Category.MAINTENANCE,
        rule_ids=tuple(f"RI-HIST-{index:03}" for index in range(1, 6)),
        capabilities=("git-history", "clock"),
    )

    def applies(self, context: AnalysisContext) -> Applicability:
        summary = context.git_history.summary
        if not summary.available:
            return Applicability(
                True,
                Completeness.UNAVAILABLE,
                summary.limitations or ("Git metadata or history is unavailable",),
            )
        if summary.completeness is Completeness.PARTIAL:
            return Applicability(
                True,
                Completeness.PARTIAL,
                summary.limitations or ("Reachable Git history is incomplete",),
            )
        return Applicability(True, Completeness.AVAILABLE)

    def analyze(self, context: AnalysisContext) -> AnalyzerResult:
        applicability = self.applies(context)
        history = context.git_history
        summary = history.summary
        available = summary.available
        first = summary.first_commit_at if available else None
        latest = summary.latest_commit_at if available else None
        repository_age = _age_days(context.observed_at, first) if first is not None else None
        newest_age = _age_days(context.observed_at, latest) if latest is not None else None
        window_start = context.observed_at - timedelta(
            days=context.config.thresholds.activity_window_days
        )
        recent_commits = (
            sum(
                window_start <= commit.authored_at <= context.observed_at
                for commit in history.commits
            )
            if available
            else None
        )

        findings = []
        if (
            available
            and latest is not None
            and latest < context.observed_at - timedelta(days=context.config.thresholds.stale_days)
            and is_rule_enabled(context.config, "RI-HIST-001")
        ):
            findings.append(
                make_finding(
                    self.metadata,
                    "RI-HIST-001",
                    evidence=f"newest reachable commit age: {newest_age} days",
                )
            )
        if (
            available
            and repository_age is not None
            and recent_commits is not None
            and repository_age >= context.config.thresholds.activity_window_days
            and recent_commits < context.config.thresholds.activity_min_commits
            and is_rule_enabled(context.config, "RI-HIST-002")
        ):
            findings.append(
                make_finding(
                    self.metadata,
                    "RI-HIST-002",
                    evidence=(
                        "commits in inclusive "
                        f"{context.config.thresholds.activity_window_days}-day "
                        f"window: {recent_commits}"
                    ),
                )
            )
        if (
            available
            and repository_age is not None
            and repository_age >= context.config.thresholds.single_contributor_min_age_days
            and summary.contributor_count == 1
            and is_rule_enabled(context.config, "RI-HIST-003")
        ):
            findings.append(
                make_finding(
                    self.metadata,
                    "RI-HIST-003",
                    evidence=(
                        f"reachable contributor count: 1; repository age: {repository_age} days"
                    ),
                )
            )
        if (
            available
            and summary.completeness is Completeness.PARTIAL
            and context.source_kind is SourceKind.GITHUB
            and is_rule_enabled(context.config, "RI-HIST-004")
        ):
            findings.append(
                make_finding(
                    self.metadata,
                    "RI-HIST-004",
                    evidence="remote reachable Git history completeness: partial",
                )
            )
        if not available and is_rule_enabled(context.config, "RI-HIST-005"):
            findings.append(
                make_finding(
                    self.metadata,
                    "RI-HIST-005",
                    evidence="Git metadata or reachable history available: false",
                )
            )

        evidence_completeness = summary.completeness
        evidence_limitations = summary.limitations
        metrics = [
            make_metric(
                self.metadata,
                "maintenance.git_available",
                True if available else None,
                unit=None,
                provenance="Contained reachable Git summary",
                completeness=evidence_completeness,
                limitations=evidence_limitations,
            ),
            make_metric(
                self.metadata,
                "maintenance.history_completeness",
                summary.completeness.value,
                unit=None,
                provenance="Git acquisition and shallow-history state",
                completeness=Completeness.AVAILABLE,
                limitations=summary.limitations,
            ),
            make_metric(
                self.metadata,
                "maintenance.repository_age_days",
                repository_age,
                unit="days",
                provenance="Injected observation time minus first reachable commit time",
                completeness=evidence_completeness,
                limitations=evidence_limitations,
            ),
            make_metric(
                self.metadata,
                "maintenance.newest_commit_age_days",
                newest_age,
                unit="days",
                provenance="Injected observation time minus newest reachable commit time",
                completeness=evidence_completeness,
                limitations=evidence_limitations,
            ),
            make_metric(
                self.metadata,
                "maintenance.commits_in_activity_window",
                recent_commits,
                unit="count",
                provenance="Reachable commits in the inclusive configured activity window",
                completeness=evidence_completeness,
                limitations=evidence_limitations,
            ),
            make_metric(
                self.metadata,
                "maintenance.contributor_count",
                summary.contributor_count if available else None,
                unit="count",
                provenance="Normalized contributor identities in reachable Git history",
                completeness=evidence_completeness,
                limitations=evidence_limitations,
            ),
        ]
        limitations = tuple(
            make_limitation(self.metadata, "git-history-evidence", message)
            for message in applicability.limitations
        )
        return make_result(
            self.metadata,
            applicability.completeness,
            metrics=metrics,
            findings=findings,
            limitations=limitations,
        )


ANALYZER = MaintenanceAnalyzer()

__all__ = ["ANALYZER", "MaintenanceAnalyzer"]
