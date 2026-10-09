"""Deterministic comparison JSON, safe terminal text and atomic file output."""

from __future__ import annotations

import json
from importlib.resources import files
from pathlib import Path
from typing import cast

from jsonschema import Draft202012Validator

from ..comparison_models import ComparisonReport
from ..errors import ReportError
from ..redaction import redact_text
from ..schema import _SAFE_REPORT_PATH_PATTERN
from .writers import _atomic_write


def generate_comparison_schema() -> dict[str, object]:
    schema = ComparisonReport.model_json_schema(mode="serialization")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    definitions = cast(dict[str, dict[str, object]], schema["$defs"])
    properties = cast(dict[str, dict[str, object]], definitions["Location"]["properties"])
    properties["path"]["pattern"] = _SAFE_REPORT_PATH_PATTERN
    return schema


def comparison_schema() -> dict[str, object]:
    resource = files("repoinsight.schema").joinpath("repoinsight-comparison-v1.schema.json")
    try:
        schema = json.loads(resource.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise ReportError("Unable to load the checked comparison schema") from None
    if not isinstance(schema, dict):
        raise ReportError("Checked comparison schema is invalid")
    return cast(dict[str, object], schema)


def serialize_comparison(report: ComparisonReport) -> bytes:
    payload = report.model_dump(mode="json")
    if not Draft202012Validator(comparison_schema()).is_valid(payload):
        raise ReportError("Comparison does not satisfy its independent schema")
    # ASCII JSON escapes C1 and bidi controls as well as C0 controls on stdout.
    return (
        json.dumps(
            payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False
        )
        + "\n"
    ).encode("utf-8")


def _terminal_text(text: str) -> str:
    # Escape C0/C1 controls and Unicode format/bidi controls; never interpret input markup.
    import unicodedata

    return "".join(
        c if not unicodedata.category(c).startswith("C") else f"\\u{ord(c):04x}"
        for c in redact_text(text)
    )


def render_comparison(report: ComparisonReport) -> str:
    def score(value: float | None) -> str:
        return "unavailable" if value is None else f"{value:g}"

    def score_line(
        name: str, before: float | None, after: float | None, delta: float | None
    ) -> str:
        return f"{name}: {score(before)} -> {score(after)}; observed delta {score(delta)}"

    lines = [
        "RepoInsight saved-report comparison (contract 1.0)",
        f"Before SHA256: {report.before.sha256}",
        f"After SHA256: {report.after.sha256}",
        score_line(
            "Overall score", report.overall.before, report.overall.after, report.overall.delta
        ),
        f"Completeness: {report.before.completeness.value} -> {report.after.completeness.value}",
        f"Findings: {report.before.findings} -> {report.after.findings}; "
        f"suppressed {report.before.suppressed_findings} -> {report.after.suppressed_findings}",
        f"Skipped inputs: {report.skipped_inputs.before} -> {report.skipped_inputs.after}; "
        f"delta {report.skipped_inputs.delta}",
        f"Warnings: {report.warning_count.before} -> {report.warning_count.after}; "
        f"delta {report.warning_count.delta}",
        "Skipped diagnostic evidence: " + str(report.skipped_input_changes.model_dump()),
        "Warning diagnostic evidence: " + str(report.warning_changes.model_dump()),
        "Changes: "
        + ", ".join(f"{key}={value}" for key, value in report.counts.model_dump().items()),
        "Categories:",
    ]
    for category in report.categories:
        assert category.category is not None
        lines.append(
            "  "
            + score_line(category.category.value, category.before, category.after, category.delta)
            + f"; coverage {category.before_completeness} -> {category.after_completeness}"
        )
    lines.append("Finding evidence (counts; no repository prose):")
    for item in report.findings:
        location = (
            f"{item.location.path}:lines {item.location.start_line}-{item.location.end_line}; "
            f"columns {item.location.start_column}-{item.location.end_column}"
            if item.location
            else "no location"
        )
        qualifiers = ("; ambiguous" if item.ambiguous else "") + (
            "; uncertain" if item.uncertain else ""
        )
        details = []
        if item.before is not None and item.after is not None:
            old = item.before.model_dump(mode="json")
            new = item.after.model_dump(mode="json")
            for field in item.changed_attributes:
                if field in old and field != "content_hashes":
                    details.append(
                        f"{field} {_terminal_text(str(old[field]))} -> "
                        f"{_terminal_text(str(new[field]))}"
                    )
                else:
                    details.append(field + " redacted content changed")
        fields = "; changed " + ", ".join(details) if details else ""
        lines.append(
            f"  {item.status} x{item.count} {item.rule_id} [{_terminal_text(item.analyzer_id)}] "
            f"{_terminal_text(location)}{fields}{qualifiers}"
        )
    lines.append(
        "Compatibility: "
        + (
            "compatible static evidence"
            if report.compatibility.scores_interpretable
            else "limited; deltas need context"
        )
    )
    lines.extend("Warning: " + warning for warning in report.warnings)
    lines.extend("Limit: " + limitation for limitation in report.limitations)
    return "\n".join(lines) + "\n"


def preflight_output(output: Path, inputs: tuple[Path, Path]) -> None:
    """Reject lexical, resolved, symlink and hardlink aliases before any output mutation."""
    try:
        for source in inputs:
            if output.resolve() == source.resolve() or (
                output.exists() and output.samefile(source)
            ):
                raise ReportError("Comparison output must not replace either input report")
        if output.exists() and not output.is_file():
            raise ReportError("Comparison output must be a regular file")
    except (OSError, RuntimeError):
        raise ReportError("Unable to validate comparison output path") from None


def write_comparison(output: Path, payload: bytes, inputs: tuple[Path, Path]) -> None:
    preflight_output(output, inputs)
    try:
        output.parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        raise ReportError("Unable to create comparison output directory") from None
    preflight_output(output, inputs)
    _atomic_write(output, payload)
