"""Typed operational errors with stable exit-code ownership."""

from __future__ import annotations

from .exit_codes import ExitCode
from .redaction import redact_text


class RepoInsightError(Exception):
    """Base class for safe, user-facing operational failures."""

    exit_code = ExitCode.ANALYSIS_FAILED

    def __init__(self, message: str) -> None:
        super().__init__(redact_text(message))


class InvalidUsageError(RepoInsightError):
    """Invalid command, source syntax, or configuration."""

    exit_code = ExitCode.INVALID_USAGE


class AcquisitionError(RepoInsightError):
    """Repository acquisition failed."""

    exit_code = ExitCode.ACQUISITION_FAILED


class AnalysisError(RepoInsightError):
    """Analysis could not produce a safe result."""

    exit_code = ExitCode.ANALYSIS_FAILED


class ReportError(RepoInsightError):
    """Required report output could not be written."""

    exit_code = ExitCode.REPORT_FAILED


class ConfigurationError(InvalidUsageError):
    """Configuration parsing or validation failed."""
