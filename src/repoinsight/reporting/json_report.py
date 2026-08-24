"""Canonical JSON serialization and independent public-schema validation."""

from __future__ import annotations

import json
from importlib.resources import files
from typing import cast

from jsonschema import Draft202012Validator

from ..errors import ReportError
from ..models import AnalysisReport


def _schema() -> dict[str, object]:
    resource = files("repoinsight.schema").joinpath("repoinsight-report-v1.schema.json")
    try:
        loaded = json.loads(resource.read_text(encoding="utf-8"))
    except (OSError, TypeError, ValueError):
        raise ReportError("Unable to load the checked report schema") from None
    if not isinstance(loaded, dict):
        raise ReportError("Checked report schema is invalid")
    return cast(dict[str, object], loaded)


def validate_json_report(report: AnalysisReport) -> None:
    """Validate the public JSON representation independently of Pydantic."""
    payload = report.model_dump(mode="json")
    errors = sorted(
        Draft202012Validator(_schema()).iter_errors(payload), key=lambda e: list(e.path)
    )
    if errors:
        raise ReportError("Generated report does not satisfy schema version 1.0")


def serialize_json(report: AnalysisReport) -> bytes:
    """Return stable UTF-8 JSON bytes with only runtime fields allowed to vary."""
    validate_json_report(report)
    payload = report.model_dump(mode="json")
    return (
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")


__all__ = ["serialize_json", "validate_json_report"]
