"""Stable process exit codes."""

from enum import IntEnum


class ExitCode(IntEnum):
    """Public process results used by the command-line interface."""

    SUCCESS = 0
    THRESHOLD_FAILED = 10
    INVALID_USAGE = 20
    ACQUISITION_FAILED = 21
    ANALYSIS_FAILED = 22
    REPORT_FAILED = 23
