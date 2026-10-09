"""Offline, conservative multiset comparison of validated saved static reports."""

from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from functools import partial
from pathlib import Path
from typing import Literal

from .comparison_models import (
    AnalyzerVersions,
    ComparisonReport,
    Compatibility,
    CountChange,
    DiagnosticChanges,
    FindingAttributes,
    FindingChange,
    FindingCounts,
    InputSummary,
    ScoreChange,
)
from .models import AnalysisReport, AnalyzerState, Category, Completeness, Finding, StrictModel
from .saved_reports import load_report

_PROSE = ("title", "explanation", "evidence", "remediation", "limitations", "suppression_reason")
_LIMITATIONS = (
    "Exact normalized locations only; renames, line shifts and range changes "
    "can appear as removals/additions.",
    "Repeated keys are multisets: exact attributes match first; residual pairs "
    "are deterministic, not proven identities.",
    "Locationless matches are ambiguous; suppression is not a fix.",
    "Resolved means absent from compatible complete static evidence, "
    "never a verified security fix.",
    "Score deltas are observed arithmetic, not proof of improvement or regression.",
    "Prose changes use hashes of redacted values; secrets removed by redaction "
    "cannot be distinguished.",
    "Analyzer versions come only from finding evidence; absent versions and "
    "configuration details cannot be inferred.",
)


def _canonical(value: object) -> str:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    )


def _attributes(finding: Finding) -> FindingAttributes:
    values = finding.model_dump(mode="json")
    return FindingAttributes(
        analyzer_version=finding.analyzer_version,
        category=finding.category,
        severity=finding.severity,
        confidence=finding.confidence,
        score_impact=finding.score_impact,
        suppressed=finding.suppressed,
        cap_applied=finding.cap_applied,
        content_hashes={
            name: hashlib.sha256(_canonical(values[name]).encode("utf-8")).hexdigest()
            for name in _PROSE
        },
    )


def _summary(report: AnalysisReport, digest: str) -> InputSummary:
    return InputSummary(
        sha256=digest,
        tool_version=report.tool.version,
        schema_version=report.schema_version,
        score_contract_version=report.score_contract_version,
        configuration_fingerprint=report.configuration_fingerprint,
        completeness=report.completeness,
        findings=len(report.findings),
        suppressed_findings=sum(f.suppressed for f in report.findings),
        skipped_inputs=len(report.skipped_inputs),
        warnings=len(report.warnings),
    )


def _append_change(
    changes: list[FindingChange],
    sample: Finding,
    attributes: dict[str, FindingAttributes],
    ambiguous: bool,
    compatible_coverage: bool,
    status: Literal["new", "resolved", "no_longer_observed", "unchanged", "changed"],
    count: int,
    old_key: str | None,
    new_key: str | None,
) -> None:
    old_value = attributes[old_key] if old_key else None
    new_value = attributes[new_key] if new_key else None
    changed: list[str] = []
    if old_value is not None and new_value is not None:
        a, b = old_value.model_dump(mode="json"), new_value.model_dump(mode="json")
        changed.extend(name for name in a if name != "content_hashes" and a[name] != b[name])
        changed.extend(
            name
            for name in _PROSE
            if old_value.content_hashes[name] != new_value.content_hashes[name]
        )
    changes.append(
        FindingChange(
            rule_id=sample.rule_id,
            analyzer_id=sample.analyzer_id,
            location=sample.location,
            status=status,
            count=count,
            before=old_value,
            after=new_value,
            changed_attributes=tuple(sorted(changed)),
            ambiguous=ambiguous,
            uncertain=not compatible_coverage or ambiguous,
        )
    )


def _versions(report: AnalysisReport) -> dict[str, tuple[str, ...]]:
    versions: dict[str, set[str]] = {s.analyzer_id: set() for s in report.analyzer_status}
    for finding in report.findings:
        versions.setdefault(finding.analyzer_id, set()).add(finding.analyzer_version)
    return {identifier: tuple(sorted(values)) for identifier, values in versions.items()}


def _diagnostics(
    before: tuple[StrictModel, ...], after: tuple[StrictModel, ...]
) -> DiagnosticChanges:
    old = Counter(_canonical(x.model_dump(mode="json")) for x in before)
    new = Counter(_canonical(x.model_dump(mode="json")) for x in after)
    return DiagnosticChanges(
        added=sum((new - old).values()),
        removed=sum((old - new).values()),
        unchanged=sum((old & new).values()),
    )


