from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace

import pytest

from repoinsight.analyzers.base import AnalysisContext
from repoinsight.analyzers.catalog import RULE_CATALOG
from repoinsight.analyzers.repository_hygiene import ANALYZER
from repoinsight.models import AnalyzerResult, Completeness, Finding, Limitation, Metric

ContextFactory = Callable[..., AnalysisContext]


def _rule_ids(result: AnalyzerResult) -> list[str]:
    return [finding.rule_id for finding in result.findings]


def _findings(result: AnalyzerResult, rule_id: str) -> list[Finding]:
    return [finding for finding in result.findings if finding.rule_id == rule_id]


def _metrics(result: AnalyzerResult) -> dict[str, Metric]:
    return {metric.id: metric for metric in result.metrics}


def test_empty_repository_emits_only_unconditional_repository_findings(
    context_factory: ContextFactory,
) -> None:
    result = ANALYZER.analyze(context_factory())

    assert _rule_ids(result) == [
        "RI-REPO-001",
        "RI-REPO-002",
        "RI-REPO-005",
        "RI-REPO-007",
        "RI-REPO-008",
    ]
    assert _metrics(result)["repository.dependency_metadata_present"].value is False
    assert _metrics(result)["repository.dockerfile_count"].value == 0


@pytest.mark.parametrize(
    ("path", "content"),
    [
        pytest.param("LICENSE", "MIT License\n", id="license-file"),
        pytest.param(
            "pyproject.toml",
            "[project]\nname = 'demo'\nlicense = 'MIT'\n",
            id="pep621-spdx",
        ),
        pytest.param("setup.cfg", "[metadata]\nlicense = Apache-2.0\n", id="setup-cfg"),
        pytest.param(
            "setup.py",
            "from setuptools import setup\nsetup(name='demo', license='BSD-3-Clause')\n",
            id="setup-py-literal",
        ),
    ],
)
def test_license_rule_accepts_file_or_static_license_metadata(
    context_factory: ContextFactory,
    path: str,
    content: str,
) -> None:
    result = ANALYZER.analyze(context_factory({path: content}))
    assert _findings(result, "RI-REPO-001") == []
    assert _metrics(result)["repository.license_present"].value is True


def test_python_dependency_and_packaging_rules_are_conditional_on_python(
    context_factory: ContextFactory,
) -> None:
    python_only = ANALYZER.analyze(context_factory({"app.py": "value = 1\n"}))
    assert len(_findings(python_only, "RI-REPO-003")) == 1
    assert len(_findings(python_only, "RI-REPO-004")) == 1

    configured = ANALYZER.analyze(
        context_factory(
            {
                "app.py": "value = 1\n",
                "pyproject.toml": "[project]\nname = 'demo'\ndependencies = []\n",
            }
        )
    )
    assert _findings(configured, "RI-REPO-003") == []
    assert _findings(configured, "RI-REPO-004") == []

    text_only = ANALYZER.analyze(context_factory({"notes.txt": "text\n"}))
    assert _findings(text_only, "RI-REPO-003") == []
    assert _findings(text_only, "RI-REPO-004") == []


def test_ci_rule_narrows_broad_role_to_actual_conventional_configuration(
    context_factory: ContextFactory,
) -> None:
    misleading = ANALYZER.analyze(
        context_factory({"docs/.github/archive/workflows/README.md": "not CI\n"})
    )
    assert len(_findings(misleading, "RI-REPO-005")) == 1
    assert _metrics(misleading)["repository.ci_present"].value is False

    actual = ANALYZER.analyze(context_factory({".github/workflows/ci.yaml": "jobs: {}\n"}))
    assert _findings(actual, "RI-REPO-005") == []
    assert _metrics(actual)["repository.ci_present"].value is True


def test_dockerignore_rule_requires_dockerfile_and_root_ignore(
    context_factory: ContextFactory,
) -> None:
    no_docker = ANALYZER.analyze(context_factory())
    assert _findings(no_docker, "RI-REPO-006") == []

    missing_ignore = ANALYZER.analyze(context_factory({"Dockerfile": "FROM scratch\n"}))
    assert len(_findings(missing_ignore, "RI-REPO-006")) == 1

    ignored = ANALYZER.analyze(
        context_factory({"docker/Dockerfile.dev": "FROM scratch\n", ".dockerignore": ".git\n"})
    )
    assert _findings(ignored, "RI-REPO-006") == []


