"""Thin Typer command adapters for RepoInsight."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Annotated

import typer
from typer import _click

from .acquisition import parse_source
from .analyzers.catalog import RULE_CATALOG
from .application import AnalyzeService
from .config import load_config
from .errors import InvalidUsageError, RepoInsightError
from .exit_codes import ExitCode
from .models import AnalysisRequest, OutputFormat, ReportFormat, SourceKind
from .redaction import safe_exception_message
from .reporting.terminal import render_terminal_summary
from .version import SCHEMA_VERSION, __version__

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Safe, deterministic static insight for Python repositories.",
)
_SERVICE_FACTORY: Callable[[], AnalyzeService] = AnalyzeService


def _formats(value: str) -> tuple[OutputFormat, ...]:
    try:
        selected = ReportFormat(value.casefold())
    except ValueError:
        raise InvalidUsageError("Supported formats are json, html, and all") from None
    if selected is ReportFormat.ALL:
        return (OutputFormat.JSON, OutputFormat.HTML)
    return (OutputFormat(selected.value),)


@app.command("version")
def version_command() -> int:
    """Display tool and schema versions."""
    typer.echo(f"RepoInsight {__version__} (JSON schema {SCHEMA_VERSION})")
    return int(ExitCode.SUCCESS)


@app.command("rules")
def rules_command() -> int:
    """List the stable version 1 rule catalog."""
    for rule in RULE_CATALOG:
        enabled = "enabled" if rule.default_enabled else "disabled"
        typer.echo(
            f"{rule.id}\t{rule.category.value}\t{rule.severity.value}\t"
            f"-{rule.default_deduction:g} cap {rule.per_rule_cap:g}\t{enabled}\t{rule.title}"
        )
    return int(ExitCode.SUCCESS)


@app.command("explain")
def explain_command(rule_id: str = typer.Argument(..., help="Stable rule ID.")) -> int:
    """Explain one stable rule, its limits, and remediation."""
    rule = next((item for item in RULE_CATALOG if item.id == rule_id.upper()), None)
    if rule is None:
        raise InvalidUsageError("Unknown rule ID")
    typer.echo(f"{rule.id}: {rule.title}")
    typer.echo(f"Category: {rule.category.value}")
    typer.echo(f"Severity: {rule.severity.value}")
    typer.echo(f"Evidence: {rule.evidence_definition}")
    typer.echo(f"Score: -{rule.default_deduction:g}, cap {rule.per_rule_cap:g}")
    typer.echo(f"Limitations: {rule.limitations}")
    typer.echo(f"Remediation: {rule.remediation}")
    return int(ExitCode.SUCCESS)


@app.command("analyze")
def analyze_command(
    source: Annotated[str, typer.Argument(help="Local directory or public GitHub URL.")],
    output: Annotated[
        Path | None,
        typer.Option("--output", help="Report output directory."),
    ] = None,
    report_format: Annotated[
        str | None,
        typer.Option("--format", help="json, html, or all."),
    ] = None,
    fail_under: Annotated[float | None, typer.Option("--fail-under", min=0, max=100)] = None,
    config_path: Annotated[
        Path | None,
        typer.Option("--config", help="Explicit TOML config."),
    ] = None,
    exclude: Annotated[
        list[str] | None,
        typer.Option("--exclude", help="Git-style exclusion."),
    ] = None,
    max_file_bytes: Annotated[int | None, typer.Option("--max-file-bytes", min=1)] = None,
    max_files: Annotated[int | None, typer.Option("--max-files", min=1)] = None,
    max_source_bytes: Annotated[
        int | None,
        typer.Option("--max-source-bytes", min=1),
    ] = None,
    timeout_seconds: Annotated[int | None, typer.Option("--timeout", min=1)] = None,
    enable_rule: Annotated[list[str] | None, typer.Option("--enable-rule")] = None,
    disable_rule: Annotated[list[str] | None, typer.Option("--disable-rule")] = None,
) -> int:
    """Analyze a repository and write validated offline reports."""
    overrides: dict[str, object] = {}
    if fail_under is not None:
        overrides["ci.fail_under"] = fail_under
    if exclude is not None:
        overrides["analysis.exclude"] = exclude
    if max_file_bytes is not None:
        overrides["analysis.max_file_bytes"] = max_file_bytes
    if max_files is not None:
        overrides["analysis.max_files"] = max_files
    if max_source_bytes is not None:
        overrides["analysis.max_source_bytes"] = max_source_bytes
    if timeout_seconds is not None:
        overrides["analysis.timeout_seconds"] = timeout_seconds
    if enable_rule is not None:
        overrides["rules.enabled"] = tuple(item.upper() for item in enable_rule)
    if disable_rule is not None:
        overrides["rules.disabled"] = tuple(item.upper() for item in disable_rule)

    reference = parse_source(source)
    preview_root = reference.local_path if reference.kind is SourceKind.LOCAL else None
    preview = load_config(preview_root, config_path, overrides)
    selected_format = report_format or preview.output.format.value
    formats = _formats(selected_format)
    output_directory = output or Path(preview.output.directory)
    if not output_directory.is_absolute():
        output_directory = Path.cwd() / output_directory
    request = AnalysisRequest(
        source=source,
        output_directory=output_directory,
        formats=formats,
        cli_overrides=overrides,
        explicit_config=config_path,
    )
    outcome = _SERVICE_FACTORY().analyze(request)
    typer.echo(render_terminal_summary(outcome.report, outcome.output_paths), nl=False)
    return int(outcome.exit_code)


def main(args: list[str] | None = None) -> int:
    """Run the Typer command tree while preserving RepoInsight exit codes."""
    command = typer.main.get_command(app)
    try:
        result = command.main(args=args, prog_name="repoinsight", standalone_mode=False)
    except RepoInsightError as error:
        typer.echo(f"Error: {safe_exception_message(error)}", err=True)
        return int(error.exit_code)
    except (_click.ClickException, typer.Abort) as error:
        typer.echo(f"Error: {safe_exception_message(error)}", err=True)
        return int(ExitCode.INVALID_USAGE)
    return int(result or ExitCode.SUCCESS)


__all__ = ["app", "main"]
