"""Maintainability analyzer."""

from __future__ import annotations

import ast
import io
import re
import tokenize
from collections import defaultdict
from collections.abc import Iterable

from ..inventory import FileRecord, FileRole
from ..models import AnalyzerMetadata, AnalyzerResult, Category, Completeness, Location
from ..python_index import ParsedPythonFile
from ._shared import (
    is_rule_enabled,
    lexical_control_depth,
    make_finding,
    make_limitation,
    make_location,
    make_metric,
    make_result,
    node_span,
    parent_map,
    source_python_files,
)
from .base import AnalysisContext, Applicability

_CallableNode = ast.FunctionDef | ast.AsyncFunctionDef
_MARKER = re.compile(r"\b(TODO|FIXME)\b", re.IGNORECASE)


def _scoped_nodes(root: _CallableNode) -> Iterable[ast.AST]:
    pending: list[ast.AST] = list(reversed(root.body))
    while pending:
        node = pending.pop()
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)):
            continue
        yield node
        pending.extend(reversed(list(ast.iter_child_nodes(node))))


def _complexity(function: _CallableNode) -> int:
    value = 1
    branch_nodes = (
        ast.If,
        ast.For,
        ast.AsyncFor,
        ast.While,
        ast.ExceptHandler,
        ast.IfExp,
    )
    for node in _scoped_nodes(function):
        if isinstance(node, branch_nodes):
            value += 1
        elif isinstance(node, ast.BoolOp):
            value += max(len(node.values) - 1, 0)
        elif isinstance(node, ast.Match):
            for case in node.cases:
                pattern = case.pattern
                is_default = (
                    isinstance(pattern, ast.MatchAs)
                    and pattern.pattern is None
                    and pattern.name is None
                    and case.guard is None
                )
                if not is_default:
                    value += 1
    return value


def _callables(parsed: ParsedPythonFile) -> tuple[_CallableNode, ...]:
    return tuple(
        sorted(
            (
                node
                for node in ast.walk(parsed.tree)
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            ),
            key=lambda node: (node.lineno, node.col_offset, node.name),
        )
    )


def _classes(parsed: ParsedPythonFile) -> tuple[ast.ClassDef, ...]:
    return tuple(
        sorted(
            (node for node in ast.walk(parsed.tree) if isinstance(node, ast.ClassDef)),
            key=lambda node: (node.lineno, node.col_offset, node.name),
        )
    )


_IDENTIFIER_FIELDS = frozenset({"id", "arg", "attr", "name", "asname", "module"})


def _structural_value(value: object, field: str | None = None) -> object:
    if isinstance(value, ast.Constant):
        return ("Constant", type(value.value).__name__)
    if isinstance(value, ast.AST):
        values: list[tuple[str, object]] = []
        for child_field, child_value in ast.iter_fields(value):
            if child_field in _IDENTIFIER_FIELDS:
                normalized: object = "<identifier>" if child_value is not None else None
            elif child_field in {"type_comment", "kind"}:
                normalized = None
            else:
                normalized = _structural_value(child_value, child_field)
            values.append((child_field, normalized))
        return (type(value).__name__, tuple(values))
    if isinstance(value, list):
        return tuple(_structural_value(item, field) for item in value)
    if isinstance(value, tuple):
        return tuple(_structural_value(item, field) for item in value)
    if field in _IDENTIFIER_FIELDS and isinstance(value, str):
        return "<identifier>"
    return value


def _duplicate_groups(
    callables: Iterable[tuple[ParsedPythonFile, _CallableNode]],
    minimum_statements: int,
) -> tuple[tuple[tuple[ParsedPythonFile, _CallableNode], ...], ...]:
    grouped: dict[object, list[tuple[ParsedPythonFile, _CallableNode]]] = defaultdict(list)
    for parsed, function in callables:
        if len(function.body) < minimum_statements:
            continue
        grouped[_structural_value(function.body)].append((parsed, function))
    groups = [
        tuple(sorted(items, key=lambda item: (item[0].file.path, item[1].lineno, item[1].name)))
        for items in grouped.values()
        if len(items) >= 2
    ]
    return tuple(
        sorted(
            groups,
            key=lambda group: (group[0][0].file.path, group[0][1].lineno, group[0][1].name),
        )
    )


