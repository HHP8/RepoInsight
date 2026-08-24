from __future__ import annotations

import json
from copy import deepcopy
from datetime import UTC, datetime

import jsonschema
import pytest

from repoinsight import models, schema


def _minimal_complete_report() -> models.AnalysisReport:
    category_scores = tuple(
        models.CategoryScoreTrace(
            category=category,
            baseline=100,
            score=100,
            weight=weight,
            completeness=models.Completeness.AVAILABLE,
            impacts=(),
            limitations=(),
        )
        for category, weight in (
            (models.Category.MAINTAINABILITY, 25),
            (models.Category.TESTING, 25),
            (models.Category.DOCUMENTATION, 15),
            (models.Category.SECURITY_HYGIENE, 15),
            (models.Category.REPOSITORY_HYGIENE, 10),
            (models.Category.MAINTENANCE, 10),
        )
    )
    return models.AnalysisReport(
        schema_version="1.0",
        score_contract_version="1.0",
        tool=models.ToolMetadata(
            name="RepoInsight",
            version="1.0.0",
            schema_version="1.0",
            score_contract_version="1.0",
        ),
        run=models.RunMetadata(generated_at=datetime(2026, 8, 24, tzinfo=UTC), elapsed_seconds=0),
        source=models.SourceMetadata(
            kind=models.SourceKind.LOCAL,
            identity="fixture",
            revision=None,
            history_completeness=models.Completeness.UNAVAILABLE,
        ),
        configuration_fingerprint="0" * 64,
        completeness=models.Completeness.AVAILABLE,
        inventory=models.RepositoryInventory(
            total_files=0,
            python_files=0,
            test_files=0,
            total_bytes=0,
            source_bytes=0,
            python_lines=0,
        ),
        metrics=(),
        findings=(),
        scorecard=models.Scorecard(
            categories=category_scores,
            overall_score=100,
            rating="Excellent",
            available_weight=100,
            rounding="ROUND_HALF_UP to one decimal",
        ),
        git=models.GitSummary(
            available=False,
            completeness=models.Completeness.UNAVAILABLE,
            head_revision=None,
            branch=None,
            commits_considered=0,
            contributor_count=0,
            first_commit_at=None,
            latest_commit_at=None,
            limitations=("Git metadata unavailable",),
        ),
        skipped_inputs=(),
        warnings=(),
        analyzer_status=(),
        limitations=(),
    )


def test_checked_in_schema_is_identical_to_generated_model_schema() -> None:
    generated = schema.generate_report_json_schema()
    checked_in = schema.report_json_schema()

    assert checked_in == generated
    assert checked_in["$schema"] == "https://json-schema.org/draft/2020-12/schema"


def test_minimal_complete_report_validates_independently_with_jsonschema() -> None:
    report = _minimal_complete_report()
    payload = json.loads(report.model_dump_json())

    jsonschema.Draft202012Validator.check_schema(schema.report_json_schema())
    jsonschema.validate(payload, schema.report_json_schema())


@pytest.mark.parametrize(
    "path",
    ["../secret.py", "/absolute.py", "C:/absolute.py", "src\\module.py", "src/./module.py"],
)
def test_schema_rejects_unsafe_report_paths(path: str) -> None:
    payload = json.loads(_minimal_complete_report().model_dump_json())
    payload["warnings"] = [
        {"code": "probe", "message": "unsafe", "location": {"path": path, "start_line": 1}}
    ]

    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(payload, schema.report_json_schema())

    payload = json.loads(_minimal_complete_report().model_dump_json())
    payload["skipped_inputs"] = [{"path": path, "reason": "unsafe"}]
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(payload, schema.report_json_schema())


@pytest.mark.parametrize(
    ("completeness", "value"),
    [("unavailable", 0), ("skipped", False), ("available", None)],
)
def test_schema_rejects_metric_value_completeness_mismatch(
    completeness: str, value: object
) -> None:
    payload = json.loads(_minimal_complete_report().model_dump_json())
    payload["metrics"] = [
        {
            "id": "probe",
            "analyzer_id": "probe",
            "category": "maintenance",
            "value": value,
            "unit": None,
            "provenance": "fixture",
            "completeness": completeness,
            "limitations": [],
        }
    ]

    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(payload, schema.report_json_schema())


@pytest.mark.parametrize(
    ("field", "invalid"),
    [
        ("version", "2.0.0"),
        ("schema_version", "2.0"),
        ("score_contract_version", "3.0"),
    ],
)
def test_schema_rejects_tool_version_drift(field: str, invalid: str) -> None:
    payload = json.loads(_minimal_complete_report().model_dump_json())
    changed = deepcopy(payload)
    changed["tool"][field] = invalid

    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(changed, schema.report_json_schema())
