from __future__ import annotations

import re
import tomllib
from pathlib import Path
from urllib.parse import unquote

from repoinsight.analyzers.catalog import RULE_CATALOG
from repoinsight.config import load_config
from repoinsight.version import __version__

ROOT = Path(__file__).parents[2]
MARKDOWN_LINK = re.compile(r"!?\[[^]]*\]\(([^)]+)\)")


def _leaf_keys(value: object, prefix: str = "") -> set[str]:
    if not isinstance(value, dict):
        return {prefix}
    keys: set[str] = set()
    for key, item in value.items():
        dotted = f"{prefix}.{key}" if prefix else key
        keys.update(_leaf_keys(item, dotted))
    return keys


def test_public_versions_commands_rules_and_config_are_synchronized() -> None:
    metadata = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert metadata["project"]["version"] == __version__
    assert metadata["project"]["readme"] == "README.md"
    assert metadata["project"]["license"] == {"file": "LICENSE"}
    assert "twine>=7,<8" in metadata["dependency-groups"]["dev"]

    cli_docs = (ROOT / "docs" / "cli.md").read_text(encoding="utf-8")
    for command in ("analyze", "rules", "explain", "version"):
        assert f"`repoinsight {command}" in cli_docs

    rule_docs = (ROOT / "docs" / "rules.md").read_text(encoding="utf-8")
    assert all(rule.id in rule_docs for rule in RULE_CATALOG)

    scoring_docs = (ROOT / "docs" / "scoring.md").read_text(encoding="utf-8")
    for rating in (
        "Excellent",
        "Strong",
        "Healthy",
        "Needs improvement",
        "High maintenance risk",
    ):
        assert rating in scoring_docs

    config_docs = (ROOT / "docs" / "configuration.md").read_text(encoding="utf-8")
    effective = load_config(None, None, {}).model_dump(mode="json")
    assert all(f"`{key}`" in config_docs for key in _leaf_keys(effective))


def test_release_governance_workflows_and_fixtures_are_present() -> None:
    required_files = (
        "README.md",
        "LICENSE",
        "CHANGELOG.md",
        "CONTRIBUTING.md",
        "CODE_OF_CONDUCT.md",
        "SECURITY.md",
        "SUPPORT.md",
        "docs/architecture.md",
        "docs/analyzers.md",
        "docs/scoring.md",
        "docs/configuration.md",
        "docs/cli.md",
        "docs/rules.md",
        "docs/security.md",
        "docs/limitations.md",
        "docs/release.md",
        "docs/assets/report-preview.svg",
        "benchmarks/README.md",
        "benchmarks/results/2026-08-24-windows-cpython-3.12.json",
        "tools/validate_reports.py",
        ".github/dependabot.yml",
        ".github/workflows/ci.yml",
        ".github/workflows/benchmark.yml",
        ".github/workflows/release.yml",
        ".github/ISSUE_TEMPLATE/bug.yml",
        ".github/ISSUE_TEMPLATE/feature.yml",
        ".github/pull_request_template.md",
    )
    assert all((ROOT / path).is_file() for path in required_files)

    fixtures = ROOT / "tests" / "fixtures" / "repos"
    expected = {
        "healthy",
        "problematic",
        "malformed",
        "no_git",
        "partial_history",
        "oversized",
        "link_escape",
        "suspected_secret",
        "analyzer_failure",
    }
    assert {item.name for item in fixtures.iterdir() if item.is_dir()} == expected


def test_ci_matrix_and_release_workflow_cover_supported_contract() -> None:
    ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    for operating_system in ("ubuntu-latest", "macos-latest", "windows-latest"):
        assert operating_system in ci
    for version in ("3.11", "3.12", "3.13", "3.14"):
        assert version in ci

    release = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    assert "id-token: write" in release
    assert "pypa/gh-action-pypi-publish" in release
    assert "refs/tags/v" in release


def test_release_workflow_separates_tag_builds_from_manual_pypi_publication() -> None:
    release = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    build, publish = release.split("\n  publish:\n", maxsplit=1)
    publish_gate, publish_steps = publish.split("\n    steps:\n", maxsplit=1)

    assert "workflow_dispatch:" in release
    assert "github.event_name == 'push'" in build
    assert "github.event_name == 'workflow_dispatch'" in build
    assert "github.event_name == 'workflow_dispatch'" in publish_gate
    assert "github.ref_type == 'tag'" in publish_gate
    assert "needs.build.result == 'success'" in publish_gate
    assert "id-token: write" not in build
    assert "id-token: write" in publish_gate
    assert release.count("id-token: write") == 1
    assert "refs/tags/$GITHUB_REF_NAME" in publish_steps
    assert "tag == f'v{version}'" in publish_steps
    assert "pypa/gh-action-pypi-publish" not in build
    assert "pypa/gh-action-pypi-publish" in publish_steps
    assert release.count("pypa/gh-action-pypi-publish") == 1


def test_public_tree_omits_internal_execution_ledger() -> None:
    assert not (ROOT / "plan.md").exists()
    metadata = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert "plan.md" not in metadata["tool"]["ruff"]["exclude"]
    assert ".superpowers" not in metadata["tool"]["ruff"]["exclude"]


def test_public_markdown_relative_links_resolve() -> None:
    documents = (
        ROOT / "README.md",
        ROOT / "CHANGELOG.md",
        ROOT / "CONTRIBUTING.md",
        ROOT / "SECURITY.md",
        ROOT / "SUPPORT.md",
        *(ROOT / "docs").glob("*.md"),
        ROOT / "benchmarks" / "README.md",
    )
    missing: list[str] = []
    for document in documents:
        for target in MARKDOWN_LINK.findall(document.read_text(encoding="utf-8")):
            if "://" in target or target.startswith(("#", "mailto:")):
                continue
            relative = unquote(target.split("#", maxsplit=1)[0])
            if relative and not (document.parent / relative).exists():
                missing.append(f"{document.relative_to(ROOT).as_posix()} -> {target}")
    assert not missing, missing