def test_template_and_policy_rules_trigger_only_when_both_members_are_absent(
    context_factory: ContextFactory,
) -> None:
    one_template = ANALYZER.analyze(context_factory({".github/ISSUE_TEMPLATE/bug.md": "Bug\n"}))
    assert _findings(one_template, "RI-REPO-007") == []

    one_policy = ANALYZER.analyze(context_factory({"SECURITY.md": "Policy\n"}))
    assert _findings(one_policy, "RI-REPO-008") == []

    source_named_security = ANALYZER.analyze(
        context_factory({"security.py": "def check(): return True\n"})
    )
    assert len(_findings(source_named_security, "RI-REPO-008")) == 1
    assert _metrics(source_named_security)["repository.security_policy_present"].value is False


@pytest.mark.parametrize(
    ("path", "rule_id", "base_files"),
    [
        pytest.param("LICENSE", "RI-REPO-001", {}, id="license"),
        pytest.param(".gitignore", "RI-REPO-002", {}, id="gitignore"),
        pytest.param(
            "requirements.txt",
            "RI-REPO-003",
            {"app.py": "x = 1\n"},
            id="dependency",
        ),
        pytest.param(
            "pyproject.toml",
            "RI-REPO-004",
            {"app.py": "x = 1\n"},
            id="packaging",
        ),
        pytest.param(
            "tox.ini",
            "RI-REPO-004",
            {"app.py": "x = 1\n"},
            id="alternate-packaging",
        ),
        pytest.param(
            ".github/workflows/ci.yml",
            "RI-REPO-005",
            {},
            id="ci",
        ),
        pytest.param(
            ".dockerignore",
            "RI-REPO-006",
            {"Dockerfile": "FROM scratch\n"},
            id="dockerignore",
        ),
        pytest.param(
            ".github/ISSUE_TEMPLATE/bug.md",
            "RI-REPO-007",
            {},
            id="templates",
        ),
        pytest.param("SECURITY.md", "RI-REPO-008", {}, id="policies"),
    ],
)
def test_skipped_repository_candidate_suppresses_matching_absence_finding(
    context_factory: ContextFactory,
    path: str,
    rule_id: str,
    base_files: dict[str, str],
) -> None:
    files = {**base_files, path: "repository evidence\n" * 4}
    result = ANALYZER.analyze(
        context_factory(
            files,
            config_overrides={"analysis": {"max_file_bytes": 24}},
        )
    )

    assert _findings(result, rule_id) == []


def test_repository_broad_discovery_limit_suppresses_all_absence_findings(
    context_factory: ContextFactory,
) -> None:
    context = context_factory()
    inventory = replace(
        context.inventory,
        completeness=Completeness.PARTIAL,
        limitations=(
            Limitation(code="directory-entry-limit", message="Directory entries unknown"),
        ),
    )

    result = ANALYZER.analyze(replace(context, inventory=inventory))

    assert result.findings == ()


def test_repository_metrics_disabled_rule_partial_state_catalog_and_order(
    context_factory: ContextFactory,
) -> None:
    result = ANALYZER.analyze(
        context_factory(
            {"app.py": "value = 1\n"},
            config_overrides={"rules": {"disabled": ["RI-REPO-005"]}},
            inventory_completeness=Completeness.PARTIAL,
        )
    )
    assert _findings(result, "RI-REPO-005") == []
    assert _metrics(result)["repository.ci_present"].value is False
    expected_ids = {
        "repository.license_present",
        "repository.gitignore_present",
        "repository.dependency_metadata_present",
        "repository.packaging_config_present",
        "repository.ci_present",
        "repository.dockerfile_count",
        "repository.dockerignore_present",
        "repository.issue_template_present",
        "repository.pull_request_template_present",
        "repository.code_of_conduct_present",
        "repository.security_policy_present",
    }
    assert [metric.id for metric in result.metrics] == sorted(expected_ids)
    assert all(metric.completeness is Completeness.PARTIAL for metric in result.metrics)
    assert all(
        metric.analyzer_id == "repository-hygiene" and metric.provenance
        for metric in result.metrics
    )
    assert _rule_ids(result) == sorted(_rule_ids(result))
    catalog = {rule.id: rule for rule in RULE_CATALOG}
    for finding in result.findings:
        rule = catalog[finding.rule_id]
        assert finding.title == rule.title
        assert finding.remediation == rule.remediation
        assert finding.limitations[0] == rule.limitations
