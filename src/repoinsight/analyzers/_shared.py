"""Pure helpers shared by the six built-in static analyzers."""

from __future__ import annotations

import ast
import re
from collections.abc import Callable, Iterable, Mapping

from ..inventory import FileRecord, FileRole, InventoryResult
from ..models import (
    AnalyzerMetadata,
    AnalyzerResult,
    AnalyzerState,
    AnalyzerStatus,
    Completeness,
    Confidence,
    EffectiveConfig,
    Finding,
    Limitation,
    Location,
    Metric,
    Severity,
    SkippedInput,
    WarningRecord,
)
from ..python_index import ParsedPythonFile, PythonIndex
from ..redaction import redact_text
from .catalog import RULE_CATALOG

CATALOG_BY_ID = {rule.id: rule for rule in RULE_CATALOG}
_BROAD_ABSENCE_LIMITATIONS = frozenset(
    {"directory-entry-limit", "file-discovery-limit", "inventory-timeout", "root-unreadable"}
)
_CONVENTIONAL_CI = re.compile(r"^\.github/workflows/[^/]+\.ya?ml$", re.IGNORECASE)


def catalog_rule(rule_id: str):  # type: ignore[no-untyped-def]
    """Return immutable catalog metadata for one stable rule ID."""
    try:
        return CATALOG_BY_ID[rule_id]
    except KeyError:
        raise ValueError(f"unknown catalog rule: {rule_id}") from None


def is_rule_enabled(config: EffectiveConfig, rule_id: str) -> bool:
    rule = catalog_rule(rule_id)
    return rule_id in config.rules.enabled or (
        rule.default_enabled and rule_id not in config.rules.disabled
    )


def is_conventional_ci_path(path: str) -> bool:
    folded = path.casefold()
    return bool(_CONVENTIONAL_CI.fullmatch(path)) or folded in {".travis.yml", "appveyor.yml"}


def absence_evidence_complete(
    inventory: InventoryResult,
    could_satisfy: Callable[[str], bool],
) -> bool:
    """Return true only when missing evidence is known to be genuinely absent."""
    if inventory.completeness in {Completeness.UNAVAILABLE, Completeness.SKIPPED}:
        return False
    if any(item.code in _BROAD_ABSENCE_LIMITATIONS for item in inventory.limitations):
        return False
    for skipped in inventory.skipped_inputs:
        if skipped.reason == "safety-excluded directory":
            continue
        if "directory" in skipped.reason or could_satisfy(skipped.path):
            return False
    return True


def make_location(
    parsed: ParsedPythonFile,
    node: ast.AST,
    *,
    line: int | None = None,
) -> Location:
    start_line = line if line is not None else int(getattr(node, "lineno", 1))
    if line is not None:
        return Location(path=parsed.file.path, start_line=start_line, end_line=start_line)
    end_line = int(getattr(node, "end_lineno", start_line) or start_line)
    start_column = getattr(node, "col_offset", None)
    end_column = getattr(node, "end_col_offset", None)
    return Location(
        path=parsed.file.path,
        start_line=start_line,
        end_line=end_line,
        start_column=start_column if isinstance(start_column, int) else None,
        end_column=end_column if isinstance(end_column, int) else None,
    )


def make_finding(
    metadata: AnalyzerMetadata,
    rule_id: str,
    *,
    location: Location | None = None,
    evidence: str = "",
    explanation_detail: str = "",
    severity: Severity | None = None,
    score_impact: float | None = None,
    confidence: Confidence | None = None,
    limitations: tuple[str, ...] = (),
) -> Finding:
    """Build one finding exclusively from catalog-owned rule metadata."""
    rule = catalog_rule(rule_id)
    if rule_id not in metadata.rule_ids or rule.category is not metadata.category:
        raise ValueError("finding rule is not owned by the analyzer")
    explanation = rule.evidence_definition
    if explanation_detail:
        explanation = f"{explanation} {explanation_detail}"
    return Finding(
        rule_id=rule.id,
        analyzer_id=metadata.id,
        analyzer_version=metadata.version,
        category=rule.category,
        severity=severity or rule.severity,
        title=rule.title,
        explanation=redact_text(explanation),
        location=location,
        evidence=redact_text(evidence),
        remediation=rule.remediation,
        score_impact=rule.default_deduction if score_impact is None else score_impact,
        confidence=confidence or rule.confidence,
        limitations=tuple(redact_text(item) for item in (rule.limitations, *limitations)),
        suppressed=False,
        suppression_reason=None,
        cap_applied=False,
    )


def make_metric(
    metadata: AnalyzerMetadata,
    metric_id: str,
    value: bool | int | float | str | None,
    *,
    unit: str | None,
    provenance: str,
    completeness: Completeness,
    limitations: tuple[str, ...] = (),
) -> Metric:
    return Metric(
        id=metric_id,
        analyzer_id=metadata.id,
        category=metadata.category,
        value=value,
        unit=unit,
        provenance=redact_text(provenance),
        completeness=completeness,
        limitations=tuple(redact_text(item) for item in limitations),
    )


def finding_sort_key(finding: Finding) -> tuple[str, str, int, int, str, str]:
    location = finding.location
    return (
        finding.rule_id,
        location.path if location is not None else "",
        location.start_line if location is not None else 0,
        location.start_column if location is not None and location.start_column is not None else -1,
        finding.title,
        finding.evidence,
    )


def metric_sort_key(metric: Metric) -> tuple[str, str]:
    return metric.id, metric.analyzer_id


def make_limitation(metadata: AnalyzerMetadata, code: str, message: str) -> Limitation:
    return Limitation(
        code=code,
        message=redact_text(message),
        category=metadata.category,
        analyzer_id=metadata.id,
    )


