from __future__ import annotations

import json
from pathlib import Path
from typing import NoReturn

import pytest

from repoinsight.cli import main
from repoinsight.errors import (
    AcquisitionError,
    AnalysisError,
    RepoInsightError,
    ReportError,
)
from repoinsight.exit_codes import ExitCode
from repoinsight.models import AnalysisRequest


def test_version_rules_and_explain_commands(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["version"]) == ExitCode.SUCCESS
    assert "RepoInsight 1.0.0" in capsys.readouterr().out

    assert main(["rules"]) == ExitCode.SUCCESS
    rules_output = capsys.readouterr().out
    assert rules_output.count("RI-") == 41
    assert "RI-SEC-001" in rules_output

    assert main(["explain", "RI-SEC-001"]) == ExitCode.SUCCESS
    explanation = capsys.readouterr().out
    assert "Possible secret" in explanation
    assert "Rotate or revoke" in explanation

    assert main(["explain", "RI-NOT-999"]) == ExitCode.INVALID_USAGE
    assert "Unknown rule ID" in capsys.readouterr().err


def test_analyze_writes_selected_format_and_prints_redacted_summary(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    root = tmp_path / "repository"
    root.mkdir()
    (root / "app.py").write_text("value = 1\n", encoding="utf-8")
    output = tmp_path / "reports"

    result = main(["analyze", str(root), "--output", str(output), "--format", "json"])
    captured = capsys.readouterr()

    assert result == ExitCode.SUCCESS
    assert (output / "repoinsight-report.json").is_file()
    assert not (output / "repoinsight-report.html").exists()
    assert "Overall score:" in captured.out
    assert "repoinsight-report.json" in captured.out
    assert "possible secret" not in captured.out.casefold()


def test_configuration_precedence_and_fail_under_boundary(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    root = tmp_path / "repository"
    root.mkdir()
    (root / "app.py").write_text("value = 1\n", encoding="utf-8")
    (root / ".repoinsight.toml").write_text("[ci]\nfail_under = 100\n", encoding="utf-8")

    configured = main(
        ["analyze", str(root), "--output", str(tmp_path / "configured"), "--format", "json"]
    )
    capsys.readouterr()
    overridden = main(
        [
            "analyze",
            str(root),
            "--output",
            str(tmp_path / "overridden"),
            "--format",
            "json",
            "--fail-under",
            "0",
        ]
    )

    assert configured == ExitCode.THRESHOLD_FAILED
    assert overridden == ExitCode.SUCCESS
    assert (
        json.loads(
            (tmp_path / "overridden" / "repoinsight-report.json").read_text(encoding="utf-8")
        )["scorecard"]["overall_score"]
        < 100
    )


def test_invalid_source_and_option_use_stable_safe_usage_exit(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    sentinel = "ghp_" + "abcdefghijklmnopqrstuvwxyz1234567890"

    source_result = main(["analyze", f"https://example.com/{sentinel}"])
    source_error = capsys.readouterr().err
    option_result = main(["analyze", str(tmp_path), "--format", "xml"])
    option_error = capsys.readouterr().err

    assert source_result == ExitCode.INVALID_USAGE
    assert option_result == ExitCode.INVALID_USAGE
    assert sentinel not in source_error
    assert "Supported formats" in option_error


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        pytest.param(
            AcquisitionError("clone failed"), ExitCode.ACQUISITION_FAILED, id="acquisition"
        ),
        pytest.param(AnalysisError("analysis failed"), ExitCode.ANALYSIS_FAILED, id="analysis"),
        pytest.param(ReportError("report failed"), ExitCode.REPORT_FAILED, id="report"),
    ],
)
def test_operational_errors_keep_their_stable_exit_codes(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    error: RepoInsightError,
    expected: ExitCode,
) -> None:
    class FailingService:
        def analyze(self, request: AnalysisRequest) -> NoReturn:
            raise error

    monkeypatch.setattr("repoinsight.cli._SERVICE_FACTORY", FailingService)

    result = main(["analyze", str(tmp_path), "--output", str(tmp_path / "reports")])

    assert result == expected
    assert str(error) in capsys.readouterr().err
