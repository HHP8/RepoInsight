"""Testing-evidence analyzer."""

from __future__ import annotations

import ast
import configparser
import re
import tomllib
from pathlib import PurePosixPath

from ..inventory import FileRecord, FileRole
from ..models import AnalyzerMetadata, AnalyzerResult, Category, Completeness, Location, Severity
from ._shared import (
    absence_evidence_complete,
    files_with_role,
    is_conventional_ci_path,
    is_rule_enabled,
    make_finding,
    make_limitation,
    make_metric,
    make_result,
    test_python_files,
)
from .base import AnalysisContext, Applicability

_ROOT_TEST = re.compile(r"^(?:test_.+|.+_test)\.py$", re.IGNORECASE)
_CI_TEST_COMMAND = re.compile(
    r"^(?:(?:uv|poetry|pipenv)\s+run\s+)?(?:pytest\b|"
    r"python(?:\d+(?:\.\d+)*)?\s+-m\s+(?:pytest|unittest)\b|tox\b|nox\b|"
    r"hatch\s+run\s+(?:test|pytest)\b|make\s+test\b)",
    re.IGNORECASE,
)
_COVERAGE = re.compile(r"(?:\bcoverage\b|pytest-cov|\[tool\.coverage(?:\.|\]))", re.IGNORECASE)
_RUNNER_CONFIG_NAMES = frozenset(
    {"noxfile.py", "pipfile", "pyproject.toml", "pytest.ini", "setup.cfg", "tox.ini"}
)
_COVERAGE_CONFIG_NAMES = frozenset(
    {
        ".coveragerc",
        "codecov.yaml",
        "codecov.yml",
        "coverage.toml",
        "pipfile",
        "pyproject.toml",
        "requirements.txt",
        "setup.cfg",
        "tox.ini",
    }
)


def _safe_test_root(value: str) -> str | None:
    normalized = value.strip().strip("\"'").replace("\\", "/").strip("/")
    path = PurePosixPath(normalized)
    if (
        not normalized
        or path.is_absolute()
        or ".." in path.parts
        or "." in path.parts
        or ":" in normalized
    ):
        return None
    return str(path).casefold()


def _configured_test_roots(files: tuple[FileRecord, ...]) -> tuple[str, ...]:
    roots: set[str] = set()
    for file in files:
        name = file.path.casefold()
        if name == "pyproject.toml":
            try:
                loaded = tomllib.loads(file.text)
                pytest_options = loaded.get("tool", {}).get("pytest", {}).get("ini_options", {})
                raw = pytest_options.get("testpaths", ())
            except (AttributeError, TypeError, tomllib.TOMLDecodeError):
                continue
            values = raw.split() if isinstance(raw, str) else raw
            if isinstance(values, list):
                for value in values:
                    if isinstance(value, str) and (safe := _safe_test_root(value)) is not None:
                        roots.add(safe)
        elif name in {"pytest.ini", "tox.ini", "setup.cfg"}:
            parser = configparser.ConfigParser(interpolation=None, strict=False)
            try:
                parser.read_string(file.text)
            except (configparser.Error, ValueError):
                continue
            sections = ("tool:pytest", "pytest") if name == "setup.cfg" else ("pytest",)
            for section in sections:
                raw = parser.get(section, "testpaths", fallback="")
                for value in raw.split():
                    if (safe := _safe_test_root(value)) is not None:
                        roots.add(safe)
    return tuple(sorted(roots))


def _is_recognized_test(file: FileRecord, configured_roots: tuple[str, ...]) -> bool:
    if FileRole.PYTHON_TEST not in file.roles:
        return False
    folded = file.path.casefold()
    parts = folded.split("/")
    if parts[0] in {"tests", "test"}:
        return True
    if len(parts) == 1 and _ROOT_TEST.fullmatch(parts[0]):
        return True
    return any(folded == root or folded.startswith(f"{root}/") for root in configured_roots)


def _path_is_test_like(path: str) -> bool:
    folded = path.casefold()
    parts = folded.split("/")
    name = parts[-1]
    return name.endswith(".py") and (
        "tests" in parts or "test" in parts or name.startswith("test_") or name.endswith("_test.py")
    )


