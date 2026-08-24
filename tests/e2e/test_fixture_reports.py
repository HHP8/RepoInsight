from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

import pytest

from repoinsight.application import AnalyzeService
from repoinsight.models import AnalysisRequest, OutputFormat

FIXTURES = Path(__file__).parents[1] / "fixtures" / "repos"


def _analyze(name: str, output: Path, overrides: dict[str, object] | None = None) -> dict[str, Any]:
    outcome = AnalyzeService().analyze(
        AnalysisRequest(
            source=str(FIXTURES / name),
            output_directory=output,
            formats=(OutputFormat.JSON, OutputFormat.HTML),
            cli_overrides=overrides or {},
        )
    )
    assert outcome.output_paths == (
        output / "repoinsight-report.json",
        output / "repoinsight-report.html",
    )
    return cast(
        dict[str, Any],
        json.loads(outcome.output_paths[0].read_text(encoding="utf-8")),
    )


@pytest.mark.parametrize("name", ["healthy", "problematic", "malformed", "no_git"])
def test_representative_fixture_writes_schema_valid_reports(name: str, tmp_path: Path) -> None:
    data = _analyze(name, tmp_path / name)

    assert data["schema_version"] == "1.0"
    assert len(data["analyzer_status"]) == 6


def test_problematic_and_malformed_fixtures_disclose_static_evidence(tmp_path: Path) -> None:
    problematic = _analyze("problematic", tmp_path / "problematic")
    malformed = _analyze("malformed", tmp_path / "malformed")

    problematic_rules = {finding["rule_id"] for finding in problematic["findings"]}
    assert {"RI-SEC-002", "RI-SEC-003", "RI-SEC-004"} <= problematic_rules
    assert any(item["path"] == "broken.py" for item in malformed["skipped_inputs"])


def test_oversized_and_suspected_secret_fixtures_are_safe(tmp_path: Path) -> None:
    oversized = _analyze(
        "oversized",
        tmp_path / "oversized",
        {"analysis.max_file_bytes": 32},
    )
    suspected = _analyze("suspected_secret", tmp_path / "suspected")
    suspected_bytes = (tmp_path / "suspected" / "repoinsight-report.json").read_bytes()
    suspected_html = (tmp_path / "suspected" / "repoinsight-report.html").read_text(
        encoding="utf-8"
    )

    assert any(item["path"] == "payload.py" for item in oversized["skipped_inputs"])
    assert "RI-SEC-001" in {finding["rule_id"] for finding in suspected["findings"]}
    assert b"RepoInsightFixture1234567890" not in suspected_bytes
    assert "RepoInsightFixture1234567890" not in suspected_html
