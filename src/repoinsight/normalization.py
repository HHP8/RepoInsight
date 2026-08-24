"""Canonical validation, deduplication, redaction, and rule-cap application."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from pydantic import ValidationError

from .analyzers._shared import finding_sort_key, is_rule_enabled, metric_sort_key
from .errors import AnalysisError
from .models import (
    AnalyzerResult,
    AnalyzerStatus,
    Category,
    Completeness,
    EffectiveConfig,
    Finding,
    Limitation,
    Metric,
    RuleDefinition,
    SkippedInput,
    WarningRecord,
)


@dataclass(frozen=True)
class NormalizedEvidence:
    """Detached, deterministic evidence ready for scoring and reporting."""

    metrics: tuple[Metric, ...]
    findings: tuple[Finding, ...]
    raw_deductions: tuple[tuple[str, float], ...]
    skipped_inputs: tuple[SkippedInput, ...]
    warnings: tuple[WarningRecord, ...]
    analyzer_status: tuple[AnalyzerStatus, ...]
    limitations: tuple[Limitation, ...]
    category_completeness: tuple[tuple[Category, Completeness], ...]


def _location_key(finding: Finding) -> tuple[object, ...]:
    location = finding.location
    if location is None:
        return (None,)
    return (
        location.path,
        location.start_line,
        location.end_line,
        location.start_column,
        location.end_column,
    )


def _finding_identity(finding: Finding) -> tuple[object, ...]:
    return finding.rule_id, _location_key(finding), finding.evidence


def _finding_choice_key(finding: Finding) -> str:
    return finding.model_dump_json()


def _warning_key(warning: WarningRecord) -> tuple[object, ...]:
    location = warning.location
    return (
        warning.code,
        warning.message,
        warning.analyzer_id or "",
        location.path if location else "",
        location.start_line if location else 0,
        location.start_column if location and location.start_column is not None else -1,
    )


def _limitation_key(limitation: Limitation) -> tuple[str, str, str, str]:
    return (
        limitation.code,
        limitation.message,
        limitation.category.value if limitation.category else "",
        limitation.analyzer_id or "",
    )


def _revalidate(result: AnalyzerResult) -> AnalyzerResult:
    try:
        return AnalyzerResult.model_validate(result.model_dump(mode="python"))
    except (TypeError, ValueError, ValidationError):
        raise AnalysisError("Invalid analyzer output") from None


def normalize_results(
    analyzer_results: Sequence[AnalyzerResult],
    catalog: Sequence[RuleDefinition],
    config: EffectiveConfig | None = None,
) -> NormalizedEvidence:
    """Validate and canonicalize analyzer evidence before any scoring occurs."""
    effective = config or EffectiveConfig()
    definitions = {rule.id: rule for rule in catalog}
    if len(definitions) != len(catalog):
        raise AnalysisError("Rule catalog contains duplicate identifiers")

    seen_analyzers: set[str] = set()
    seen_categories: set[Category] = set()
    seen_metrics: set[str] = set()
    metrics: list[Metric] = []
    findings_by_identity: dict[tuple[object, ...], Finding] = {}
    skipped: dict[tuple[str, str, str], SkippedInput] = {}
    warnings: dict[tuple[object, ...], WarningRecord] = {}
    limitations: dict[tuple[str, str, str, str], Limitation] = {}
    statuses: list[AnalyzerStatus] = []
    category_completeness: list[tuple[Category, Completeness]] = []

    for untrusted_result in analyzer_results:
        result = _revalidate(untrusted_result)
        metadata = result.metadata
        if metadata.id in seen_analyzers or metadata.category in seen_categories:
            raise AnalysisError("Analyzer output contains duplicate ownership")
        seen_analyzers.add(metadata.id)
        seen_categories.add(metadata.category)
        if result.status.analyzer_id != metadata.id:
            raise AnalysisError("Invalid analyzer output: status ownership mismatch")
        for owned_rule_id in metadata.rule_ids:
            definition = definitions.get(owned_rule_id)
            if definition is None or definition.category is not metadata.category:
                raise AnalysisError("Invalid analyzer output: rule ownership mismatch")

        statuses.append(result.status)
        category_completeness.append((metadata.category, result.status.completeness))
        for metric in result.metrics:
            if metric.analyzer_id != metadata.id or metric.category is not metadata.category:
                raise AnalysisError("Invalid analyzer output: metric ownership mismatch")
            if metric.id in seen_metrics:
                raise AnalysisError(f"Duplicate metric identifier: {metric.id}")
            seen_metrics.add(metric.id)
            metrics.append(metric)
        for finding in result.findings:
            definition = definitions.get(finding.rule_id)
            if (
                definition is None
                or finding.rule_id not in metadata.rule_ids
                or finding.analyzer_id != metadata.id
                or finding.analyzer_version != metadata.version
                or finding.category is not metadata.category
                or finding.category is not definition.category
                or finding.title != definition.title
                or finding.remediation != definition.remediation
                or finding.score_impact > definition.per_rule_cap
            ):
                raise AnalysisError("Invalid analyzer output: finding contract mismatch")
            if not is_rule_enabled(effective, finding.rule_id):
                continue
            identity = _finding_identity(finding)
            existing = findings_by_identity.get(identity)
            if existing is None or _finding_choice_key(finding) < _finding_choice_key(existing):
                findings_by_identity[identity] = finding
        for skipped_item in result.skipped_inputs:
            skipped[(skipped_item.path, skipped_item.reason, skipped_item.analyzer_id or "")] = (
                skipped_item
            )
        for warning_item in result.warnings:
            warnings[_warning_key(warning_item)] = warning_item
        for limitation_item in result.limitations:
            limitations[_limitation_key(limitation_item)] = limitation_item

    unique_findings = sorted(findings_by_identity.values(), key=finding_sort_key)
    raw_deductions: dict[str, float] = {}
    remaining_caps = {rule.id: rule.per_rule_cap for rule in catalog}
    normalized_findings: list[Finding] = []
    for finding in unique_findings:
        raw_impact = 0.0 if finding.suppressed else finding.score_impact
        raw_deductions[finding.rule_id] = raw_deductions.get(finding.rule_id, 0.0) + raw_impact
        remaining = remaining_caps[finding.rule_id]
        applied = min(raw_impact, remaining)
        remaining_caps[finding.rule_id] = max(remaining - applied, 0.0)
        normalized_findings.append(
            finding.model_copy(
                update={
                    "score_impact": applied,
                    "cap_applied": finding.cap_applied or applied < raw_impact,
                }
            )
        )

    return NormalizedEvidence(
        metrics=tuple(sorted(metrics, key=metric_sort_key)),
        findings=tuple(normalized_findings),
        raw_deductions=tuple(sorted(raw_deductions.items())),
        skipped_inputs=tuple(sorted(skipped.values(), key=lambda item: (item.path, item.reason))),
        warnings=tuple(sorted(warnings.values(), key=_warning_key)),
        analyzer_status=tuple(sorted(statuses, key=lambda item: item.analyzer_id)),
        limitations=tuple(sorted(limitations.values(), key=_limitation_key)),
        category_completeness=tuple(sorted(category_completeness, key=lambda item: item[0].value)),
    )


__all__ = ["NormalizedEvidence", "normalize_results"]