def _path_is_source_python(path: str) -> bool:
    return path.casefold().endswith(".py") and not _path_is_test_like(path)


def _path_could_be_recognized_test(path: str, configured_roots: tuple[str, ...]) -> bool:
    folded = path.casefold().strip("/")
    parts = folded.split("/") if folded else []
    if _path_is_test_like(folded) and (
        (parts and parts[0] in {"test", "tests"})
        or (len(parts) == 1 and _ROOT_TEST.fullmatch(parts[0]))
    ):
        return True
    return any(
        folded == root or folded.startswith(f"{root}/") or root.startswith(f"{folded}/")
        for root in configured_roots
    )


def _framework_evidence(
    context: AnalysisContext,
    test_files: tuple[FileRecord, ...],
    *,
    include_ast: bool,
) -> bool:
    test_paths = {file.path for file in test_files}
    if include_ast:
        for parsed in test_python_files(context.python_index):
            if parsed.file.path not in test_paths:
                continue
            for node in ast.walk(parsed.tree):
                if isinstance(node, ast.Import) and any(
                    alias.name.split(".", 1)[0] in {"pytest", "unittest"} for alias in node.names
                ):
                    return True
                if (
                    isinstance(node, ast.ImportFrom)
                    and node.module is not None
                    and node.module.split(".", 1)[0] in {"pytest", "unittest"}
                ):
                    return True
    for file in context.inventory.files:
        name = file.path.casefold().rsplit("/", 1)[-1]
        if name in {"tox.ini", "noxfile.py", "pytest.ini"}:
            return True
        if FileRole.DEPENDENCY in file.roles or FileRole.PACKAGING in file.roles:
            lowered = file.text.casefold()
            if re.search(r"\b(?:pytest|unittest|tox|nox)\b|\[tool\.pytest", lowered):
                return True
    return False


def _ci_has_test_command(text: str) -> bool:
    for raw_line in text.splitlines():
        line = raw_line.strip()
        line = re.sub(r"^(?:-\s*)?run\s*:\s*", "", line, flags=re.IGNORECASE)
        for segment in re.split(r"&&|\|\||;", line):
            if _CI_TEST_COMMAND.search(segment.strip()):
                return True
    return False


def _coverage_evidence(files: tuple[FileRecord, ...]) -> bool:
    for file in files:
        name = file.path.casefold().rsplit("/", 1)[-1]
        if name in {".coveragerc", "coverage.toml", "codecov.yml", "codecov.yaml"}:
            return True
        if (
            FileRole.DEPENDENCY in file.roles
            or FileRole.PACKAGING in file.roles
            or (FileRole.CI in file.roles and is_conventional_ci_path(file.path))
        ) and _COVERAGE.search(file.text):
            return True
    return False


