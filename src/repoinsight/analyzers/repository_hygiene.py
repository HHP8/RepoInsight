"""Repository-hygiene analyzer."""

from __future__ import annotations

import ast
import configparser
import re
import tomllib
from collections.abc import Mapping

from ..inventory import FileRecord, FileRole
from ..models import AnalyzerMetadata, AnalyzerResult, Category, Completeness, Location
from ._shared import (
    absence_evidence_complete,
    files_with_role,
    is_conventional_ci_path,
    is_rule_enabled,
    make_finding,
    make_limitation,
    make_metric,
    make_result,
    module_aliases,
    qualified_call_name,
)
from .base import AnalysisContext, Applicability

_LICENSE_VALUE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.+() /-]{1,127}$")
_WORKFLOW = re.compile(r"^\.github/workflows/[^/]+\.ya?ml$", re.IGNORECASE)


def _base_name(path: str) -> str:
    return path.casefold().rsplit("/", 1)[-1]


def _path_is_license_evidence(path: str) -> bool:
    name = _base_name(path)
    return name.startswith(("license", "licence", "copying")) or name in {
        "pyproject.toml",
        "setup.cfg",
        "setup.py",
    }


def _path_is_root_gitignore(path: str) -> bool:
    return path.casefold() == ".gitignore"


def _path_is_dependency_metadata(path: str) -> bool:
    name = _base_name(path)
    return name.startswith("requirements") or name in {
        "constraints.txt",
        "pdm.lock",
        "pipfile",
        "pipfile.lock",
        "poetry.lock",
        "pyproject.toml",
        "setup.cfg",
        "setup.py",
        "uv.lock",
    }


def _path_is_packaging_config(path: str) -> bool:
    return _base_name(path) in {
        "manifest.in",
        "noxfile.py",
        "pyproject.toml",
        "setup.cfg",
        "setup.py",
        "tox.ini",
    }


def _path_is_root_dockerignore(path: str) -> bool:
    return path.casefold() == ".dockerignore"


def _path_is_collaboration_template(path: str) -> bool:
    folded = path.casefold()
    return "issue_template" in folded.split("/") or "pull_request_template" in folded


def _path_is_policy(path: str) -> bool:
    name = _base_name(path)
    return name.startswith(("code_of_conduct", "code-of-conduct", "security"))


def _license_value(value: object) -> bool:
    if isinstance(value, str):
        stripped = value.strip()
        return bool(_LICENSE_VALUE.fullmatch(stripped)) and stripped.casefold() not in {
            "unknown",
            "none",
        }
    if isinstance(value, Mapping):
        text = value.get("text")
        return isinstance(text, str) and _license_value(text)
    return False


def _pyproject_license(file: FileRecord) -> bool:
    try:
        loaded = tomllib.loads(file.text)
    except tomllib.TOMLDecodeError:
        return False
    project = loaded.get("project")
    return isinstance(project, Mapping) and _license_value(project.get("license"))


def _setup_cfg_license(file: FileRecord) -> bool:
    parser = configparser.ConfigParser(interpolation=None, strict=False)
    try:
        parser.read_string(file.text)
    except configparser.Error:
        return False
    return _license_value(parser.get("metadata", "license", fallback=""))


def _setup_py_license(context: AnalysisContext, path: str) -> bool:
    parsed = next(
        (
            item
            for item in context.python_index.files
            if item.file.path.casefold() == path.casefold()
        ),
        None,
    )
    if parsed is None:
        return False
    aliases = module_aliases(parsed.tree)
    for node in ast.walk(parsed.tree):
        if not isinstance(node, ast.Call):
            continue
        if qualified_call_name(node, aliases) not in {
            "setup",
            "setuptools.setup",
            "distutils.core.setup",
        }:
            continue
        for keyword in node.keywords:
            if (
                keyword.arg == "license"
                and isinstance(keyword.value, ast.Constant)
                and _license_value(keyword.value.value)
            ):
                return True
    return False


def _license_present(context: AnalysisContext) -> bool:
    if files_with_role(context.inventory.files, FileRole.LICENSE):
        return True
    for file in context.inventory.files:
        name = file.path.casefold().rsplit("/", 1)[-1]
        if name == "pyproject.toml" and _pyproject_license(file):
            return True
        if name == "setup.cfg" and _setup_cfg_license(file):
            return True
        if name == "setup.py" and _setup_py_license(context, file.path):
            return True
    return False


def _actual_ci(files: tuple[FileRecord, ...]) -> tuple[FileRecord, ...]:
    return tuple(
        sorted(
            (
                file
                for file in files
                if _WORKFLOW.fullmatch(file.path) is not None
                or file.path.casefold() in {".travis.yml", "appveyor.yml"}
            ),
            key=lambda file: file.path,
        )
    )


def _security_policy_present(files: tuple[FileRecord, ...]) -> bool:
    return any(
        file.path.casefold() in {"security.md", ".github/security.md", "docs/security.md"}
        for file in files
    )


