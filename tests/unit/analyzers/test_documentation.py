from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace

import pytest

from repoinsight.analyzers.base import AnalysisContext
from repoinsight.analyzers.catalog import RULE_CATALOG
from repoinsight.analyzers.documentation import ANALYZER
from repoinsight.models import AnalyzerResult, Completeness, Finding, Limitation, Metric

ContextFactory = Callable[..., AnalysisContext]


def _findings(result: AnalyzerResult, rule_id: str) -> list[Finding]:
    return [finding for finding in result.findings if finding.rule_id == rule_id]


def _metrics(result: AnalyzerResult) -> dict[str, Metric]:
    return {metric.id: metric for metric in result.metrics}


def test_root_readme_and_three_fixed_content_elements(context_factory: ContextFactory) -> None:
    missing = ANALYZER.analyze(context_factory())
    assert len(_findings(missing, "RI-DOC-001")) == 1
    assert _findings(missing, "RI-DOC-002") == []
    assert _metrics(missing)["documentation.readme_present"].value is False

    incomplete = ANALYZER.analyze(context_factory({"README.md": "# Project\nShort text.\n"}))
    content_findings = _findings(incomplete, "RI-DOC-002")
    assert [item.evidence for item in content_findings] == [
        "README missing installation evidence",
        "README missing purpose evidence",
        "README missing usage evidence",
    ]
    assert all("heuristic" in item.limitations[0].casefold() for item in content_findings)

    complete = ANALYZER.analyze(
        context_factory(
            {
                "README.md": (
                    "# Project\n"
                    "## Overview\nA focused static repository inspector.\n"
                    "## Installation\n```console\npip install project\n```\n"
                    "## Usage\n```console\npython -m project .\n```\n"
                )
            }
        )
    )
    assert _findings(complete, "RI-DOC-001") == []
    assert _findings(complete, "RI-DOC-002") == []
    metrics = _metrics(complete)
    assert metrics["documentation.readme_purpose"].value is True
    assert metrics["documentation.readme_installation"].value is True
    assert metrics["documentation.readme_usage"].value is True


def test_public_docstring_denominator_excludes_private_nested_and_tests_at_50_percent(
    context_factory: ContextFactory,
) -> None:
    boundary = ANALYZER.analyze(
        context_factory(
            {
                "api.py": 'def documented():\n    """Public API."""\n    return 1\n',
                "tests/test_api.py": "def undocumented_test():\n    return 1\n",
            }
        )
    )
    boundary_metrics = _metrics(boundary)
    assert boundary_metrics["documentation.public_api_count"].value == 2
    assert boundary_metrics["documentation.documented_public_api_count"].value == 1
    assert boundary_metrics["documentation.public_docstring_rate"].value == 0.5
    assert _findings(boundary, "RI-DOC-003") == []

    below = ANALYZER.analyze(
        context_factory(
            {
                "api.py": (
                    'def documented():\n    """Public API."""\n    return 1\n'
                    "def undocumented():\n    return 2\n"
                    "def _private():\n    return 3\n"
                    "def outer():\n"
                    "    def nested():\n        return 4\n"
                    "    return nested\n"
                )
            }
        )
    )
    assert _metrics(below)["documentation.public_api_count"].value == 4
    assert _metrics(below)["documentation.documented_public_api_count"].value == 1
    assert _metrics(below)["documentation.public_docstring_rate"].value == 0.25
    assert len(_findings(below, "RI-DOC-003")) == 1


def test_public_classes_and_only_their_public_methods_enter_docstring_denominator(
    context_factory: ContextFactory,
) -> None:
    result = ANALYZER.analyze(
        context_factory(
            {
                "api.py": (
                    '"""Module docs."""\n'
                    "class Public:\n"
                    '    """Class docs."""\n'
                    "    def method(self):\n        return 1\n"
                    "    def _private_method(self):\n        return 2\n"
                    "class _Private:\n"
                    "    def method(self):\n        return 3\n"
                )
            }
        )
    )
    metrics = _metrics(result)
    assert metrics["documentation.public_api_count"].value == 3
    assert metrics["documentation.documented_public_api_count"].value == 2


def test_contribution_changelog_and_examples_rules_use_inventory_or_readme_code(
    context_factory: ContextFactory,
) -> None:
    missing = ANALYZER.analyze(context_factory({"README.md": "## Overview\nProject.\n"}))
    assert len(_findings(missing, "RI-DOC-004")) == 1
    assert len(_findings(missing, "RI-DOC-005")) == 1
    assert len(_findings(missing, "RI-DOC-006")) == 1

    files = ANALYZER.analyze(
        context_factory(
            {
                "README.md": "## Overview\nProject.\n",
                "CONTRIBUTING.md": "Workflow\n",
                "CHANGELOG.md": "# Changes\n",
                "examples/demo.py": "print('demo')\n",
            }
        )
    )
    assert _findings(files, "RI-DOC-004") == []
    assert _findings(files, "RI-DOC-005") == []
    assert _findings(files, "RI-DOC-006") == []

    readme_example = ANALYZER.analyze(
        context_factory(
            {
                "README.md": (
                    "## Overview\nProject.\n"
                    "## Usage\n```python\nfrom project import run\nrun()\n```\n"
                )
            }
        )
    )
    assert _findings(readme_example, "RI-DOC-006") == []


