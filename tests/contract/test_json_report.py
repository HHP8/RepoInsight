from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from repoinsight.application import AnalyzeService
from repoinsight.errors import ReportError
from repoinsight.models import AnalysisReport, AnalysisRequest, OutputFormat
from repoinsight.reporting.json_report import serialize_json, validate_json_report
from repoinsight.reporting.writers import write_reports


def _report(root: Path) -> AnalysisReport:
    return (
        AnalyzeService(
            now=lambda: datetime(2026, 8, 24, 12, 0, tzinfo=UTC),
            monotonic=lambda: 1.0,
        )
        .analyze(
            AnalysisRequest(
                source=str(root),
                output_directory=root.parent / "unused",
                formats=(),
                cli_overrides={},
            )
        )
        .report
    )


def test_json_bytes_are_canonical_and_validate_against_checked_schema(tmp_path: Path) -> None:
    root = tmp_path / "repository"
    root.mkdir()
    (root / "app.py").write_text("value = 1\n", encoding="utf-8")
    report = _report(root)

    first = serialize_json(report)
    second = serialize_json(report)

    assert first == second
    assert first.endswith(b"\n")
    assert first.count(b"\n") == 1
    assert first.startswith(b'{"analyzer_status":')
    assert json.loads(first)["schema_version"] == "1.0"
    validate_json_report(report)


def test_report_writer_selects_formats_and_replaces_files_atomically(tmp_path: Path) -> None:
    root = tmp_path / "repository"
    root.mkdir()
    report = _report(root)
    output = tmp_path / "reports"

    first_paths = write_reports(report, output, (OutputFormat.JSON,))
    (output / "repoinsight-report.json").write_text("stale", encoding="utf-8")
    second_paths = write_reports(report, output, (OutputFormat.JSON, OutputFormat.HTML))

    assert first_paths == (output / "repoinsight-report.json",)
    assert second_paths == (
        output / "repoinsight-report.json",
        output / "repoinsight-report.html",
    )
    assert (output / "repoinsight-report.json").read_bytes() == serialize_json(report)
    assert not tuple(output.glob("*.tmp"))


def test_report_writer_cleans_temporary_file_when_replace_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "repository"
    root.mkdir()
    report = _report(root)
    output = tmp_path / "reports"

    def fail_replace(source: Path, target: Path) -> None:
        raise OSError("replace failed")

    monkeypatch.setattr("repoinsight.reporting.writers.os.replace", fail_replace)

    with pytest.raises(Exception, match="Unable to write report output"):
        write_reports(report, output, (OutputFormat.JSON,))
    assert not tuple(output.glob("*.tmp"))


def test_html_only_output_still_requires_public_schema_validation(tmp_path: Path) -> None:
    root = tmp_path / "repository"
    root.mkdir()
    report = _report(root)
    invalid = report.model_copy(update={"schema_version": "9.0"})
    output = tmp_path / "reports"

    with pytest.raises(ReportError, match="does not satisfy schema"):
        write_reports(invalid, output, (OutputFormat.HTML,))

    assert not output.exists()
