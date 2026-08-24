"""Access to the checked-in public report schema."""

from __future__ import annotations

import json
from copy import deepcopy
from importlib.resources import files
from typing import cast

_SAFE_REPORT_PATH_PATTERN = (
    r"^(?!/)(?![A-Za-z]:/)(?!.*\\)(?!\.{1,2}(?:/|$))"
    r"(?!.*(?:/\.{1,2})(?:/|$))[^/]+(?:/[^/]+)*$"
)


def generate_report_json_schema() -> dict[str, object]:
    """Generate and deterministically augment the public report schema.

    Pydantic emits structural fields and scalar constraints. JSON Schema additions
    below mirror model validators whose cross-field or path semantics Pydantic does
    not currently express in generated schemas.
    """
    from ..models import AnalysisReport

    generated = AnalysisReport.model_json_schema(mode="serialization")
    schema = deepcopy(generated)
    definitions = cast(dict[str, object], schema["$defs"])
    for definition_name in ("Location", "SkippedInput"):
        definition = cast(dict[str, object], definitions[definition_name])
        properties = cast(dict[str, object], definition["properties"])
        path = cast(dict[str, object], properties["path"])
        path["pattern"] = _SAFE_REPORT_PATH_PATTERN

    metric = cast(dict[str, object], definitions["Metric"])
    metric["allOf"] = [
        {
            "if": {
                "properties": {"completeness": {"enum": ["unavailable", "skipped"]}},
                "required": ["completeness"],
            },
            "then": {"properties": {"value": {"type": "null"}}},
        },
        {
            "if": {
                "properties": {"completeness": {"const": "available"}},
                "required": ["completeness"],
            },
            "then": {"properties": {"value": {"not": {"type": "null"}}}},
        },
    ]
    return schema


def report_json_schema() -> dict[str, object]:
    """Load a fresh copy of the packaged Draft 2020-12 report schema."""
    resource = files(__package__).joinpath("repoinsight-report-v1.schema.json")
    return cast(dict[str, object], json.loads(resource.read_text(encoding="utf-8")))


__all__ = ["generate_report_json_schema", "report_json_schema"]
