"""Bounded report loading and an allowlist-only outbound evidence projection."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

from ..analyzers.catalog import RULE_CATALOG
from ..errors import InvalidUsageError
from ..models import AnalysisReport, Severity
from ..saved_reports import MAX_REPORT_BYTES
from ..saved_reports import load_report as _load_report
from .contracts import PROMPT_VERSION, request_body
from .models import EvidenceReference, PromptVersion

_MODEL = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$")
_METRICS = frozenset(
    {
        "maintainability.max_complexity",
        "maintainability.max_function_loc",
        "maintainability.function_count",
        "testing.test_source_ratio",
        "testing.coverage_evidence",
        "testing.ci_test_evidence",
        "documentation.public_docstring_rate",
        "documentation.readme_present",
        "documentation.readme_installation",
        "documentation.readme_usage",
        "security.possible_secret_count",
        "security.unsafe_subprocess_calls",
        "repository.license_present",
        "repository.ci_present",
        "maintenance.git_available",
    }
)
_SEVERITY_ORDER = {value: index for index, value in enumerate(reversed(tuple(Severity)))}


@dataclass(frozen=True)
class PreparedRequest:
    report: AnalysisReport
    base_report_hash: str
    request_json: str
    payload_hash: str
    estimated_input_tokens: int
    evidence: tuple[EvidenceReference, ...]
    omitted_findings: int
    omitted_metrics: int
    prompt_version: PromptVersion = PROMPT_VERSION


def load_report(path: Path) -> tuple[AnalysisReport, str]:
    """Compatibility wrapper retaining the enrichment import and limit boundary."""
    return _load_report(path, max_bytes=MAX_REPORT_BYTES)


def _estimate(request: str) -> int:
    # One token per UTF-8 byte plus message overhead is intentionally conservative.
    # Count the entire envelope, including instructions and the response schema.
    return len(request.encode("utf-8")) + 256


def prepare_request(
    path: Path,
    *,
    model: str,
    max_findings: int = 20,
    max_input_tokens: int = 8000,
    max_output_tokens: int = 1500,
) -> PreparedRequest:
    if not _MODEL.fullmatch(model):
        raise InvalidUsageError("Model must be a supported model identifier")
    if not 0 <= max_findings <= 20 or not 1 <= max_input_tokens <= 32000:
        raise InvalidUsageError("Invalid finding or input-token limit")
    if not 1 <= max_output_tokens <= 4000:
        raise InvalidUsageError("Invalid output-token limit")
    report, base_hash = load_report(path)
    catalog = {rule.id: rule for rule in RULE_CATALOG}
    references: list[EvidenceReference] = []
    categories: list[dict[str, object]] = []
    for index, category in enumerate(report.scorecard.categories[:6], 1):
        identifier = f"C{index:03}"
        categories.append(
            {
                "id": identifier,
                "category": category.category.value,
                "score": category.score,
                "completeness": category.completeness.value,
            }
        )
        references.append(
            EvidenceReference(id=identifier, label=category.category.value, location=None)
        )
    metrics: list[dict[str, object]] = []
    for metric in sorted(report.metrics, key=lambda item: item.id):
        if metric.id in _METRICS and not isinstance(metric.value, str):
            identifier = f"M{len(metrics) + 1:03}"
            metrics.append(
                {
                    "id": identifier,
                    "metric": metric.id,
                    "value": metric.value,
                    "completeness": metric.completeness.value,
                }
            )
            references.append(EvidenceReference(id=identifier, label=metric.id, location=None))
    findings: list[dict[str, object]] = []
    ordered = sorted(
        report.findings,
        key=lambda item: (
            _SEVERITY_ORDER[item.severity],
            -item.score_impact,
            item.rule_id,
            item.location.path if item.location else "",
            item.location.start_line if item.location else 0,
        ),
    )
    for finding in ordered:
        if len(findings) >= max_findings:
            break
        rule = catalog.get(finding.rule_id)
        if rule is None or finding.suppressed:
            continue
        identifier = f"F{len(findings) + 1:03}"
        # Never forward repository-controlled prose, evidence, paths, or metadata.
        findings.append(
            {
                "id": identifier,
                "rule_id": rule.id,
                "title": rule.title,
                "definition": rule.evidence_definition,
                "remediation": rule.remediation,
                "limitations": rule.limitations,
                "severity": finding.severity.value,
                "confidence": finding.confidence.value,
                "score_impact": finding.score_impact,
            }
        )
        references.append(
            EvidenceReference(
                id=identifier, label=f"{rule.id}: {rule.title}", location=finding.location
            )
        )
    omitted_findings = len(report.findings) - len(findings)
    omitted_metrics = len(report.metrics) - len(metrics)
    while True:
        evidence: dict[str, object] = {
            "completeness": report.completeness.value,
            "overall_score": report.scorecard.overall_score,
            "categories": categories,
            "metrics": metrics,
            "findings": findings,
            "skipped_input_count": len(report.skipped_inputs),
            "warning_count": len(report.warnings),
            "omitted_findings": omitted_findings,
            "omitted_metrics": omitted_metrics,
            "limitations": [
                "Static evidence only; no source or runtime verification.",
                "Findings describe rule matches, not confirmed defects or vulnerabilities.",
            ],
        }
        body = request_body(model, evidence, max_output_tokens)
        if _estimate(body) <= max_input_tokens:
            break
        if findings:
            removed = findings.pop()
            omitted_findings += 1
        elif metrics:
            removed = metrics.pop()
            omitted_metrics += 1
        else:
            raise InvalidUsageError("Input-token limit is too small for the fixed request envelope")
        references = [ref for ref in references if ref.id != removed["id"]]
    return PreparedRequest(
        report=report,
        base_report_hash=base_hash,
        request_json=body,
        payload_hash=hashlib.sha256(body.encode("utf-8")).hexdigest(),
        estimated_input_tokens=_estimate(body),
        evidence=tuple(references),
        omitted_findings=omitted_findings,
        omitted_metrics=omitted_metrics,
    )
