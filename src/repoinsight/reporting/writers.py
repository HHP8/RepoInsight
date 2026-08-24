"""Atomic report output writers with cleanup on every failure path."""

from __future__ import annotations

import os
import tempfile
from contextlib import suppress
from pathlib import Path

from ..errors import ReportError
from ..models import AnalysisReport, OutputFormat
from .html_report import render_html
from .json_report import serialize_json, validate_json_report

_NAMES = {
    OutputFormat.JSON: "repoinsight-report.json",
    OutputFormat.HTML: "repoinsight-report.html",
}


def _atomic_write(path: Path, payload: bytes) -> None:
    descriptor = -1
    temporary_path: Path | None = None
    try:
        descriptor, raw_temporary = tempfile.mkstemp(
            prefix=f".{path.name}.",
            suffix=".tmp",
            dir=path.parent,
        )
        temporary_path = Path(raw_temporary)
        with os.fdopen(descriptor, "wb") as stream:
            descriptor = -1
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_path, path)
        temporary_path = None
    except OSError:
        raise ReportError("Unable to write report output") from None
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if temporary_path is not None:
            with suppress(OSError):
                temporary_path.unlink()


def write_reports(
    report: AnalysisReport,
    output_directory: Path,
    formats: tuple[OutputFormat, ...],
) -> tuple[Path, ...]:
    """Validate and write selected formats in deterministic order."""
    selected = tuple(item for item in OutputFormat if item in formats)
    if not selected:
        return ()
    validate_json_report(report)
    try:
        output_directory.mkdir(parents=True, exist_ok=True)
        if not output_directory.is_dir():
            raise OSError("output is not a directory")
    except OSError:
        raise ReportError("Unable to create report output directory") from None

    paths: list[Path] = []
    for report_format in selected:
        path = output_directory / _NAMES[report_format]
        payload = (
            serialize_json(report)
            if report_format is OutputFormat.JSON
            else render_html(report).encode("utf-8")
        )
        _atomic_write(path, payload)
        paths.append(path)
    return tuple(paths)


__all__ = ["write_reports"]
