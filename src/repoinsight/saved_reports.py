"""Bounded static-report loading shared by local consumers, without AI dependencies."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from jsonschema import Draft202012Validator
from pydantic import ValidationError

from .errors import InvalidUsageError
from .models import AnalysisReport
from .schema import report_json_schema

MAX_REPORT_BYTES = 16 * 1024 * 1024


def load_report(path: Path, *, max_bytes: int = MAX_REPORT_BYTES) -> tuple[AnalysisReport, str]:
    """Validate schema, models, uniqueness and finiteness; hash the original bytes."""
    try:
        with path.open("rb") as stream:
            raw = stream.read(max_bytes + 1)
        if len(raw) > max_bytes:
            raise InvalidUsageError("Saved report exceeds the 16 MiB input limit")
        payload = json.loads(raw)
        if not Draft202012Validator(report_json_schema()).is_valid(payload):
            raise InvalidUsageError("Input must satisfy the RepoInsight v1 report schema")
        # Redaction's before-validator converts JSON to Python values. The independent
        # schema enforces JSON types; allow arrays/enums/datetimes to decode here.
        report = AnalysisReport.model_validate_json(raw, strict=False)
        if len({metric.id for metric in report.metrics}) != len(report.metrics):
            raise InvalidUsageError("Saved report contains duplicate metric identifiers")
        categories = report.scorecard.categories
        if len({category.category for category in categories}) != len(categories):
            raise InvalidUsageError("Saved report contains duplicate scoring categories")
        json.dumps(
            report.model_dump(mode="json"),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (OSError, ValueError, RecursionError, ValidationError):
        raise InvalidUsageError("Unable to read a valid saved RepoInsight v1 report") from None
    return report, hashlib.sha256(raw).hexdigest()