def make_result(
    metadata: AnalyzerMetadata,
    completeness: Completeness,
    *,
    metrics: Iterable[Metric] = (),
    findings: Iterable[Finding] = (),
    skipped_inputs: Iterable[SkippedInput] = (),
    warnings: Iterable[WarningRecord] = (),
    limitations: Iterable[Limitation] = (),
) -> AnalyzerResult:
    state = (
        AnalyzerState.SUCCEEDED if completeness is Completeness.AVAILABLE else AnalyzerState.PARTIAL
    )
    return AnalyzerResult(
        metadata=metadata,
        status=AnalyzerStatus(
            analyzer_id=metadata.id,
            state=state,
            completeness=completeness,
            elapsed_seconds=0.0,
        ),
        metrics=tuple(sorted(metrics, key=metric_sort_key)),
        findings=tuple(sorted(findings, key=finding_sort_key)),
        skipped_inputs=tuple(sorted(skipped_inputs, key=lambda item: (item.path, item.reason))),
        warnings=tuple(sorted(warnings, key=lambda item: (item.code, item.message))),
        limitations=tuple(sorted(limitations, key=lambda item: (item.code, item.message))),
    )


def source_python_files(index: PythonIndex) -> tuple[ParsedPythonFile, ...]:
    return tuple(
        item
        for item in index.files
        if FileRole.PYTHON_SOURCE in item.file.roles and FileRole.PYTHON_TEST not in item.file.roles
    )


def test_python_files(index: PythonIndex) -> tuple[ParsedPythonFile, ...]:
    return tuple(item for item in index.files if FileRole.PYTHON_TEST in item.file.roles)


def files_with_role(files: Iterable[FileRecord], role: FileRole) -> tuple[FileRecord, ...]:
    return tuple(sorted((item for item in files if role in item.roles), key=lambda item: item.path))


def module_aliases(tree: ast.Module) -> dict[str, str]:
    aliases: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                local_name = alias.asname or alias.name.split(".", 1)[0]
                aliases[local_name] = alias.name
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            for alias in node.names:
                if alias.name == "*":
                    continue
                aliases[alias.asname or alias.name] = f"{node.module}.{alias.name}"
    return aliases


def _qualified_name(node: ast.expr, aliases: Mapping[str, str]) -> str | None:
    if isinstance(node, ast.Name):
        return aliases.get(node.id, node.id)
    if isinstance(node, ast.Attribute):
        prefix = _qualified_name(node.value, aliases)
        return f"{prefix}.{node.attr}" if prefix else None
    return None


def qualified_call_name(call: ast.Call, aliases: Mapping[str, str]) -> str | None:
    return _qualified_name(call.func, aliases)


def qualified_expr_name(node: ast.expr, aliases: Mapping[str, str]) -> str | None:
    return _qualified_name(node, aliases)


def parent_map(tree: ast.AST) -> dict[ast.AST, ast.AST]:
    return {child: parent for parent in ast.walk(tree) for child in ast.iter_child_nodes(parent)}


_CALLABLE_SCOPES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)
_NESTED_SCOPES = (*_CALLABLE_SCOPES, ast.ClassDef)
_CONTROL_NODES: tuple[type[ast.AST], ...] = (
    ast.If,
    ast.For,
    ast.AsyncFor,
    ast.While,
    ast.With,
    ast.AsyncWith,
    ast.Try,
    ast.Match,
    ast.TryStar,
)


def lexical_control_depth(callable_node: ast.AST) -> int:
    maximum = 0

    def visit(node: ast.AST, depth: int, *, root: bool = False) -> None:
        nonlocal maximum
        if not root and isinstance(node, _NESTED_SCOPES):
            return
        if isinstance(node, (ast.Try, ast.TryStar)):
            branch_depth = depth + 1
            maximum = max(maximum, branch_depth)
            for statement in (*node.body, *node.orelse, *node.finalbody):
                visit(statement, branch_depth)
            for handler in node.handlers:
                if handler.type is not None:
                    visit(handler.type, branch_depth)
                for statement in handler.body:
                    visit(statement, branch_depth)
            return
        nested_depth = depth + 1 if isinstance(node, _CONTROL_NODES) else depth
        maximum = max(maximum, nested_depth)
        for child in ast.iter_child_nodes(node):
            visit(child, nested_depth)

    visit(callable_node, 0, root=True)
    return maximum


def node_span(node: ast.AST) -> int:
    start = getattr(node, "lineno", None)
    end = getattr(node, "end_lineno", None)
    if not isinstance(start, int) or not isinstance(end, int):
        return 0
    return max(end - start + 1, 0)


def ast_source_line(parsed: ParsedPythonFile, node: ast.AST) -> str:
    line = getattr(node, "lineno", None)
    if not isinstance(line, int) or line < 1 or line > len(parsed.source_lines):
        return ""
    return parsed.source_lines[line - 1].rstrip("\r\n")


def matching_text_lines(file: FileRecord, pattern: re.Pattern[str]) -> tuple[tuple[int, str], ...]:
    matches: list[tuple[int, str]] = []
    for line_number, line in enumerate(file.text.splitlines(), start=1):
        if pattern.search(line):
            matches.append((line_number, redact_text(line)))
    return tuple(matches)


__all__ = [
    "CATALOG_BY_ID",
    "absence_evidence_complete",
    "ast_source_line",
    "catalog_rule",
    "files_with_role",
    "finding_sort_key",
    "is_conventional_ci_path",
    "is_rule_enabled",
    "lexical_control_depth",
    "make_finding",
    "make_limitation",
    "make_location",
    "make_metric",
    "make_result",
    "matching_text_lines",
    "metric_sort_key",
    "module_aliases",
    "node_span",
    "parent_map",
    "qualified_call_name",
    "qualified_expr_name",
    "source_python_files",
    "test_python_files",
]
