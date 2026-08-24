"""Autoescaped standalone offline HTML report rendering."""

from __future__ import annotations

from importlib.resources import files

from jinja2 import Environment, StrictUndefined
from markupsafe import Markup

from ..errors import ReportError
from ..models import AnalysisReport, Category, Severity


def _resource_text(relative: str) -> str:
    try:
        return files("repoinsight.reporting").joinpath(relative).read_text(encoding="utf-8")
    except OSError:
        raise ReportError("Unable to load standalone HTML report resources") from None


def render_html(report: AnalysisReport) -> str:
    """Render trusted package assets around strictly autoescaped report data."""
    environment = Environment(
        autoescape=True,
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    template = environment.from_string(_resource_text("templates/report.html"))
    presentation_findings = tuple(
        sorted(report.findings, key=lambda finding: -finding.score_impact)
    )
    try:
        rendered = template.render(
            report=report,
            findings=presentation_findings,
            categories=tuple(Category),
            severities=tuple(Severity),
            css=Markup(_resource_text("assets/report.css")),
            javascript=Markup(_resource_text("assets/report.js")),
        )
    except Exception:
        raise ReportError("Unable to render standalone HTML report") from None
    return rendered.rstrip() + "\n"


__all__ = ["render_html"]