def test_disabled_documentation_rule_does_not_change_presence_metric(
    context_factory: ContextFactory,
) -> None:
    result = ANALYZER.analyze(
        context_factory(
            {"README.md": "## Overview\nProject.\n"},
            config_overrides={"rules": {"disabled": ["RI-DOC-004"]}},
        )
    )
    assert _findings(result, "RI-DOC-004") == []
    assert _metrics(result)["documentation.contribution_guide_present"].value is False


def test_no_python_makes_docstring_metrics_unavailable_while_inventory_rules_continue(
    context_factory: ContextFactory,
) -> None:
    result = ANALYZER.analyze(context_factory({"README.md": "## Overview\nProject.\n"}))
    metrics = _metrics(result)
    assert metrics["documentation.public_api_count"].value is None
    assert metrics["documentation.public_docstring_rate"].value is None
    assert metrics["documentation.public_docstring_rate"].completeness is Completeness.UNAVAILABLE
    assert len(_findings(result, "RI-DOC-004")) == 1


def test_constructed_unavailable_docstring_ast_is_not_upgraded_by_retained_records(
    context_factory: ContextFactory,
) -> None:
    result = ANALYZER.analyze(
        context_factory(
            {"README.md": "## Overview\nProject.\n", "api.py": "def public(): pass\n"},
            index_completeness=Completeness.UNAVAILABLE,
        )
    )

    public_count = _metrics(result)["documentation.public_api_count"]
    assert public_count.value is None
    assert public_count.completeness is Completeness.UNAVAILABLE
    assert _metrics(result)["documentation.readme_present"].value is True


@pytest.mark.parametrize(
    ("path", "rule_id", "base_files"),
    [
        pytest.param("README.md", "RI-DOC-001", {}, id="readme"),
        pytest.param(
            "CONTRIBUTING.md",
            "RI-DOC-004",
            {"README.md": "## Overview\nText\n"},
            id="contributing",
        ),
        pytest.param(
            "CHANGELOG.md",
            "RI-DOC-005",
            {"README.md": "## Overview\nText\n"},
            id="changelog",
        ),
        pytest.param(
            "examples/demo.py",
            "RI-DOC-006",
            {"README.md": "## Overview\nText\n"},
            id="examples",
        ),
    ],
)
def test_skipped_documentation_candidate_suppresses_matching_absence_finding(
    context_factory: ContextFactory,
    path: str,
    rule_id: str,
    base_files: dict[str, str],
) -> None:
    files = {**base_files, path: "documentation evidence\n" * 4}
    result = ANALYZER.analyze(
        context_factory(
            files,
            config_overrides={"analysis": {"max_file_bytes": 24}},
        )
    )

    assert _findings(result, rule_id) == []


def test_skipped_python_source_suppresses_low_docstring_rate_finding(
    context_factory: ContextFactory,
) -> None:
    result = ANALYZER.analyze(
        context_factory(
            {
                "api.py": "def public(): pass\n",
                "hidden.py": '"""Documented."""\n' * 4,
            },
            config_overrides={"analysis": {"max_file_bytes": 32}},
        )
    )

    assert _findings(result, "RI-DOC-003") == []
    assert (
        _metrics(result)["documentation.public_docstring_rate"].completeness is Completeness.PARTIAL
    )


def test_documentation_broad_discovery_limit_suppresses_absence_findings(
    context_factory: ContextFactory,
) -> None:
    context = context_factory()
    inventory = replace(
        context.inventory,
        completeness=Completeness.PARTIAL,
        limitations=(Limitation(code="inventory-timeout", message="Inventory timed out"),),
    )

    result = ANALYZER.analyze(replace(context, inventory=inventory))

    assert result.findings == ()


def test_documentation_metrics_catalog_metadata_partial_state_and_stable_order(
    context_factory: ContextFactory,
) -> None:
    result = ANALYZER.analyze(
        context_factory(
            {"README.md": "# Project\n", "api.py": "def public():\n    pass\n"},
            index_completeness=Completeness.PARTIAL,
        )
    )
    expected_ids = {
        "documentation.readme_present",
        "documentation.readme_purpose",
        "documentation.readme_installation",
        "documentation.readme_usage",
        "documentation.public_api_count",
        "documentation.documented_public_api_count",
        "documentation.public_docstring_rate",
        "documentation.contribution_guide_present",
        "documentation.changelog_present",
        "documentation.examples_evidence",
    }
    assert [metric.id for metric in result.metrics] == sorted(expected_ids)
    assert all(
        metric.provenance and metric.analyzer_id == "documentation" for metric in result.metrics
    )
    assert result.status.completeness is Completeness.PARTIAL
    assert _metrics(result)["documentation.public_api_count"].completeness is Completeness.PARTIAL
    assert [finding.rule_id for finding in result.findings] == sorted(
        finding.rule_id for finding in result.findings
    )
    catalog = {rule.id: rule for rule in RULE_CATALOG}
    for finding in result.findings:
        rule = catalog[finding.rule_id]
        assert finding.title == rule.title
        assert finding.remediation == rule.remediation
        assert finding.limitations[0] == rule.limitations
