"""Documentation-evidence analyzer."""

from __future__ import annotations

import ast
import re

from ..inventory import FileRecord, FileRole
from ..models import AnalyzerMetadata, AnalyzerResult, Category, Completeness, Location
from ..python_index import ParsedPythonFile
from ._shared import (
    absence_evidence_complete,
    files_with_role,
    is_rule_enabled,
    make_finding,
    make_limitation,
    make_metric,
    make_result,
    source_python_files,
)
from .base import AnalysisContext, Applicability

_README_NAME = re.compile(r"^readme(?:\.(?:md|markdown|rst|txt))?$", re.IGNORECASE)
_ATX_HEADING = re.compile(r"^\s{0,3}#{1,6}\s+(.+?)\s*#*\s*$")
_PURPOSE_HEADINGS = ("overview", "about", "introduction", "purpose", "what is")
_INSTALL_HEADINGS = ("installation", "install", "setup", "getting started", "requirements")
_USAGE_HEADINGS = ("usage", "quickstart", "quick start", "how to use", "examples")
_INSTALL_COMMAND = re.compile(
    r"\b(?:pip(?:x)?\s+install|uv\s+(?:add|sync)|poetry\s+install|conda\s+install)\b",
    re.IGNORECASE,
)
_REALISTIC_CODE = re.compile(
    r"(?:\bpython(?:\d+(?:\.\d+)*)?\s+-m\b|\b(?:pip|uv|poetry)\s+|"
    r"^\s*(?:from\s+\w[\w.]*\s+import|import\s+\w|[A-Za-z_]\w*\s*=|[A-Za-z_]\w*\s*\())",
    re.IGNORECASE | re.MULTILINE,
)
_FENCED_BLOCK = re.compile(r"```[^\n]*\n(.*?)```|~~~[^\n]*\n(.*?)~~~", re.DOTALL)


def _path_is_readme(path: str) -> bool:
    return "/" not in path and _README_NAME.fullmatch(path) is not None


def _path_is_contribution(path: str) -> bool:
    return path.casefold().rsplit("/", 1)[-1].startswith("contributing")


def _path_is_changelog(path: str) -> bool:
    return (
        path.casefold()
        .rsplit("/", 1)[-1]
        .startswith(("changelog", "changes", "release-notes", "release_notes"))
    )


def _path_is_example(path: str) -> bool:
    parts = path.casefold().split("/")
    return "examples" in parts or "example" in parts


def _path_is_source_python(path: str) -> bool:
    folded = path.casefold()
    parts = folded.split("/")
    name = parts[-1]
    return name.endswith(".py") and not (
        "tests" in parts or "test" in parts or name.startswith("test_") or name.endswith("_test.py")
    )


def _root_readme(files: tuple[FileRecord, ...]) -> FileRecord | None:
    candidates = [
        file
        for file in files
        if "/" not in file.path and _README_NAME.fullmatch(file.path) is not None
    ]
    return min(candidates, key=lambda file: file.path.casefold()) if candidates else None


def _headings(text: str) -> tuple[str, ...]:
    lines = text.splitlines()
    headings: list[str] = []
    for index, line in enumerate(lines):
        match = _ATX_HEADING.match(line)
        if match is not None:
            headings.append(" ".join(match.group(1).casefold().split()))
        elif (
            index > 0
            and line.strip()
            and set(line.strip()) <= {"=", "-", "~", "^"}
            and len(line.strip()) >= 3
        ):
            headings.append(" ".join(lines[index - 1].strip().casefold().split()))
    return tuple(headings)


def _has_heading(headings: tuple[str, ...], vocabulary: tuple[str, ...]) -> bool:
    return any(
        heading == term or heading.startswith(f"{term} ")
        for heading in headings
        for term in vocabulary
    )


def _readme_example(text: str) -> bool:
    for match in _FENCED_BLOCK.finditer(text):
        block = match.group(1) or match.group(2) or ""
        if block.strip() and _REALISTIC_CODE.search(block):
            return True
    indented = "\n".join(line[4:] for line in text.splitlines() if line.startswith("    "))
    return bool(indented.strip() and _REALISTIC_CODE.search(indented))


def _readme_evidence(readme: FileRecord | None) -> tuple[bool, bool, bool, bool]:
    if readme is None:
        return False, False, False, False
    headings = _headings(readme.text)
    example = _readme_example(readme.text)
    purpose = _has_heading(headings, _PURPOSE_HEADINGS)
    installation = _has_heading(headings, _INSTALL_HEADINGS) or bool(
        _INSTALL_COMMAND.search(readme.text)
    )
    usage = _has_heading(headings, _USAGE_HEADINGS) or example
    return purpose, installation, usage, example