def _exported_private_names(tree: ast.Module) -> set[str]:
    exported: set[str] = set()
    for node in tree.body:
        value: ast.expr | None = None
        if isinstance(node, (ast.Assign, ast.AnnAssign)) and (
            (
                isinstance(node, ast.Assign)
                and any(
                    isinstance(target, ast.Name) and target.id == "__all__"
                    for target in node.targets
                )
            )
            or (
                isinstance(node, ast.AnnAssign)
                and isinstance(node.target, ast.Name)
                and node.target.id == "__all__"
            )
        ):
            value = node.value
        if isinstance(value, (ast.List, ast.Tuple, ast.Set)):
            exported.update(
                element.value
                for element in value.elts
                if isinstance(element, ast.Constant) and isinstance(element.value, str)
            )
    return exported


def _possible_unused(
    parsed_files: tuple[ParsedPythonFile, ...],
) -> tuple[tuple[ParsedPythonFile, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef], ...]:
    candidates: list[
        tuple[ParsedPythonFile, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef]
    ] = []
    exported_by_path: dict[str, set[str]] = {}
    for parsed in parsed_files:
        exported_by_path[parsed.file.path] = _exported_private_names(parsed.tree)
        for node in parsed.tree.body:
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue
            if (
                not node.name.startswith("_")
                or (node.name.startswith("__") and node.name.endswith("__"))
                or node.decorator_list
            ):
                continue
            candidates.append((parsed, node))

    unused: list[
        tuple[ParsedPythonFile, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef]
    ] = []
    for candidate_parsed, candidate in candidates:
        if candidate.name in exported_by_path[candidate_parsed.file.path]:
            continue
        referenced = False
        own_nodes = set(ast.walk(candidate))
        for parsed in parsed_files:
            for reference_node in ast.walk(parsed.tree):
                if parsed is candidate_parsed and reference_node in own_nodes:
                    continue
                if (
                    isinstance(reference_node, ast.Name) and reference_node.id == candidate.name
                ) or (
                    isinstance(reference_node, ast.Attribute)
                    and reference_node.attr == candidate.name
                ):
                    referenced = True
                    break
            if referenced:
                break
        if not referenced:
            unused.append((candidate_parsed, candidate))
    return tuple(sorted(unused, key=lambda item: (item[0].file.path, item[1].lineno, item[1].name)))


def _comment_markers(
    files: Iterable[FileRecord],
) -> tuple[tuple[FileRecord, str, int, int, int], ...]:
    markers: list[tuple[FileRecord, str, int, int, int]] = []
    for file in sorted(files, key=lambda item: item.path):
        if FileRole.PYTHON_SOURCE not in file.roles or FileRole.PYTHON_TEST in file.roles:
            continue
        try:
            tokens = tokenize.generate_tokens(io.StringIO(file.text).readline)
            for token in tokens:
                if token.type != tokenize.COMMENT:
                    continue
                for match in _MARKER.finditer(token.string):
                    markers.append(
                        (
                            file,
                            match.group(1).upper(),
                            token.start[0],
                            token.start[1] + match.start(),
                            token.start[1] + match.end(),
                        )
                    )
        except (IndentationError, SyntaxError, tokenize.TokenError):
            continue
    return tuple(markers)


def _import_display(node: ast.Import | ast.ImportFrom) -> str:
    names = ", ".join(
        alias.name + (f" as {alias.asname}" if alias.asname else "") for alias in node.names
    )
    if isinstance(node, ast.Import):
        return f"import {names}"
    prefix = "." * node.level + (node.module or "")
    return f"from {prefix} import {names}"