def _compatibility(before: AnalysisReport, after: AnalysisReport) -> Compatibility:
    differences: list[str] = []
    checks = {
        "source-identity": (before.source.kind, before.source.identity)
        != (after.source.kind, after.source.identity),
        "configuration-fingerprint": before.configuration_fingerprint
        != after.configuration_fingerprint,
        "tool": before.tool != after.tool,
        "schema-contract": before.schema_version != after.schema_version,
        "score-contract": before.score_contract_version != after.score_contract_version,
    }
    old_categories = {c.category: c for c in before.scorecard.categories}
    new_categories = {c.category: c for c in after.scorecard.categories}
    checks["category-set"] = old_categories.keys() != new_categories.keys()
    checks["scorecard-settings"] = before.scorecard.rounding != after.scorecard.rounding or any(
        (old_categories[c].weight, old_categories[c].baseline)
        != (new_categories[c].weight, new_categories[c].baseline)
        for c in old_categories.keys() & new_categories.keys()
    )
    old_versions, new_versions = _versions(before), _versions(after)
    versions = tuple(
        AnalyzerVersions(
            analyzer_id=identifier,
            before=old_versions.get(identifier, ()),
            after=new_versions.get(identifier, ()),
        )
        for identifier in sorted(old_versions.keys() | new_versions.keys())
    )
    checks["analyzer-set"] = old_versions.keys() != new_versions.keys()
    checks["analyzer-versions"] = any(
        v.before and v.after and v.before != v.after for v in versions
    )
    differences.extend(name for name, changed in checks.items() if changed)
    complete = all(
        r.completeness is Completeness.AVAILABLE
        and not r.skipped_inputs
        and not r.warnings
        and _status_evidence(r)
        and bool(r.scorecard.categories)
        and all(c.completeness is Completeness.AVAILABLE for c in r.scorecard.categories)
        and all(
            a.completeness is Completeness.AVAILABLE and a.state is AnalyzerState.SUCCEEDED
            for a in r.analyzer_status
        )
        for r in (before, after)
    )
    version_evidence = bool(versions) and all(len(v.before) == len(v.after) == 1 for v in versions)
    return Compatibility(
        differences=tuple(sorted(differences)),
        analyzer_versions=versions,
        scores_interpretable=not differences and complete and version_evidence,
    )


def _status_evidence(report: AnalysisReport) -> bool:
    identifiers = [s.analyzer_id for s in report.analyzer_status]
    return (
        bool(identifiers)
        and len(set(identifiers)) == len(identifiers)
        and all(f.analyzer_id in identifiers for f in report.findings)
    )


def _coverage(report: AnalysisReport, finding: Finding) -> bool:
    category = next(
        (c for c in report.scorecard.categories if c.category == finding.category), None
    )
    statuses = [s for s in report.analyzer_status if s.analyzer_id == finding.analyzer_id]
    return (
        report.completeness is Completeness.AVAILABLE
        and not report.skipped_inputs
        and not report.warnings
        and category is not None
        and category.completeness is Completeness.AVAILABLE
        and len(statuses) == 1
        and statuses[0].state is AnalyzerState.SUCCEEDED
        and statuses[0].completeness is Completeness.AVAILABLE
    )


def _score(
    category: Category | None,
    old: float | None,
    new: float | None,
    old_completeness: Completeness | None,
    new_completeness: Completeness | None,
) -> ScoreChange:
    return ScoreChange(
        category=category,
        before=old,
        after=new,
        delta=None if old is None or new is None else round(new - old, 10),
        before_completeness=old_completeness,
        after_completeness=new_completeness,
    )


