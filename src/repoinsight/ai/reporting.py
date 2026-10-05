"""Independent schema validation and escaped standalone sidecar reports."""

from __future__ import annotations

from html import escape
from pathlib import Path

from jsonschema import Draft202012Validator

from ..errors import ReportError
from ..reporting.writers import _atomic_write
from .contracts import ai_report_schema, canonical_json
from .models import AIReport


def render_ai_html(report: AIReport) -> str:
    references = {ref.id: ref for ref in report.evidence}

    def citation(identifier: str) -> str:
        ref = references[identifier]
        label = ref.label
        if ref.location is not None:
            label += f" ({ref.location.path}:{ref.location.start_line})"
        return f"<li>{escape(identifier)}: {escape(label)}</li>"

    sections = []
    if report.guidance is not None:
        sections.append(f"<h2>Summary</h2><p>{escape(report.guidance.summary)}</p>")
        sections.append("<h2>Explanations</h2>")
        for explanation in report.guidance.explanations:
            sections.append(
                f"<p>{escape(explanation.text)}</p><ul>{citation(explanation.evidence_id)}</ul>"
            )
        sections.append("<h2>Suggested actions</h2>")
        for action in report.guidance.actions:
            review_note = (
                "Hypothesis: verify before changing code."
                if action.hypothesis
                else "Based on supplied static evidence; review before changing code."
            )
            sections.append(
                f"<h3>{escape(action.title)}</h3>"
                f"<p>Priority {action.priority}; effort {escape(action.effort)}.</p>"
                f"<p>{review_note}</p>"
                f"<p>{escape(action.rationale)}</p>"
                f"<p>{escape(action.suggested_change)}</p>"
                f"<p>Verification: {escape(action.verification)}</p>"
                f"<ul>{''.join(citation(ref) for ref in action.evidence_ids)}</ul>"
            )
    elif report.error is not None:
        sections.append(f"<p>{escape(report.error)}</p>")
    limitations = report.limitations + (
        report.guidance.limitations if report.guidance is not None else ()
    )
    sections.append(
        "<h2>Limitations</h2><ul>"
        + "".join(f"<li>{escape(item)}</li>" for item in limitations)
        + "</ul>"
    )
    usage = (
        "Unavailable"
        if report.usage is None
        else (f"{report.usage.input_tokens} input / {report.usage.output_tokens} output tokens")
    )
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; '
        "style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'\">"
        "<title>RepoInsight AI guidance</title><style>"
        "body{font-family:system-ui,sans-serif;max-width:70ch;margin:2rem auto;padding:1rem;"
        "overflow-wrap:anywhere}p,li{white-space:pre-wrap}h2{margin-top:2rem}"
        "@media print{body{margin:0;max-width:none}}</style></head><body>"
        "<h1>RepoInsight AI guidance</h1>"
        "<p>Advisory suggestions require developer review. Static scores are unchanged.</p>"
        f"<p>Status: {escape(report.status)}. Model: {escape(report.model)}.</p>"
        f"<p>Base report: {escape(report.base_generated_at.isoformat())}; "
        f"revision: {escape(report.base_revision or 'unavailable')}; "
        f"SHA-256: {report.base_report_hash}.</p>"
        f"<p>Guidance generated: {escape(report.generated_at.isoformat())}.</p>"
        f"<p>Conservative input estimate: {report.estimated_input_tokens}. "
        f"Provider usage: {usage}. Omitted findings: {report.omitted_findings}; "
        f"omitted metrics: {report.omitted_metrics}.</p>" + "".join(sections) + "</body></html>"
    )


def prepare_output_directory(output_directory: Path, base_path: Path) -> tuple[Path, ...]:
    """Catch invalid destinations before incurring provider charges."""
    paths = tuple(output_directory / f"repoinsight-ai.{suffix}" for suffix in ("json", "html"))
    # Refuse accidental replacement of the input, including existing symlink/hardlink aliases.
    try:
        for path in paths:
            if path.resolve() == base_path.resolve() or (
                path.exists() and base_path.exists() and path.samefile(base_path)
            ):
                raise ReportError("AI output must not replace the base report")
        output_directory.mkdir(parents=True, exist_ok=True)
    except OSError:
        raise ReportError("Unable to create AI report directory") from None
    return paths


def write_ai_reports(report: AIReport, output_directory: Path, base_path: Path) -> tuple[Path, ...]:
    payload = report.model_dump(mode="json")
    if not Draft202012Validator(ai_report_schema()).is_valid(payload):
        raise ReportError("AI report does not satisfy its independent schema")
    paths = prepare_output_directory(output_directory, base_path)
    for path, content in zip(
        paths, (canonical_json(payload) + "\n", render_ai_html(report)), strict=True
    ):
        _atomic_write(path, content.encode("utf-8"))
    return paths
