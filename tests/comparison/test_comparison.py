from __future__ import annotations

import hashlib
import json

import pytest

from repoinsight.comparison import compare_reports
from repoinsight.errors import InvalidUsageError
from repoinsight.models import Completeness, Location
from repoinsight.reporting.comparison import serialize_comparison

from .conftest import ReportFactory, finding


def test_identical_reports_preserve_hashes_and_duplicate_counts(
    report_factory: ReportFactory,
) -> None:
    path = report_factory(findings=(finding(), finding(), finding(location=None)))
    raw = path.read_bytes()
    result = compare_reports(path, path)
    assert result.before.sha256 == result.after.sha256 == hashlib.sha256(raw).hexdigest()
    assert result.counts.unchanged == 3
    assert result.counts.new == result.counts.changed == result.counts.resolved == 0
    assert result.overall.delta == 0
    assert sum(item.count for item in result.findings) == 3
    assert serialize_comparison(result) == serialize_comparison(compare_reports(path, path))
    assert path.read_bytes() == raw


def test_add_remove_and_changed_attributes(report_factory: ReportFactory) -> None:
    before = report_factory(
        findings=(finding(), finding(location=Location(path="old.py", start_line=1)))
    )
    after = report_factory(
        findings=(
            finding(severity="high", confidence="low", score_impact=9, evidence="Changed"),
            finding(location=Location(path="new.py", start_line=1)),
        )
    )
    result = compare_reports(before, after)
    assert result.counts.new == result.counts.resolved == result.counts.changed == 1
    changed = next(x for x in result.findings if x.status == "changed")
    assert {"severity", "confidence", "score_impact", "evidence"} <= set(changed.changed_attributes)
    assert "Changed" not in serialize_comparison(result).decode()


def test_suppression_is_a_change_not_resolution(report_factory: ReportFactory) -> None:
    before = report_factory(findings=(finding(),))
    after = report_factory(
        findings=(finding(suppressed=True, suppression_reason="Synthetic waiver"),)
    )
    result = compare_reports(before, after)
    assert result.counts.changed == 1 and result.counts.resolved == 0
    assert "suppressed" in result.findings[0].changed_attributes
    assert result.findings[0].after is not None and result.findings[0].after.suppressed
    assert "suppression-is-not-a-fix" in result.warnings
    reverse = compare_reports(after, before)
    assert reverse.counts.changed == 1


def test_exact_first_multiset_pairing_is_order_independent(report_factory: ReportFactory) -> None:
    before = report_factory(findings=(finding(), finding(), finding(severity="low")))
    after = report_factory(findings=(finding(severity="high"), finding()))
    result = compare_reports(before, after)
    assert result.counts.unchanged == 1
    assert result.counts.changed == 1
    assert result.counts.resolved == 1
    assert all(x.ambiguous for x in result.findings)
    permuted = report_factory(findings=(finding(severity="low"), finding(), finding()))
    # Input hashes differ, comparison evidence must still have the same ordering/counts.
    assert result.findings == compare_reports(permuted, after).findings


@pytest.mark.parametrize(
    "change",
    [
        {"location": None},
        {"location": Location(path="src/renamed.py", start_line=3)},
        {"location": Location(path="src/app.py", start_line=4)},
        {"location": Location(path="src/App.py", start_line=3)},
        {"location": Location(path="src/app.py", start_line=3, end_line=5)},
        {"location": Location(path="src/app.py", start_line=3, start_column=1)},
        {"analyzer_id": "another-analyzer"},
    ],
)
def test_matching_has_no_fuzzy_path_line_case_or_analyzer_inference(
    report_factory: ReportFactory,
    change: dict[str, object],
) -> None:
    result = compare_reports(
        report_factory(findings=(finding(),)), report_factory(findings=(finding(**change),))
    )
    assert result.counts.changed == result.counts.unchanged == 0
    assert result.counts.new == 1
    assert result.counts.resolved + result.counts.no_longer_observed == 1


@pytest.mark.parametrize(
    "completeness", [Completeness.PARTIAL, Completeness.UNAVAILABLE, Completeness.SKIPPED]
)
def test_missing_under_partial_coverage_is_not_resolution(
    report_factory: ReportFactory,
    completeness: Completeness,
) -> None:
    result = compare_reports(
        report_factory(findings=(finding(),)), report_factory(completeness=completeness)
    )
    assert result.counts.no_longer_observed == 1 and result.counts.resolved == 0
    assert result.findings[0].uncertain
    assert not result.compatibility.scores_interpretable
    assert "partial-or-unavailable-coverage" in result.warnings


@pytest.mark.parametrize(
    "field,value", [("schema_version", "2.0"), ("score_contract_version", "2.0")]
)
def test_unsupported_contract_is_rejected_without_echoing_input(
    report_factory: ReportFactory,
    field: str,
    value: str,
) -> None:
    path = report_factory()
    payload = json.loads(path.read_bytes())
    payload[field] = value
    path.write_text(json.dumps(payload), encoding="utf-8")
    raw = path.read_bytes()
    with pytest.raises(InvalidUsageError):
        compare_reports(path, path)
    assert path.read_bytes() == raw