class RepositoryHygieneAnalyzer:
    metadata = AnalyzerMetadata(
        id="repository-hygiene",
        version="1.0.0",
        category=Category.REPOSITORY_HYGIENE,
        rule_ids=tuple(f"RI-REPO-{index:03}" for index in range(1, 9)),
        capabilities=("inventory", "static-metadata-text"),
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
        if context.inventory.completeness is Completeness.PARTIAL:
            return Applicability(
                True,
                Completeness.PARTIAL,
                ("Repository metadata inventory is incomplete",),
            )
        return Applicability(True, Completeness.AVAILABLE)

    def analyze(self, context: AnalysisContext) -> AnalyzerResult:
        applicability = self.applies(context)
        files = context.inventory.files
        license_present = _license_present(context)
        gitignore_present = any(file.path.casefold() == ".gitignore" for file in files)
        python_present = any(
            FileRole.PYTHON_SOURCE in file.roles or FileRole.PYTHON_TEST in file.roles
            for file in files
        )
        dependency_present = bool(files_with_role(files, FileRole.DEPENDENCY))
        packaging_present = bool(files_with_role(files, FileRole.PACKAGING))
        ci_files = _actual_ci(files)
        ci_present = bool(ci_files)
        dockerfiles = files_with_role(files, FileRole.DOCKERFILE)
        dockerignore_present = any(file.path.casefold() == ".dockerignore" for file in files)
        issue_template = bool(files_with_role(files, FileRole.ISSUE_TEMPLATE))
        pull_request_template = bool(files_with_role(files, FileRole.PULL_REQUEST_TEMPLATE))
        code_of_conduct = bool(files_with_role(files, FileRole.CODE_OF_CONDUCT))
        security_policy = _security_policy_present(files)

        absence_complete = {
            "RI-REPO-001": absence_evidence_complete(context.inventory, _path_is_license_evidence),
            "RI-REPO-002": absence_evidence_complete(context.inventory, _path_is_root_gitignore),
            "RI-REPO-003": absence_evidence_complete(
                context.inventory, _path_is_dependency_metadata
            ),
            "RI-REPO-004": absence_evidence_complete(context.inventory, _path_is_packaging_config),
            "RI-REPO-005": absence_evidence_complete(context.inventory, is_conventional_ci_path),
            "RI-REPO-006": absence_evidence_complete(context.inventory, _path_is_root_dockerignore),
            "RI-REPO-007": absence_evidence_complete(
                context.inventory, _path_is_collaboration_template
            ),
            "RI-REPO-008": absence_evidence_complete(context.inventory, _path_is_policy),
        }

        findings = []
        predicates = (
            (
                "RI-REPO-001",
                not license_present,
                "license file or static license metadata present: false",
            ),
            ("RI-REPO-002", not gitignore_present, "root .gitignore present: false"),
            (
                "RI-REPO-003",
                python_present and not dependency_present,
                "Python exists and dependency metadata present: false",
            ),
            (
                "RI-REPO-004",
                python_present and not packaging_present,
                "Python exists and packaging configuration present: false",
            ),
            ("RI-REPO-005", not ci_present, "conventional CI configuration present: false"),
            (
                "RI-REPO-006",
                bool(dockerfiles) and not dockerignore_present,
                "Dockerfile exists and root .dockerignore present: false",
            ),
            (
                "RI-REPO-007",
                not issue_template and not pull_request_template,
                "issue and pull-request templates present: false",
            ),
            (
                "RI-REPO-008",
                not code_of_conduct and not security_policy,
                "code of conduct and security policy present: false",
            ),
        )
        for rule_id, triggered, evidence in predicates:
            if (
                not triggered
                or not absence_complete[rule_id]
                or not is_rule_enabled(context.config, rule_id)
            ):
                continue
            location = None
            if rule_id == "RI-REPO-006" and dockerfiles:
                location = Location(path=dockerfiles[0].path, start_line=1)
            findings.append(
                make_finding(
                    self.metadata,
                    rule_id,
                    location=location,
                    evidence=evidence,
                )
            )

        values: dict[str, bool | int] = {
            "repository.license_present": license_present,
            "repository.gitignore_present": gitignore_present,
            "repository.dependency_metadata_present": dependency_present,
            "repository.packaging_config_present": packaging_present,
            "repository.ci_present": ci_present,
            "repository.dockerfile_count": len(dockerfiles),
            "repository.dockerignore_present": dockerignore_present,
            "repository.issue_template_present": issue_template,
            "repository.pull_request_template_present": pull_request_template,
            "repository.code_of_conduct_present": code_of_conduct,
            "repository.security_policy_present": security_policy,
        }
        metrics = [
            make_metric(
                self.metadata,
                metric_id,
                value,
                unit="count" if metric_id == "repository.dockerfile_count" else None,
                provenance="Narrowed conventional repository metadata inventory",
                completeness=applicability.completeness,
                limitations=applicability.limitations,
            )
            for metric_id, value in values.items()
        ]
        limitations = tuple(
            make_limitation(self.metadata, "repository-evidence", message)
            for message in applicability.limitations
        )
        return make_result(
            self.metadata,
            applicability.completeness,
            metrics=metrics,
            findings=findings,
            limitations=limitations,
        )


ANALYZER = RepositoryHygieneAnalyzer()

__all__ = ["ANALYZER", "RepositoryHygieneAnalyzer"]