_DocumentableNode = ast.Module | ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef


def _public_api_nodes(parsed: ParsedPythonFile) -> tuple[_DocumentableNode, ...]:
    nodes: list[_DocumentableNode] = [parsed.tree]
    for node in parsed.tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and not node.name.startswith(
            "_"
        ):
            nodes.append(node)
        elif isinstance(node, ast.ClassDef) and not node.name.startswith("_"):
            nodes.append(node)
            nodes.extend(
                child
                for child in node.body
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef))
                and not child.name.startswith("_")
            )
    return tuple(nodes)


def _docstring_counts(parsed_files: tuple[ParsedPythonFile, ...]) -> tuple[int, int]:
    nodes = tuple(node for parsed in parsed_files for node in _public_api_nodes(parsed))
    return len(nodes), sum(ast.get_docstring(node, clean=False) is not None for node in nodes)


class DocumentationAnalyzer:
    metadata = AnalyzerMetadata(
        id="documentation",
        version="1.0.0",
        category=Category.DOCUMENTATION,
        rule_ids=tuple(f"RI-DOC-{index:03}" for index in range(1, 7)),
        capabilities=("inventory", "python-ast", "readme-text"),
    )

    def applies(self, context: AnalysisContext) -> Applicability:
        if context.inventory.completeness in {
            Completeness.UNAVAILABLE,
            Completeness.SKIPPED,
        }:
            return Applicability(
                False,
                Completeness.UNAVAILABLE,
                ("Repository root inventory is unavailable",),
            )
        has_python_source = any(
            FileRole.PYTHON_SOURCE in file.roles and FileRole.PYTHON_TEST not in file.roles
            for file in context.inventory.files
        )
        docstring_incomplete = has_python_source and context.python_index.completeness in {
            Completeness.PARTIAL,
            Completeness.UNAVAILABLE,
            Completeness.SKIPPED,
        }
        if context.inventory.completeness is Completeness.PARTIAL or docstring_incomplete:
            return Applicability(
                True,
                Completeness.PARTIAL,
                ("Repository inventory or public-docstring AST evidence is incomplete",),
            )
        return Applicability(True, Completeness.AVAILABLE)

    def analyze(self, context: AnalysisContext) -> AnalyzerResult:
        applicability = self.applies(context)
        files = context.inventory.files
        readme = _root_readme(files)
        purpose, installation, usage, readme_example = _readme_evidence(readme)
        contribution = bool(files_with_role(files, FileRole.CONTRIBUTION_GUIDE))
        changelog = bool(files_with_role(files, FileRole.CHANGELOG))
        examples = bool(files_with_role(files, FileRole.EXAMPLE)) or readme_example

        parsed_source = source_python_files(context.python_index)
        ast_trusted = bool(parsed_source) and context.python_index.completeness not in {
            Completeness.UNAVAILABLE,
            Completeness.SKIPPED,
        }
        public_count, documented_count = _docstring_counts(parsed_source) if ast_trusted else (0, 0)
        docstring_rate = documented_count / public_count if public_count else None
        readme_absence_complete = absence_evidence_complete(
            context.inventory,
            _path_is_readme,
        )
        contribution_absence_complete = absence_evidence_complete(
            context.inventory,
            _path_is_contribution,
        )
        changelog_absence_complete = absence_evidence_complete(
            context.inventory,
            _path_is_changelog,
        )
        example_absence_complete = absence_evidence_complete(
            context.inventory,
            _path_is_example,
        )
        docstring_evidence_complete = absence_evidence_complete(
            context.inventory,
            _path_is_source_python,
        )
        if ast_trusted:
            doc_completeness = (
                Completeness.PARTIAL
                if context.python_index.completeness is Completeness.PARTIAL
                or not docstring_evidence_complete
                else Completeness.AVAILABLE
            )
            doc_limitations = (
                ("Public-docstring AST evidence is incomplete",)
                if doc_completeness is Completeness.PARTIAL
                else ()
            )
        else:
            doc_completeness = Completeness.UNAVAILABLE
            doc_limitations = (
                "No parsed non-test Python module is available for public-docstring metrics",
            )

        findings = []
        if (
            readme is None
            and readme_absence_complete
            and is_rule_enabled(context.config, "RI-DOC-001")
        ):
            findings.append(
                make_finding(
                    self.metadata,
                    "RI-DOC-001",
                    evidence="conventional root README present: false",
                )
            )
        if readme is not None and is_rule_enabled(context.config, "RI-DOC-002"):
            for label, present in (
                ("purpose", purpose),
                ("installation", installation),
                ("usage", usage),
            ):
                if not present:
                    findings.append(
                        make_finding(
                            self.metadata,
                            "RI-DOC-002",
                            location=Location(path=readme.path, start_line=1),
                            evidence=f"README missing {label} evidence",
                            explanation_detail=f"The {label} heuristic was not satisfied.",
                        )
                    )
        if (
            docstring_rate is not None
            and docstring_rate < context.config.thresholds.public_docstring_rate
            and docstring_evidence_complete
            and is_rule_enabled(context.config, "RI-DOC-003")
        ):
            first_path = parsed_source[0].file.path
            findings.append(
                make_finding(
                    self.metadata,
                    "RI-DOC-003",
                    location=Location(path=first_path, start_line=1),
                    evidence=(
                        f"documented public API entries: {documented_count}/{public_count} "
                        f"({docstring_rate:.6f})"
                    ),
                )
            )
        if (
            not contribution
            and contribution_absence_complete
            and is_rule_enabled(context.config, "RI-DOC-004")
        ):
            findings.append(
                make_finding(
                    self.metadata,
                    "RI-DOC-004",
                    evidence="recognized contribution guide present: false",
                )
            )
        if (
            not changelog
            and changelog_absence_complete
            and is_rule_enabled(context.config, "RI-DOC-005")
        ):
            findings.append(
                make_finding(
                    self.metadata,
                    "RI-DOC-005",
                    evidence="recognized changelog or release notes present: false",
                )
            )
        if (
            not examples
            and example_absence_complete
            and is_rule_enabled(context.config, "RI-DOC-006")
        ):
            findings.append(
                make_finding(
                    self.metadata,
                    "RI-DOC-006",
                    evidence="examples directory or realistic README code example present: false",
                )
            )

        inventory_completeness = context.inventory.completeness
        inventory_limitations = (
            ("Repository inventory evidence is incomplete",)
            if inventory_completeness is Completeness.PARTIAL
            else ()
        )
        metrics = [
            make_metric(
                self.metadata,
                "documentation.readme_present",
                readme is not None,
                unit=None,
                provenance="Conventional root README inventory",
                completeness=inventory_completeness,
                limitations=inventory_limitations,
            ),
            make_metric(
                self.metadata,
                "documentation.readme_purpose",
                purpose,
                unit=None,
                provenance="Fixed README heading vocabulary",
                completeness=inventory_completeness,
                limitations=inventory_limitations,
            ),
            make_metric(
                self.metadata,
                "documentation.readme_installation",
                installation,
                unit=None,
                provenance="README installation headings and command evidence",
                completeness=inventory_completeness,
                limitations=inventory_limitations,
            ),
            make_metric(
                self.metadata,
                "documentation.readme_usage",
                usage,
                unit=None,
                provenance="README usage headings and code-block evidence",
                completeness=inventory_completeness,
                limitations=inventory_limitations,
            ),
            make_metric(
                self.metadata,
                "documentation.contribution_guide_present",
                contribution,
                unit=None,
                provenance="Repository documentation-role inventory",
                completeness=inventory_completeness,
                limitations=inventory_limitations,
            ),
            make_metric(
                self.metadata,
                "documentation.changelog_present",
                changelog,
                unit=None,
                provenance="Repository changelog-role inventory",
                completeness=inventory_completeness,
                limitations=inventory_limitations,
            ),
            make_metric(
                self.metadata,
                "documentation.examples_evidence",
                examples,
                unit=None,
                provenance="Examples-role inventory and realistic README code blocks",
                completeness=inventory_completeness,
                limitations=inventory_limitations,
            ),
            make_metric(
                self.metadata,
                "documentation.public_api_count",
                public_count if ast_trusted else None,
                unit="count",
                provenance="Retained non-test Python AST public API denominator",
                completeness=doc_completeness,
                limitations=doc_limitations,
            ),
            make_metric(
                self.metadata,
                "documentation.documented_public_api_count",
                documented_count if ast_trusted else None,
                unit="count",
                provenance="ast.get_docstring(clean=False) on public API entries",
                completeness=doc_completeness,
                limitations=doc_limitations,
            ),
            make_metric(
                self.metadata,
                "documentation.public_docstring_rate",
                docstring_rate,
                unit="ratio",
                provenance="Documented public API entries divided by public API entries",
                completeness=doc_completeness,
                limitations=doc_limitations,
            ),
        ]
        limitations = tuple(
            make_limitation(self.metadata, "documentation-evidence", message)
            for message in applicability.limitations
        )
        return make_result(
            self.metadata,
            applicability.completeness,
            metrics=metrics,
            findings=findings,
            limitations=limitations,
        )


ANALYZER = DocumentationAnalyzer()

__all__ = ["ANALYZER", "DocumentationAnalyzer"]
