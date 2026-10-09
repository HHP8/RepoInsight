from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import pytest

from repoinsight.models import (
    AnalysisReport,
    AnalyzerState,
    AnalyzerStatus,
    Category,
    CategoryScoreTrace,
    Completeness,
    Finding,
    GitSummary,
    Location,
    RepositoryInventory,
    RunMetadata,
    Scorecard,
    SourceKind,
    SourceMetadata,
    ToolMetadata,
)
from repoinsight.reporting.json_report import serialize_json

ReportFactory = Callable[..., Path]


def finding(**changes: object) -> Finding:
    values: dict[str, object] = {
        "rule_id": "RI-MAINT-001",
        "analyzer_id": "maintainability",
        "analyzer_version": "1.0.0",
        "category": "maintainability",
        "severity": "medium",
        "title": "Synthetic finding",
        "explanation": "Static evidence",
        "location": {"path": "src/app.py", "start_line": 3},
        "evidence": "Synthetic evidence",
        "remediation": "Review behavior",
        "score_impact": 5,
        "confidence": "high",
    }
    values.update(changes)
    return Finding.model_validate(values, strict=False)


@pytest.fixture
def report_factory(tmp_path: Path) -> ReportFactory:
    sequence = 0

    def create(*, findings: tuple[Finding, ...] = (), **updates: object) -> Path:
        nonlocal sequence
        sequence += 1
        report = AnalysisReport(
            schema_version="1.0",
            score_contract_version="1.0",
            tool=ToolMetadata(
                name="RepoInsight",
                version="1.1.0",
                schema_version="1.0",
                score_contract_version="1.0",
            ),
            run=RunMetadata(generated_at=datetime(2026, 10, 8, tzinfo=UTC), elapsed_seconds=0),
            source=SourceMetadata(
                kind=SourceKind.LOCAL,
                identity="synthetic",
                revision=None,
                history_completeness=Completeness.AVAILABLE,
            ),
            configuration_fingerprint="0" * 64,
            completeness=Completeness.AVAILABLE,
            inventory=RepositoryInventory(
                total_files=0,
                python_files=0,
                test_files=0,
                total_bytes=0,
                source_bytes=0,
                python_lines=0,
            ),
            metrics=(),
            findings=findings,
            scorecard=Scorecard(
                categories=tuple(
                    CategoryScoreTrace(
                        category=c,
                        baseline=100,
                        score=100,
                        weight=1,
                        completeness=Completeness.AVAILABLE,
                        impacts=(),
                        limitations=(),
                    )
                    for c in Category
                ),
                overall_score=100,
                rating="Excellent",
                available_weight=6,
                rounding="one decimal",
            ),
            git=GitSummary(
                available=False,
                completeness=Completeness.UNAVAILABLE,
                head_revision=None,
                branch=None,
                commits_considered=0,
                contributor_count=0,
                first_commit_at=None,
                latest_commit_at=None,
            ),
            skipped_inputs=(),
            warnings=(),
            limitations=(),
            analyzer_status=(
                AnalyzerStatus(
                    analyzer_id="maintainability",
                    state=AnalyzerState.SUCCEEDED,
                    completeness=Completeness.AVAILABLE,
                    elapsed_seconds=0,
                ),
            ),
        ).model_copy(update=updates)
        path = tmp_path / f"report-{sequence}.json"
        path.write_bytes(serialize_json(report))
        return path

    return create


__all__ = ["Location", "ReportFactory", "finding"]
