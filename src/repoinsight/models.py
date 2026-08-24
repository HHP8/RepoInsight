"""Strict, immutable contracts shared by analysis, scoring, and reporting."""

from __future__ import annotations

import re
from collections.abc import Mapping
from datetime import datetime
from enum import StrEnum
from pathlib import Path, PurePosixPath
from types import MappingProxyType
from typing import Literal, TypeAlias

from pathspec import GitIgnoreSpec
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictFloat,
    StrictInt,
    StrictStr,
    field_serializer,
    field_validator,
    model_validator,
)

from .exit_codes import ExitCode
from .redaction import redact_data
from .version import SCHEMA_VERSION, SCORE_CONTRACT_VERSION

_RULE_ID = re.compile(r"^RI-(?:MAINT|TEST|DOC|SEC|REPO|HIST)-\d{3}$")
_DRIVE_PATH = re.compile(r"^[A-Za-z]:[/\\]")


class StrictModel(BaseModel):
    """Base contract that rejects unknown/coerced data and cannot be mutated."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    @model_validator(mode="before")
    @classmethod
    def redact_strings(cls, value: object) -> object:
        """Redact recursively before any value reaches a typed model boundary."""
        return redact_data(value)


class Severity(StrEnum):
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class Confidence(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class Completeness(StrEnum):
    AVAILABLE = "available"
    PARTIAL = "partial"
    UNAVAILABLE = "unavailable"
    SKIPPED = "skipped"


class Category(StrEnum):
    MAINTAINABILITY = "maintainability"
    TESTING = "testing"
    DOCUMENTATION = "documentation"
    SECURITY_HYGIENE = "security_hygiene"
    REPOSITORY_HYGIENE = "repository_hygiene"
    MAINTENANCE = "maintenance"


class SourceKind(StrEnum):
    LOCAL = "local"
    GITHUB = "github"


class OutputFormat(StrEnum):
    JSON = "json"
    HTML = "html"


class ReportFormat(StrEnum):
    JSON = "json"
    HTML = "html"
    ALL = "all"


class AnalyzerState(StrEnum):
    SUCCEEDED = "succeeded"
    PARTIAL = "partial"
    FAILED = "failed"
    SKIPPED = "skipped"


class ToolMetadata(StrictModel):
    name: StrictStr = Field(min_length=1)
    version: Literal["1.0.0"]
    schema_version: Literal["1.0"]
    score_contract_version: Literal["1.0"]


class RunMetadata(StrictModel):
    generated_at: datetime
    elapsed_seconds: float = Field(ge=0, allow_inf_nan=False)

    @field_validator("generated_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("generated_at must include a timezone")
        return value


class SourceMetadata(StrictModel):
    kind: SourceKind
    identity: StrictStr = Field(min_length=1)
    revision: StrictStr | None
    history_completeness: Completeness


def _validate_report_path(value: str) -> str:
    if "\\" in value or _DRIVE_PATH.match(value):
        raise ValueError("path must be a relative POSIX path")
    path = PurePosixPath(value)
    if path.is_absolute() or value in {"", "."} or ".." in path.parts:
        raise ValueError("path must be contained within the repository")
    if str(path) != value or "." in path.parts:
        raise ValueError("path must be normalized")
    return value


class Location(StrictModel):
    path: StrictStr
    start_line: int = Field(ge=1)
    end_line: int | None = Field(default=None, ge=1)
    start_column: int | None = Field(default=None, ge=0)
    end_column: int | None = Field(default=None, ge=0)

    @field_validator("path")
    @classmethod
    def validate_path(cls, value: str) -> str:
        return _validate_report_path(value)

    @model_validator(mode="after")
    def validate_ranges(self) -> Location:
        if self.end_line is not None and self.end_line < self.start_line:
            raise ValueError("end_line must be greater than or equal to start_line")
        if (
            self.end_line == self.start_line
            and self.start_column is not None
            and self.end_column is not None
            and self.end_column < self.start_column
        ):
            raise ValueError("end_column must not precede start_column")
        return self


MetricValue: TypeAlias = StrictBool | StrictInt | StrictFloat | StrictStr


class Metric(StrictModel):
    id: StrictStr = Field(min_length=1)
    analyzer_id: StrictStr = Field(min_length=1)
    category: Category
    value: MetricValue | None
    unit: StrictStr | None
    provenance: StrictStr = Field(min_length=1)
    completeness: Completeness
    limitations: tuple[StrictStr, ...] = ()

    @model_validator(mode="after")
    def validate_value_completeness(self) -> Metric:
        if self.completeness is Completeness.AVAILABLE and self.value is None:
            raise ValueError("available metrics require a measured value")
        if (
            self.completeness in {Completeness.UNAVAILABLE, Completeness.SKIPPED}
            and self.value is not None
        ):
            raise ValueError("unavailable or skipped metrics must use null")
        return self


class Finding(StrictModel):
    rule_id: StrictStr
    analyzer_id: StrictStr = Field(min_length=1)
    analyzer_version: StrictStr = Field(min_length=1)
    category: Category
    severity: Severity
    title: StrictStr = Field(min_length=1)
    explanation: StrictStr = Field(min_length=1)
    location: Location | None = None
    evidence: StrictStr = ""
    remediation: StrictStr = Field(min_length=1)
    score_impact: float = Field(ge=0, le=100, allow_inf_nan=False)
    confidence: Confidence
    limitations: tuple[StrictStr, ...] = ()
    suppressed: StrictBool = False
    suppression_reason: StrictStr | None = None
    cap_applied: StrictBool = False

    @field_validator("rule_id")
    @classmethod
    def validate_rule_id(cls, value: str) -> str:
        if not _RULE_ID.fullmatch(value):
            raise ValueError("rule_id is not a stable RepoInsight rule ID")
        return value

    @model_validator(mode="after")
    def validate_suppression(self) -> Finding:
        if self.suppressed and not self.suppression_reason:
            raise ValueError("suppressed findings require a suppression reason")
        if not self.suppressed and self.suppression_reason is not None:
            raise ValueError("unsuppressed findings cannot have a suppression reason")
        return self


class SkippedInput(StrictModel):
    path: StrictStr
    reason: StrictStr = Field(min_length=1)
    analyzer_id: StrictStr | None = None

    @field_validator("path")
    @classmethod
    def validate_path(cls, value: str) -> str:
        return _validate_report_path(value)


class WarningRecord(StrictModel):
    code: StrictStr = Field(min_length=1)
    message: StrictStr = Field(min_length=1)
    analyzer_id: StrictStr | None = None
    location: Location | None = None


class Limitation(StrictModel):
    code: StrictStr = Field(min_length=1)
    message: StrictStr = Field(min_length=1)
    category: Category | None = None
    analyzer_id: StrictStr | None = None


class AnalyzerMetadata(StrictModel):
    id: StrictStr = Field(min_length=1)
    version: StrictStr = Field(min_length=1)
    category: Category
    rule_ids: tuple[StrictStr, ...]
    capabilities: tuple[StrictStr, ...] = ()

    @field_validator("rule_ids")
    @classmethod
    def validate_rule_ids(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if len(values) != len(set(values)) or any(
            not _RULE_ID.fullmatch(value) for value in values
        ):
            raise ValueError("rule_ids must contain unique stable IDs")
        return values


class AnalyzerStatus(StrictModel):
    analyzer_id: StrictStr = Field(min_length=1)
    state: AnalyzerState
    completeness: Completeness
    elapsed_seconds: float = Field(ge=0, allow_inf_nan=False)
    message: StrictStr | None = None


class AnalyzerResult(StrictModel):
    metadata: AnalyzerMetadata
    status: AnalyzerStatus
    metrics: tuple[Metric, ...] = ()
    findings: tuple[Finding, ...] = ()
    skipped_inputs: tuple[SkippedInput, ...] = ()
    warnings: tuple[WarningRecord, ...] = ()
    limitations: tuple[Limitation, ...] = ()


class RepositoryInventory(StrictModel):
    total_files: int = Field(ge=0)
    python_files: int = Field(ge=0)
    test_files: int = Field(ge=0)
    total_bytes: int = Field(ge=0)
    source_bytes: int = Field(ge=0)
    python_lines: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_counts(self) -> RepositoryInventory:
        if self.python_files > self.total_files or self.test_files > self.total_files:
            raise ValueError("classified file counts cannot exceed total_files")
        if self.source_bytes > self.total_bytes:
            raise ValueError("source_bytes cannot exceed total_bytes")
        return self


class GitSummary(StrictModel):
    available: StrictBool
    completeness: Completeness
    head_revision: StrictStr | None
    branch: StrictStr | None
    commits_considered: int = Field(ge=0)
    contributor_count: int = Field(ge=0)
    first_commit_at: datetime | None
    latest_commit_at: datetime | None
    limitations: tuple[StrictStr, ...] = ()

    @model_validator(mode="after")
    def validate_availability(self) -> GitSummary:
        if not self.available and self.completeness not in {
            Completeness.UNAVAILABLE,
            Completeness.SKIPPED,
        }:
            raise ValueError("unavailable Git metadata must be marked unavailable or skipped")
        if (
            self.first_commit_at is not None
            and self.latest_commit_at is not None
            and self.latest_commit_at < self.first_commit_at
        ):
            raise ValueError("latest_commit_at cannot precede first_commit_at")
        return self


class RuleImpactTrace(StrictModel):
    rule_id: StrictStr
    finding_count: int = Field(ge=0)
    raw_deduction: float = Field(ge=0, allow_inf_nan=False)
    applied_deduction: float = Field(ge=0, allow_inf_nan=False)
    cap: float = Field(ge=0, allow_inf_nan=False)

    @field_validator("rule_id")
    @classmethod
    def validate_rule_id(cls, value: str) -> str:
        if not _RULE_ID.fullmatch(value):
            raise ValueError("rule_id is not a stable RepoInsight rule ID")
        return value

    @model_validator(mode="after")
    def validate_deductions(self) -> RuleImpactTrace:
        if self.applied_deduction > self.raw_deduction or self.applied_deduction > self.cap:
            raise ValueError("applied deduction exceeds raw deduction or cap")
        return self


class CategoryScoreTrace(StrictModel):
    category: Category
    baseline: float = Field(ge=0, le=100, allow_inf_nan=False)
    score: float | None = Field(ge=0, le=100, allow_inf_nan=False)
    weight: float = Field(ge=0, allow_inf_nan=False)
    completeness: Completeness
    impacts: tuple[RuleImpactTrace, ...]
    limitations: tuple[StrictStr, ...]

    @model_validator(mode="after")
    def validate_score_completeness(self) -> CategoryScoreTrace:
        if self.completeness in {Completeness.UNAVAILABLE, Completeness.SKIPPED}:
            if self.score is not None:
                raise ValueError("unavailable category scores must be null")
        elif self.score is None:
            raise ValueError("available or partial category scores require a value")
        return self


class Scorecard(StrictModel):
    categories: tuple[CategoryScoreTrace, ...]
    overall_score: float | None = Field(ge=0, le=100, allow_inf_nan=False)
    rating: StrictStr | None
    available_weight: float = Field(ge=0, allow_inf_nan=False)
    rounding: StrictStr = Field(min_length=1)

    @model_validator(mode="after")
    def validate_overall(self) -> Scorecard:
        if self.overall_score is None and self.rating is not None:
            raise ValueError("a rating requires an overall score")
        if self.overall_score is not None and not self.rating:
            raise ValueError("an overall score requires a rating")
        return self


ThresholdScalar: TypeAlias = StrictInt | StrictFloat
ThresholdValue: TypeAlias = ThresholdScalar | tuple[ThresholdScalar, ...]


class RuleDefinition(StrictModel):
    id: StrictStr
    category: Category
    title: StrictStr = Field(min_length=1)
    evidence_definition: StrictStr = Field(min_length=1)
    default_enabled: StrictBool
    severity: Severity
    default_deduction: float = Field(ge=0, allow_inf_nan=False)
    per_rule_cap: float = Field(ge=0, allow_inf_nan=False)
    threshold_key: StrictStr | tuple[StrictStr, ...] | None
    threshold_value: ThresholdValue | None
    confidence: Confidence
    limitations: StrictStr = Field(min_length=1)
    remediation: StrictStr = Field(min_length=1)
    heuristic: StrictBool

    @field_validator("id")
    @classmethod
    def validate_id(cls, value: str) -> str:
        if not _RULE_ID.fullmatch(value):
            raise ValueError("id is not a stable RepoInsight rule ID")
        return value

    @model_validator(mode="after")
    def validate_threshold_and_cap(self) -> RuleDefinition:
        if (self.threshold_key is None) != (self.threshold_value is None):
            raise ValueError("threshold key and value must be provided together")
        if self.per_rule_cap < self.default_deduction:
            raise ValueError("per-rule cap cannot be below the default deduction")
        return self


class AnalysisConfig(StrictModel):
    exclude: tuple[StrictStr, ...] = ()
    respect_gitignore: StrictBool = True
    max_file_bytes: int = Field(default=1_048_576, gt=0)
    max_files: int = Field(default=20_000, gt=0)
    max_source_bytes: int = Field(default=104_857_600, gt=0)
    timeout_seconds: int = Field(default=120, gt=0)

    @field_validator("exclude", mode="before")
    @classmethod
    def freeze_excludes(cls, value: object) -> object:
        return tuple(value) if isinstance(value, list) else value

    @field_validator("exclude")
    @classmethod
    def validate_exclude_patterns(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        try:
            GitIgnoreSpec.from_lines(value)
        except (TypeError, ValueError) as error:
            raise ValueError("analysis.exclude contains an invalid Git-style pattern") from error
        return value


class GitConfig(StrictModel):
    remote_history_depth: int = Field(default=500, gt=0)
    clone_timeout_seconds: int = Field(default=60, gt=0)


class CategoryWeights(StrictModel):
    maintainability: float = Field(default=25, ge=0, allow_inf_nan=False)
    testing: float = Field(default=25, ge=0, allow_inf_nan=False)
    documentation: float = Field(default=15, ge=0, allow_inf_nan=False)
    security_hygiene: float = Field(default=15, ge=0, allow_inf_nan=False)
    repository_hygiene: float = Field(default=10, ge=0, allow_inf_nan=False)
    maintenance: float = Field(default=10, ge=0, allow_inf_nan=False)

    @model_validator(mode="after")
    def reject_all_zero(self) -> CategoryWeights:
        if not any(self.model_dump().values()):
            raise ValueError("at least one category weight must be positive")
        return self


class ScoringConfig(StrictModel):
    weights: CategoryWeights = Field(default_factory=CategoryWeights)


class RulesConfig(StrictModel):
    enabled: tuple[StrictStr, ...] = ()
    disabled: tuple[StrictStr, ...] = ()

    @field_validator("enabled", "disabled", mode="before")
    @classmethod
    def freeze_rule_ids(cls, value: object) -> object:
        return tuple(value) if isinstance(value, list) else value

    @model_validator(mode="after")
    def validate_rule_sets(self) -> RulesConfig:
        from .analyzers.catalog import RULE_IDS

        enabled = set(self.enabled)
        disabled = set(self.disabled)
        unknown = (enabled | disabled) - RULE_IDS
        if unknown:
            raise ValueError(f"unknown rule IDs: {', '.join(sorted(unknown))}")
        overlap = enabled & disabled
        if overlap:
            raise ValueError(
                f"rule IDs cannot be both enabled and disabled: {', '.join(sorted(overlap))}"
            )
        if len(enabled) != len(self.enabled) or len(disabled) != len(self.disabled):
            raise ValueError("rule enable and disable lists cannot contain duplicates")
        return self


class ThresholdsConfig(StrictModel):
    complexity: int = Field(default=15, gt=0)
    function_loc: int = Field(default=75, gt=0)
    class_loc: int = Field(default=500, gt=0)
    module_loc: int = Field(default=1000, gt=0)
    nesting_depth: int = Field(default=5, gt=0)
    duplicate_statements: int = Field(default=8, gt=0)
    test_ratio_medium: float = Field(default=0.10, gt=0, le=1, allow_inf_nan=False)
    test_ratio_low: float = Field(default=0.25, gt=0, le=1, allow_inf_nan=False)
    public_docstring_rate: float = Field(default=0.50, gt=0, le=1, allow_inf_nan=False)
    stale_days: int = Field(default=365, gt=0)
    activity_window_days: int = Field(default=180, gt=0)
    activity_min_commits: int = Field(default=2, gt=0)
    single_contributor_min_age_days: int = Field(default=180, gt=0)

    @model_validator(mode="after")
    def validate_ratio_order(self) -> ThresholdsConfig:
        if self.test_ratio_medium >= self.test_ratio_low:
            raise ValueError("test_ratio_medium must be below test_ratio_low")
        return self


class OutputConfig(StrictModel):
    format: ReportFormat = ReportFormat.ALL
    directory: StrictStr = Field(default="repoinsight-report", min_length=1)

    @field_validator("format", mode="before")
    @classmethod
    def parse_format(cls, value: object) -> object:
        return ReportFormat(value) if isinstance(value, str) else value


class CIConfig(StrictModel):
    fail_under: float = Field(default=0, ge=0, le=100, allow_inf_nan=False)


class EffectiveConfig(StrictModel):
    analysis: AnalysisConfig = Field(default_factory=AnalysisConfig)
    git: GitConfig = Field(default_factory=GitConfig)
    scoring: ScoringConfig = Field(default_factory=ScoringConfig)
    rules: RulesConfig = Field(default_factory=RulesConfig)
    thresholds: ThresholdsConfig = Field(default_factory=ThresholdsConfig)
    output: OutputConfig = Field(default_factory=OutputConfig)
    ci: CIConfig = Field(default_factory=CIConfig)


class AnalysisReport(StrictModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        json_schema_extra={"$schema": "https://json-schema.org/draft/2020-12/schema"},
    )

    schema_version: Literal["1.0"]
    score_contract_version: Literal["1.0"]
    tool: ToolMetadata
    run: RunMetadata
    source: SourceMetadata
    configuration_fingerprint: StrictStr = Field(pattern=r"^[0-9a-f]{64}$")
    completeness: Completeness
    inventory: RepositoryInventory
    metrics: tuple[Metric, ...]
    findings: tuple[Finding, ...]
    scorecard: Scorecard
    git: GitSummary
    skipped_inputs: tuple[SkippedInput, ...]
    warnings: tuple[WarningRecord, ...]
    analyzer_status: tuple[AnalyzerStatus, ...]
    limitations: tuple[Limitation, ...]


def _deep_freeze(value: object) -> object:
    if isinstance(value, Mapping):
        return MappingProxyType({key: _deep_freeze(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_deep_freeze(item) for item in value)
    if isinstance(value, (set, frozenset)):
        return frozenset(_deep_freeze(item) for item in value)
    return value


def _serialization_copy(value: object) -> object:
    if isinstance(value, Mapping):
        return {key: _serialization_copy(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_serialization_copy(item) for item in value]
    if isinstance(value, (set, frozenset)):
        return [_serialization_copy(item) for item in sorted(value, key=repr)]
    return value


class AnalysisRequest(StrictModel):
    source: StrictStr = Field(min_length=1)
    output_directory: Path
    formats: tuple[OutputFormat, ...]
    cli_overrides: Mapping[StrictStr, object]
    explicit_config: Path | None = None

    @field_validator("cli_overrides", mode="after")
    @classmethod
    def freeze_cli_overrides(cls, value: Mapping[str, object]) -> Mapping[str, object]:
        frozen = _deep_freeze(value)
        if not isinstance(frozen, Mapping):
            raise TypeError("cli_overrides must be a mapping")
        return frozen

    @field_serializer("cli_overrides")
    def serialize_cli_overrides(self, value: Mapping[str, object]) -> dict[str, object]:
        serialized = _serialization_copy(value)
        if not isinstance(serialized, dict):
            raise TypeError("cli_overrides must serialize as an object")
        return serialized


class AnalysisOutcome(StrictModel):
    report: AnalysisReport
    output_paths: tuple[Path, ...]
    exit_code: ExitCode


__all__ = [
    "SCHEMA_VERSION",
    "SCORE_CONTRACT_VERSION",
    "AnalysisConfig",
    "AnalysisOutcome",
    "AnalysisReport",
    "AnalysisRequest",
    "AnalyzerMetadata",
    "AnalyzerResult",
    "AnalyzerState",
    "AnalyzerStatus",
    "CIConfig",
    "Category",
    "CategoryScoreTrace",
    "CategoryWeights",
    "Completeness",
    "Confidence",
    "EffectiveConfig",
    "Finding",
    "GitConfig",
    "GitSummary",
    "Limitation",
    "Location",
    "Metric",
    "OutputConfig",
    "OutputFormat",
    "ReportFormat",
    "RepositoryInventory",
    "RuleDefinition",
    "RuleImpactTrace",
    "RulesConfig",
    "RunMetadata",
    "Scorecard",
    "ScoringConfig",
    "Severity",
    "SkippedInput",
    "SourceKind",
    "SourceMetadata",
    "ThresholdsConfig",
    "ToolMetadata",
    "WarningRecord",
]