def _import_key(node: ast.Import | ast.ImportFrom) -> tuple[object, ...]:
    if isinstance(node, ast.Import):
        return ("import", tuple((alias.name, alias.asname) for alias in node.names))
    return (
        "from",
        node.level,
        node.module,
        tuple((alias.name, alias.asname) for alias in node.names),
    )


def _is_type_checking_test(test: ast.expr) -> bool:
    return (isinstance(test, ast.Name) and test.id == "TYPE_CHECKING") or (
        isinstance(test, ast.Attribute) and test.attr == "TYPE_CHECKING"
    )


def _exception_names(node: ast.expr | None) -> set[str]:
    if node is None:
        return set()
    if isinstance(node, ast.Name):
        return {node.id}
    if isinstance(node, ast.Attribute):
        return {node.attr}
    if isinstance(node, ast.Tuple):
        return set().union(*(_exception_names(item) for item in node.elts))
    return set()


def _is_optional_import(node: ast.Import | ast.ImportFrom, parents: dict[ast.AST, ast.AST]) -> bool:
    parent = parents.get(node)
    if not isinstance(parent, (ast.Try, ast.TryStar)) or node not in parent.body:
        return False
    caught = set().union(*(_exception_names(handler.type) for handler in parent.handlers))
    return bool(caught & {"ImportError", "ModuleNotFoundError"})


def _is_type_checking_import(
    node: ast.Import | ast.ImportFrom, parents: dict[ast.AST, ast.AST]
) -> bool:
    parent = parents.get(node)
    return (
        isinstance(parent, ast.If) and node in parent.body and _is_type_checking_test(parent.test)
    )


def _import_issues(
    parsed_files: tuple[ParsedPythonFile, ...],
) -> tuple[tuple[ParsedPythonFile, ast.Import | ast.ImportFrom, str], ...]:
    issues: list[tuple[ParsedPythonFile, ast.Import | ast.ImportFrom, str]] = []
    for parsed in parsed_files:
        parents = parent_map(parsed.tree)
        seen: set[tuple[object, ...]] = set()
        imports = sorted(
            (
                node
                for node in ast.walk(parsed.tree)
                if isinstance(node, (ast.Import, ast.ImportFrom))
            ),
            key=lambda node: (node.lineno, node.col_offset),
        )
        for node in imports:
            display = _import_display(node)
            key = _import_key(node)
            if key in seen:
                issues.append((parsed, node, f"duplicate import: {display}"))
            else:
                seen.add(key)
            if isinstance(node, ast.ImportFrom) and any(alias.name == "*" for alias in node.names):
                issues.append((parsed, node, f"wildcard import: {display}"))
            if (
                not isinstance(parents.get(node), ast.Module)
                and not _is_type_checking_import(node, parents)
                and not _is_optional_import(node, parents)
            ):
                issues.append((parsed, node, f"non-top-level import: {display}"))
    return tuple(sorted(issues, key=lambda item: (item[0].file.path, item[1].lineno, item[2])))