class TestingAnalyzer:
    metadata = AnalyzerMetadata(
        id="testing",
        version="1.0.0",
        category=Category.TESTING,
        rule_ids=tuple(f"RI-TEST-{index:03}" for index in range(1, 7)),
        capabilities=("inventory", "static-manifest-text", "static-ci-text"),
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
                ("No retained Python source or test evidence is available",),
            )
        if context.inventory.completeness in {
            Completeness.UNAVAILABLE,
            Completeness.SKIPPED,
        }:
            return Applicability(
                True,
                Completeness.UNAVAILABLE,
                ("Python inventory evidence is unavailable",),
            )
        if (
            context.inventory.completeness is Completeness.PARTIAL
            or context.python_index.completeness
            in {
                Completeness.PARTIAL,
                Completeness.UNAVAILABLE,
                Completeness.SKIPPED,
            }
        ):
            return Applicability(
                True,
                Completeness.PARTIAL,
                ("Python inventory or test-framework evidence is incomplete",),
            )
        return Applicability(True, Completeness.AVAILABLE)

    def analyze(self, context: AnalysisContext) -> AnalyzerResult:
        applicability = self.applies(context)
        inventory_available = context.inventory.completeness not in {
            Completeness.UNAVAILABLE,
            Completeness.SKIPPED,
        }
        files = context.inventory.files
        ast_usable = context.python_index.completeness not in {
            Completeness.UNAVAILABLE,
            Completeness.SKIPPED,
        }
        configured_roots = _configured_test_roots(files) if inventory_available else ()
        all_test_files = tuple(file for file in files if FileRole.PYTHON_TEST in file.roles)
        recognized = tuple(
            file for file in all_test_files if _is_recognized_test(file, configured_roots)
        )
        parsed_test_paths = (
            {parsed.file.path for parsed in test_python_files(context.python_index)}
            if ast_usable
            else set()
        )
        test_ast_complete = all(file.path in parsed_test_paths for file in all_test_files)
        source_files = tuple(
            file
            for file in files
            if FileRole.PYTHON_SOURCE in file.roles and FileRole.PYTHON_TEST not in file.roles
        )
        source_loc = sum(file.line_count for file in source_files)
        test_loc = sum(file.line_count for file in recognized)
        ratio = test_loc / source_loc if source_loc else None
        framework = (
            _framework_evidence(context, all_test_files, include_ast=ast_usable)
            if inventory_available
            else False
        )
        ci_files = (
            tuple(
                file
                for file in files_with_role(files, FileRole.CI)
                if is_conventional_ci_path(file.path)
            )
            if inventory_available
            else ()
        )
        ci_test_evidence = any(_ci_has_test_command(file.text) for file in ci_files)
        coverage = _coverage_evidence(files) if inventory_available else False
        recognized_absence_complete = absence_evidence_complete(
            context.inventory,
            lambda path: _path_could_be_recognized_test(path, configured_roots),
        )
        ratio_evidence_complete = absence_evidence_complete(
            context.inventory,
            lambda path: (
                _path_is_source_python(path)
                or _path_could_be_recognized_test(path, configured_roots)
            ),
        )
        runner_absence_complete = absence_evidence_complete(
            context.inventory,
            lambda path: (
                _path_is_test_like(path)
                or path.casefold().rsplit("/", 1)[-1] in _RUNNER_CONFIG_NAMES
            ),
        )
        ci_absence_complete = absence_evidence_complete(
            context.inventory,
            is_conventional_ci_path,
        )
        coverage_absence_complete = absence_evidence_complete(
            context.inventory,
            lambda path: (
                is_conventional_ci_path(path)
                or path.casefold().rsplit("/", 1)[-1] in _COVERAGE_CONFIG_NAMES
            ),
        )

        findings = []
        if (
            inventory_available
            and not recognized
            and recognized_absence_complete
            and is_rule_enabled(context.config, "RI-TEST-001")
        ):
            findings.append(
                make_finding(
                    self.metadata,
                    "RI-TEST-001",
                    evidence="recognized Python test files: 0",
                )
            )
        if (
            inventory_available
            and ratio is not None
            and ratio_evidence_complete
            and is_rule_enabled(context.config, "RI-TEST-002")
        ):
            if ratio < context.config.thresholds.test_ratio_medium:
                findings.append(
                    make_finding(
                        self.metadata,
                        "RI-TEST-002",
                        evidence=f"static test/source LOC ratio: {ratio:.6f}",
                        explanation_detail="This is a static LOC proxy, not runtime coverage.",
                    )
                )
            elif ratio < context.config.thresholds.test_ratio_low:
                findings.append(
                    make_finding(
                        self.metadata,
                        "RI-TEST-002",
                        evidence=f"static test/source LOC ratio: {ratio:.6f}",
                        explanation_detail="This is a static LOC proxy, not runtime coverage.",
                        severity=Severity.LOW,
                        score_impact=6.0,
                    )
                )
        if (
            inventory_available
            and all_test_files
            and not recognized
            and recognized_absence_complete
            and is_rule_enabled(context.config, "RI-TEST-003")
        ):
            first = min(all_test_files, key=lambda file: file.path)
            findings.append(
                make_finding(
                    self.metadata,
                    "RI-TEST-003",
                    location=Location(path=first.path, start_line=1),
                    evidence=f"test-like files outside recognized roots: {len(all_test_files)}",
                )
            )
        if (
            inventory_available
            and all_test_files
            and not framework
            and test_ast_complete
            and runner_absence_complete
            and is_rule_enabled(context.config, "RI-TEST-004")
        ):
            findings.append(
                make_finding(
                    self.metadata,
                    "RI-TEST-004",
                    evidence="recognized static test-runner evidence: false",
                )
            )
        if (
            inventory_available
            and ci_files
            and not ci_test_evidence
            and ci_absence_complete
            and is_rule_enabled(context.config, "RI-TEST-005")
        ):
            findings.append(
                make_finding(
                    self.metadata,
                    "RI-TEST-005",
                    location=Location(path=ci_files[0].path, start_line=1),
                    evidence="recognized CI test invocation: false",
                )
            )
        if (
            inventory_available
            and all_test_files
            and not coverage
            and coverage_absence_complete
            and is_rule_enabled(context.config, "RI-TEST-006")
        ):
            findings.append(
                make_finding(
                    self.metadata,
                    "RI-TEST-006",
                    evidence="static coverage configuration or invocation evidence: false",
                )
            )

        metric_completeness = applicability.completeness
        metric_limitations = applicability.limitations
        metrics = [
            make_metric(
                self.metadata,
                "testing.source_loc",
                source_loc if inventory_available else None,
                unit="lines",
                provenance="Retained non-test Python inventory",
                completeness=metric_completeness,
                limitations=metric_limitations,
            ),
            make_metric(
                self.metadata,
                "testing.test_loc",
                test_loc if inventory_available else None,
                unit="lines",
                provenance="Recognized Python test inventory",
                completeness=metric_completeness,
                limitations=metric_limitations,
            ),
            make_metric(
                self.metadata,
                "testing.test_files",
                len(all_test_files) if inventory_available else None,
                unit="count",
                provenance="Retained test-like Python inventory",
                completeness=metric_completeness,
                limitations=metric_limitations,
            ),
            make_metric(
                self.metadata,
                "testing.recognized_test_files",
                len(recognized) if inventory_available else None,
                unit="count",
                provenance="Conventional and statically configured test roots",
                completeness=metric_completeness,
                limitations=metric_limitations,
            ),
            make_metric(
                self.metadata,
                "testing.framework_evidence",
                (
                    None
                    if all_test_files and not ast_usable and not framework
                    else (framework if inventory_available else None)
                ),
                unit=None,
                provenance="Test AST imports and static runner configuration",
                completeness=(
                    Completeness.UNAVAILABLE
                    if all_test_files and not ast_usable and not framework
                    else metric_completeness
                ),
                limitations=(
                    ("Test AST evidence is unavailable",)
                    if all_test_files and not ast_usable and not framework
                    else metric_limitations
                ),
            ),
            make_metric(
                self.metadata,
                "testing.ci_test_evidence",
                ci_test_evidence if inventory_available else None,
                unit=None,
                provenance="Conventional CI text",
                completeness=metric_completeness,
                limitations=metric_limitations,
            ),
            make_metric(
                self.metadata,
                "testing.coverage_evidence",
                coverage if inventory_available else None,
                unit=None,
                provenance="Static coverage configuration and CI text",
                completeness=metric_completeness,
                limitations=metric_limitations,
            ),
        ]
        ratio_completeness = (
            (Completeness.PARTIAL if not ratio_evidence_complete else metric_completeness)
            if source_loc and inventory_available
            else Completeness.UNAVAILABLE
        )
        ratio_limitations = (
            (
                (*metric_limitations, "Skipped source or test evidence can change the ratio")
                if not ratio_evidence_complete
                else metric_limitations
            )
            if source_loc and inventory_available
            else ("No non-test Python source LOC is available for the ratio",)
        )
        metrics.append(
            make_metric(
                self.metadata,
                "testing.test_source_ratio",
                ratio if source_loc and inventory_available else None,
                unit="ratio",
                provenance="Recognized test LOC divided by non-test source LOC",
                completeness=ratio_completeness,
                limitations=ratio_limitations,
            )
        )
        limitations = tuple(
            make_limitation(self.metadata, "testing-evidence", message)
            for message in applicability.limitations
        )
        return make_result(
            self.metadata,
            applicability.completeness,
            metrics=metrics,
            findings=findings,
            limitations=limitations,
        )


ANALYZER = TestingAnalyzer()

__all__ = ["ANALYZER", "TestingAnalyzer"]
