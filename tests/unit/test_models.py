from __future__ import annotations

import importlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import cast

import pytest
from pydantic import ValidationError


def test_public_enums_have_exact_values() -> None:
    models = importlib.import_module("repoinsight.models")

    assert [item.value for item in models.Severity] == [
        "info",
        "low",
        "medium",
        "high",
        "critical",
    ]
    assert [item.value for item in models.Confidence] == ["low", "medium", "high"]
    assert [item.value for item in models.Completeness] == [
        "available",
        "partial",
        "unavailable",
        "skipped",
    ]


def test_models_are_frozen_and_reject_extra_fields() -> None:
    models = importlib.import_module("repoinsight.models")
    location = models.Location(path="src/module.py", start_line=1, end_line=2)

    with pytest.raises(ValidationError, match="frozen"):
        location.path = "other.py"
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        models.Location(path="src/module.py", start_line=1, surprise=True)


@pytest.mark.parametrize(
    "path",
    ["../secret.py", "/absolute.py", "C:/absolute.py", "src\\module.py", ".", "src/./module.py"],
)
def test_location_rejects_unsafe_or_noncanonical_paths(path: str) -> None:
    models = importlib.import_module("repoinsight.models")

    with pytest.raises(ValidationError):
        models.Location(path=path, start_line=1)


def test_location_enforces_positive_ordered_lines() -> None:
    models = importlib.import_module("repoinsight.models")

    with pytest.raises(ValidationError):
        models.Location(path="module.py", start_line=0)
    with pytest.raises(ValidationError):
        models.Location(path="module.py", start_line=4, end_line=3)


def test_metric_distinguishes_measured_zero_from_unavailable() -> None:
    models = importlib.import_module("repoinsight.models")
    measured = models.Metric(
        id="python.files",
        analyzer_id="inventory",
        category=models.Category.REPOSITORY_HYGIENE,
        value=0,
        unit="files",
        provenance="bounded inventory",
        completeness=models.Completeness.AVAILABLE,
    )
    unavailable = models.Metric(
        id="git.commits",
        analyzer_id="maintenance",
        category=models.Category.MAINTENANCE,
        value=None,
        unit="commits",
        provenance="git history",
        completeness=models.Completeness.UNAVAILABLE,
        limitations=("Git metadata unavailable",),
    )

    assert measured.value == 0
    assert unavailable.value is None
    with pytest.raises(ValidationError):
        models.Metric(
            id="python.files",
            analyzer_id="inventory",
            category=models.Category.REPOSITORY_HYGIENE,
            value=None,
            unit="files",
            provenance="bounded inventory",
            completeness=models.Completeness.AVAILABLE,
        )
    with pytest.raises(ValidationError):
        models.Metric(
            id="git.commits",
            analyzer_id="maintenance",
            category=models.Category.MAINTENANCE,
            value=0,
            unit="commits",
            provenance="git history",
            completeness=models.Completeness.UNAVAILABLE,
        )


def test_finding_validates_ranges_and_redacts_model_input() -> None:
    models = importlib.import_module("repoinsight.models")
    finding = models.Finding(
        rule_id="RI-SEC-001",
        analyzer_id="security",
        analyzer_version="1.0",
        category=models.Category.SECURITY_HYGIENE,
        severity=models.Severity.HIGH,
        title="Possible secret",
        explanation="A high-specificity pattern matched",
        evidence="api_key=super-secret-value",
        remediation="Rotate it",
        score_impact=10,
        confidence=models.Confidence.HIGH,
    )

    assert "super-secret-value" not in finding.evidence
    assert "[REDACTED]" in finding.evidence
    with pytest.raises(ValidationError):
        models.Finding(**{**finding.model_dump(), "score_impact": -1})


def test_suppressed_finding_requires_a_reason() -> None:
    models = importlib.import_module("repoinsight.models")

    with pytest.raises(ValidationError):
        models.Finding(
            rule_id="RI-MAINT-008",
            analyzer_id="maintainability",
            analyzer_version="1.0",
            category=models.Category.MAINTAINABILITY,
            severity=models.Severity.INFO,
            title="Marker",
            explanation="Marker found",
            evidence="TODO",
            remediation="Review it",
            score_impact=0,
            confidence=models.Confidence.HIGH,
            suppressed=True,
        )


def test_analysis_request_deeply_freezes_cli_overrides() -> None:
    models = importlib.import_module("repoinsight.models")
    supplied = {"analysis": {"max_files": 100}}
    request = models.AnalysisRequest(
        source=".",
        output_directory=Path("reports"),
        formats=(models.OutputFormat.JSON,),
        cli_overrides=supplied,
    )

    with pytest.raises(TypeError):
        request.cli_overrides["output"] = {"format": "html"}
    nested = cast(Mapping[str, object], request.cli_overrides["analysis"])
    with pytest.raises(TypeError):
        nested["max_files"] = 1  # type: ignore[index]
    supplied["analysis"]["max_files"] = 200
    assert nested["max_files"] == 100

    expected = {
        "source": ".",
        "output_directory": "reports",
        "formats": ["json"],
        "cli_overrides": {"analysis": {"max_files": 100}},
        "explicit_config": None,
    }
    first_dump = request.model_dump(mode="json")
    second_dump = request.model_dump(mode="json")
    assert first_dump == expected
    assert second_dump == expected
    assert type(first_dump["cli_overrides"]) is dict
    assert type(first_dump["cli_overrides"]["analysis"]) is dict
    dumped_overrides = cast(dict[str, object], first_dump["cli_overrides"])
    dumped_analysis = cast(dict[str, object], dumped_overrides["analysis"])
    dumped_analysis["max_files"] = 1
    assert nested["max_files"] == 100
    assert request.model_dump(mode="json") == expected
    assert json.loads(request.model_dump_json()) == expected
    assert request.model_dump_json() == request.model_dump_json()


@pytest.mark.parametrize(
    ("field", "invalid"),
    [
        ("version", "2.0.0"),
        ("schema_version", "2.0"),
        ("score_contract_version", "3.0"),
    ],
)
def test_tool_metadata_rejects_version_drift(field: str, invalid: str) -> None:
    models = importlib.import_module("repoinsight.models")
    values = {
        "name": "RepoInsight",
        "version": "1.0.0",
        "schema_version": "1.0",
        "score_contract_version": "1.0",
    }
    values[field] = invalid

    with pytest.raises(ValidationError):
        models.ToolMetadata(**values)
