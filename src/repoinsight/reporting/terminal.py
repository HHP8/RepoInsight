"""Concise color-independent terminal summary."""

from __future__ import annotations

from collections import Counter
from pathlib import Path

from ..models import AnalysisReport, Severity


def render_terminal_summary(report: AnalysisReport, output_paths: tuple[Path, ...]) -> str:
    score = (
        f"{report.scorecard.overall_score:.1f} ({report.scorecard.rating})"
        if report.scorecard.overall_score is not None
        else "unavailable"
    )
    counts = Counter(finding.severity for finding in report.findings)
    lines = [
        f"RepoInsight: {report.source.identity}",
        f"Overall score: {score}",
        "Categories:",
    ]
    for category in report.scorecard.categories:
        value = f"{category.score:.1f}" if category.score is not None else "unavailable"
        lines.append(f"  {category.category.value}: {value} ({category.completeness.value})")
    lines.append(
        "Findings: " + ", ".join(f"{severity.value}={counts[severity]}" for severity in Severity)
    )
    if report.findings:
        lines.append("Highest-impact findings:")
        ordered = sorted(
            report.findings,
            key=lambda finding: (-finding.score_impact, finding.rule_id, finding.title),
        )
        for finding in ordered[:5]:
            location = (
                f" ({finding.location.path}:{finding.location.start_line})"
                if finding.location
                else ""
            )
            lines.append(
                f"  {finding.rule_id} -{finding.score_impact:.1f}: {finding.title}{location}"
            )
    if report.completeness.value != "available":
        lines.append(
            f"Completeness: {report.completeness.value}; "
            f"skipped={len(report.skipped_inputs)}, warnings={len(report.warnings)}"
        )
    if output_paths:
        lines.append("Reports:")
        lines.extend(f"  {path}" for path in output_paths)
    return "\n".join(lines) + "\n"


__all__ = ["render_terminal_summary"]
