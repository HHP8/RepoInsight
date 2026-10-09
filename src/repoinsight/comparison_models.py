"""Independent comparison contract 1.0; static and AI contracts are unchanged."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field, StrictBool, StrictInt, StrictStr

from .models import Category, Completeness, Confidence, Location, Severity, StrictModel

Digest = Annotated[StrictStr, Field(pattern=r"^[a-f0-9]{64}$")]
Number = Annotated[float, Field(allow_inf_nan=False)]
Count = Annotated[StrictInt, Field(ge=0)]


class InputSummary(StrictModel):
    sha256: Digest
    tool_version: Literal["1.0.0", "1.1.0", "1.2.0"]
    schema_version: Literal["1.0"]
    score_contract_version: Literal["1.0"]
    configuration_fingerprint: Digest
    completeness: Completeness
    findings: Count
    suppressed_findings: Count
    skipped_inputs: Count
    warnings: Count


class AnalyzerVersions(StrictModel):
    analyzer_id: StrictStr
    before: tuple[StrictStr, ...]
    after: tuple[StrictStr, ...]
    # Empty means no version evidence, never the version installed while comparing.


class Compatibility(StrictModel):
    differences: tuple[StrictStr, ...]
    analyzer_versions: tuple[AnalyzerVersions, ...]
    scores_interpretable: StrictBool


class ScoreChange(StrictModel):
    category: Category | None
    before: Number | None
    after: Number | None
    delta: Number | None
    before_completeness: Completeness | None
    after_completeness: Completeness | None


class CountChange(StrictModel):
    before: Count
    after: Count
    delta: StrictInt


class DiagnosticChanges(StrictModel):
    added: Count
    removed: Count
    unchanged: Count


class FindingAttributes(StrictModel):
    analyzer_version: StrictStr
    category: Category
    severity: Severity
    confidence: Confidence
    score_impact: Number
    suppressed: StrictBool
    cap_applied: StrictBool
    # Hashes of redacted prose detect changes without exporting arbitrary prose.
    content_hashes: dict[StrictStr, Digest]


class FindingChange(StrictModel):
    rule_id: StrictStr
    analyzer_id: StrictStr
    location: Location | None
    status: Literal["new", "resolved", "no_longer_observed", "unchanged", "changed"]
    count: Annotated[StrictInt, Field(ge=1)]
    before: FindingAttributes | None
    after: FindingAttributes | None
    changed_attributes: tuple[StrictStr, ...]
    ambiguous: StrictBool
    uncertain: StrictBool


class FindingCounts(StrictModel):
    new: Count
    resolved: Count
    no_longer_observed: Count
    unchanged: Count
    changed: Count


class ComparisonReport(StrictModel):
    comparison_schema_version: Literal["1.0"]
    before: InputSummary
    after: InputSummary
    compatibility: Compatibility
    overall: ScoreChange
    categories: tuple[ScoreChange, ...]
    skipped_inputs: CountChange
    warning_count: CountChange
    skipped_input_changes: DiagnosticChanges
    warning_changes: DiagnosticChanges
    counts: FindingCounts
    findings: tuple[FindingChange, ...]
    warnings: tuple[StrictStr, ...]
    limitations: tuple[StrictStr, ...]