def compare_reports(before_path: Path, after_path: Path) -> ComparisonReport:
    """Read only saved inputs. Never acquire a repository, run analyzers or use AI."""
    before, before_hash = load_report(before_path)
    after, after_hash = load_report(after_path)
    compatibility = _compatibility(before, after)
    groups: dict[tuple[str, str, str], tuple[list[Finding], list[Finding]]] = defaultdict(
        lambda: ([], [])
    )
    for side, report in enumerate((before, after)):
        for finding in report.findings:
            location = (
                _canonical(finding.location.model_dump(mode="json")) if finding.location else "null"
            )
            groups[(finding.rule_id, finding.analyzer_id, location)][side].append(finding)
    changes: list[FindingChange] = []
    for _key, (old, new) in sorted(groups.items()):
        attributes = {}
        old_counts: Counter[str] = Counter()
        new_counts: Counter[str] = Counter()
        for items, counts in ((old, old_counts), (new, new_counts)):
            for finding in items:
                value = _attributes(finding)
                key = _canonical(value.model_dump(mode="json"))
                attributes[key] = value
                counts[key] += 1
        sample = (old or new)[0]
        ambiguous = sample.location is None or len(old) > 1 or len(new) > 1
        compatible_coverage = not compatibility.differences and all(
            _coverage(r, representative)
            for representative in {f.category: f for f in (*old, *new)}.values()
            for r in (before, after)
        )

        add = partial(_append_change, changes, sample, attributes, ambiguous, compatible_coverage)

        for key in sorted(old_counts.keys() & new_counts.keys()):
            count = min(old_counts[key], new_counts[key])
            add("unchanged", count, key, key)
            old_counts[key] -= count
            new_counts[key] -= count
        # Pair residual multisets by canonical attributes, with an explicit ambiguity flag.
        old_keys = sorted(k for k, c in old_counts.items() if c)
        new_keys = sorted(k for k, c in new_counts.items() if c)
        i = j = 0
        while i < len(old_keys) and j < len(new_keys):
            a, b = old_keys[i], new_keys[j]
            count = min(old_counts[a], new_counts[b])
            add("changed", count, a, b)
            old_counts[a] -= count
            new_counts[b] -= count
            i += int(old_counts[a] == 0)
            j += int(new_counts[b] == 0)
        for key in old_keys[i:]:
            status: Literal["resolved", "no_longer_observed"] = (
                "resolved" if compatible_coverage else "no_longer_observed"
            )
            add(status, old_counts[key], key, None)
        for key in new_keys[j:]:
            add("new", new_counts[key], None, key)
    counts = Counter(
        {name: 0 for name in ("new", "resolved", "no_longer_observed", "unchanged", "changed")}
    )
    for change in changes:
        counts[change.status] += change.count
    warnings = {"static-comparison-not-fix-proof", "exact-location-matching"}
    warnings.update(compatibility.differences)
    if any(
        r.completeness is not Completeness.AVAILABLE
        or r.skipped_inputs
        or r.warnings
        or any(c.completeness is not Completeness.AVAILABLE for c in r.scorecard.categories)
        or any(
            a.completeness is not Completeness.AVAILABLE or a.state is not AnalyzerState.SUCCEEDED
            for a in r.analyzer_status
        )
        for r in (before, after)
    ):
        warnings.add("partial-or-unavailable-coverage")
    if not compatibility.analyzer_versions or any(
        not v.before or not v.after for v in compatibility.analyzer_versions
    ):
        warnings.add("analyzer-version-evidence-incomplete")
    if any(len(v.before) > 1 or len(v.after) > 1 for v in compatibility.analyzer_versions):
        warnings.add("mixed-analyzer-version-evidence")
    if not all(_status_evidence(r) for r in (before, after)):
        warnings.add("analyzer-status-evidence-incomplete")
    if any(c.ambiguous for c in changes):
        warnings.add("ambiguous-finding-matches")
    if any(f.suppressed for r in (before, after) for f in r.findings):
        warnings.add("suppression-is-not-a-fix")
    if not compatibility.scores_interpretable:
        warnings.add("score-deltas-require-context")
    old_categories = {c.category: c for c in before.scorecard.categories}
    new_categories = {c.category: c for c in after.scorecard.categories}
    categories = []
    for category in sorted(old_categories.keys() | new_categories.keys()):
        old_category, new_category = old_categories.get(category), new_categories.get(category)
        categories.append(
            _score(
                category,
                old_category.score if old_category else None,
                new_category.score if new_category else None,
                old_category.completeness if old_category else None,
                new_category.completeness if new_category else None,
            )
        )
    return ComparisonReport(
        comparison_schema_version="1.0",
        before=_summary(before, before_hash),
        after=_summary(after, after_hash),
        compatibility=compatibility,
        overall=_score(
            None,
            before.scorecard.overall_score,
            after.scorecard.overall_score,
            before.completeness,
            after.completeness,
        ),
        categories=tuple(categories),
        skipped_inputs=CountChange(
            before=len(before.skipped_inputs),
            after=len(after.skipped_inputs),
            delta=len(after.skipped_inputs) - len(before.skipped_inputs),
        ),
        warning_count=CountChange(
            before=len(before.warnings),
            after=len(after.warnings),
            delta=len(after.warnings) - len(before.warnings),
        ),
        skipped_input_changes=_diagnostics(before.skipped_inputs, after.skipped_inputs),
        warning_changes=_diagnostics(before.warnings, after.warnings),
        counts=FindingCounts(**counts),
        findings=tuple(changes),
        warnings=tuple(sorted(warnings)),
        limitations=_LIMITATIONS,
    )