class MaintainabilityAnalyzer:
    metadata = AnalyzerMetadata(
        id="maintainability",
        version="1.0.0",
        category=Category.MAINTAINABILITY,
        rule_ids=tuple(f"RI-MAINT-{index:03}" for index in range(1, 10)),
        capabilities=("python-ast", "python-tokens", "static-reference-index"),
    )

    def applies(self, context: AnalysisContext) -> Applicability:
        has_python = any(
            FileRole.PYTHON_SOURCE in file.roles or FileRole.PYTHON_TEST in file.roles
            for file in context.inventory.files
        )
        if not has_python:
            return Applicability(
                False,
                Completeness.UNAVAILABLE,
                ("No retained Python evidence is available",),
            )
        if not context.python_index.files or context.python_index.completeness in {
            Completeness.UNAVAILABLE,
            Completeness.SKIPPED,
        }:
            return Applicability(
                True,
                Completeness.UNAVAILABLE,
                ("Python AST evidence is unavailable",),
            )
        if (
            context.inventory.completeness is Completeness.PARTIAL
            or context.python_index.completeness is Completeness.PARTIAL
        ):
            return Applicability(
                True,
                Completeness.PARTIAL,
                ("Python inventory or AST evidence is incomplete",),
            )
        return Applicability(True, Completeness.AVAILABLE)

    def analyze(self, context: AnalysisContext) -> AnalyzerResult:
        applicability = self.applies(context)
        parsed_files = source_python_files(context.python_index)
        ast_available = bool(
            context.python_index.files
        ) and context.python_index.completeness not in {
            Completeness.UNAVAILABLE,
            Completeness.SKIPPED,
        }
        ast_completeness = (
            context.python_index.completeness if ast_available else Completeness.UNAVAILABLE
        )
        ast_limitations = (
            ("Python AST evidence is incomplete",)
            if ast_completeness is Completeness.PARTIAL
            else (("Python AST evidence is unavailable",) if not ast_available else ())
        )

        callable_records = tuple(
            (parsed, function) for parsed in parsed_files for function in _callables(parsed)
        )
        class_records = tuple(
            (parsed, class_node) for parsed in parsed_files for class_node in _classes(parsed)
        )
        complexities = [
            (_complexity(function), parsed, function) for parsed, function in callable_records
        ]
        function_spans = [
            (node_span(function), parsed, function) for parsed, function in callable_records
        ]
        class_spans = [(node_span(node), parsed, node) for parsed, node in class_records]
        module_spans = [(parsed.file.line_count, parsed) for parsed in parsed_files]
        nesting = [
            (lexical_control_depth(function), parsed, function)
            for parsed, function in callable_records
        ]
        duplicate_groups = _duplicate_groups(
            callable_records,
            context.config.thresholds.duplicate_statements,
        )
        possible_unused = _possible_unused(parsed_files)
        markers = _comment_markers(context.inventory.files)
        import_issues = _import_issues(parsed_files)

        findings = []
        thresholds = context.config.thresholds
        if ast_available and is_rule_enabled(context.config, "RI-MAINT-001"):
            for value, parsed, function in complexities:
                if value >= thresholds.complexity:
                    findings.append(
                        make_finding(
                            self.metadata,
                            "RI-MAINT-001",
                            location=make_location(parsed, function),
                            evidence=f"{function.name} has static cyclomatic complexity {value}",
                            explanation_detail=f"Measured static complexity: {value}.",
                        )
                    )
        if ast_available and is_rule_enabled(context.config, "RI-MAINT-002"):
            for value, parsed, function in function_spans:
                if value > thresholds.function_loc:
                    findings.append(
                        make_finding(
                            self.metadata,
                            "RI-MAINT-002",
                            location=make_location(parsed, function),
                            evidence=f"{function.name} spans {value} physical lines",
                        )
                    )
        if ast_available and is_rule_enabled(context.config, "RI-MAINT-003"):
            for value, parsed, class_node in class_spans:
                if value > thresholds.class_loc:
                    findings.append(
                        make_finding(
                            self.metadata,
                            "RI-MAINT-003",
                            location=make_location(parsed, class_node),
                            evidence=f"{class_node.name} spans {value} physical lines",
                        )
                    )
        if ast_available and is_rule_enabled(context.config, "RI-MAINT-004"):
            for value, parsed in module_spans:
                if value > thresholds.module_loc:
                    findings.append(
                        make_finding(
                            self.metadata,
                            "RI-MAINT-004",
                            location=Location(path=parsed.file.path, start_line=1, end_line=value),
                            evidence=f"module spans {value} physical lines",
                        )
                    )
        if ast_available and is_rule_enabled(context.config, "RI-MAINT-005"):
            for value, parsed, function in nesting:
                if value >= thresholds.nesting_depth:
                    findings.append(
                        make_finding(
                            self.metadata,
                            "RI-MAINT-005",
                            location=make_location(parsed, function),
                            evidence=f"{function.name} has lexical control-flow depth {value}",
                        )
                    )
        if ast_available and is_rule_enabled(context.config, "RI-MAINT-006"):
            for group in duplicate_groups:
                representative_parsed, representative = group[0]
                names = ", ".join(item[1].name for item in group)
                findings.append(
                    make_finding(
                        self.metadata,
                        "RI-MAINT-006",
                        location=make_location(representative_parsed, representative),
                        evidence=f"duplicated-looking group: {names}",
                        explanation_detail="This is duplicated-looking structure.",
                    )
                )
        if ast_available and is_rule_enabled(context.config, "RI-MAINT-007"):
            for parsed, definition in possible_unused:
                findings.append(
                    make_finding(
                        self.metadata,
                        "RI-MAINT-007",
                        location=make_location(parsed, definition),
                        evidence=f"possible unused definition: {definition.name}",
                        explanation_detail="This is a possible unused definition.",
                    )
                )
        if context.inventory.completeness not in {
            Completeness.UNAVAILABLE,
            Completeness.SKIPPED,
        } and is_rule_enabled(context.config, "RI-MAINT-008"):
            for file, marker, line, start_column, end_column in markers:
                findings.append(
                    make_finding(
                        self.metadata,
                        "RI-MAINT-008",
                        location=Location(
                            path=file.path,
                            start_line=line,
                            end_line=line,
                            start_column=start_column,
                            end_column=end_column,
                        ),
                        evidence=f"{marker} marker in Python comment",
                    )
                )
        if ast_available and is_rule_enabled(context.config, "RI-MAINT-009"):
            for parsed, node, evidence in import_issues:
                findings.append(
                    make_finding(
                        self.metadata,
                        "RI-MAINT-009",
                        location=make_location(parsed, node),
                        evidence=evidence,
                    )
                )

        ast_values: dict[str, int] = {
            "maintainability.function_count": len(callable_records),
            "maintainability.max_complexity": max((item[0] for item in complexities), default=0),
            "maintainability.max_function_loc": max(
                (item[0] for item in function_spans), default=0
            ),
            "maintainability.max_class_loc": max((item[0] for item in class_spans), default=0),
            "maintainability.max_module_loc": max((item[0] for item in module_spans), default=0),
            "maintainability.max_nesting_depth": max((item[0] for item in nesting), default=0),
            "maintainability.duplicate_structure_groups": len(duplicate_groups),
            "maintainability.possible_unused_definitions": len(possible_unused),
            "maintainability.import_issues": len(import_issues),
        }
        metrics = [
            make_metric(
                self.metadata,
                metric_id,
                value if ast_available else None,
                unit=(
                    "lines"
                    if metric_id
                    in {
                        "maintainability.max_function_loc",
                        "maintainability.max_class_loc",
                        "maintainability.max_module_loc",
                    }
                    else "count"
                ),
                provenance="Retained Python AST evidence",
                completeness=ast_completeness,
                limitations=ast_limitations,
            )
            for metric_id, value in ast_values.items()
        ]
        token_completeness = context.inventory.completeness
        token_available = token_completeness not in {
            Completeness.UNAVAILABLE,
            Completeness.SKIPPED,
        }
        metrics.append(
            make_metric(
                self.metadata,
                "maintainability.todo_fixme_markers",
                len(markers) if token_available else None,
                unit="count",
                provenance="Retained Python comment-token evidence",
                completeness=token_completeness,
                limitations=(
                    ("Python inventory evidence is incomplete",)
                    if token_completeness is Completeness.PARTIAL
                    else ()
                ),
            )
        )
        limitations = tuple(
            make_limitation(self.metadata, "maintainability-evidence", message)
            for message in applicability.limitations
        )
        return make_result(
            self.metadata,
            applicability.completeness,
            metrics=metrics,
            findings=findings,
            limitations=limitations,
        )


ANALYZER = MaintainabilityAnalyzer()

__all__ = ["ANALYZER", "MaintainabilityAnalyzer"]
