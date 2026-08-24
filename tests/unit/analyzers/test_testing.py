from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace

import pytest

from repoinsight.analyzers.base import AnalysisContext
from repoinsight.analyzers.catalog import RULE_CATALOG
from repoinsight.analyzers.testing import ANALYZER
from repoinsight.models import (
    AnalyzerResult,
    Completeness,
    Finding,
    Limitation,
    Metric,
    Severity,
)

ContextFactory = Callable[..., AnalysisContext]


def _rule_findings(result: AnalyzerResult, rule_id: str) -> list[Finding]:
    return [finding for finding in result.findings if finding.rule_id == rule_id]


def _metric_map(result: AnalyzerResult) -> dict[str, Metric]:
    return {metric.id: metric for metric in result.metrics}


def test_test_discovery_distinguishes_recognized_configured_and_nonstandard_layouts(
    context_factory: ContextFactory,
) -> None:
    source_only = ANALYZER.analyze(context_factory({"src/app.py": "value = 1\n"}))
    assert len(_rule_findings(source_only, "RI-TEST-001")) == 1
    assert _rule_findings(source_only, "RI-TEST-003") == []

    outside = ANALYZER.analyze(
        context_factory({"src/app.py": "value = 1\n", "specs/test_app.py": "assert True\n"})
    )
    assert len(_rule_findings(outside, "RI-TEST-001")) == 1
    assert len(_rule_findings(outside, "RI-TEST-003")) == 1

    configured = ANALYZER.analyze(
        context_factory(
            {
                "src/app.py": "value = 1\n",
                "specs/test_app.py": "import pytest\nassert True\n",
                "pyproject.toml": (
                    "[tool.pytest.ini_options]\n"
                    'testpaths = ["specs"]\n'
                    "[tool.coverage.run]\nbranch = true\n"
                ),
            }
        )
    )
    assert _rule_findings(configured, "RI-TEST-001") == []
    assert _rule_findings(configured, "RI-TEST-003") == []
    assert _metric_map(configured)["testing.recognized_test_files"].value == 1

    root_pattern = ANALYZER.analyze(
        context_factory({"app.py": "value = 1\n", "test_root.py": "import unittest\n"})
    )
    assert _rule_findings(root_pattern, "RI-TEST-001") == []


@pytest.mark.parametrize("config_name", ["pytest.ini", "tox.ini", "setup.cfg"])
def test_ini_testpaths_are_read_statically_from_each_supported_surface(
    context_factory: ContextFactory,
    config_name: str,
) -> None:
    result = ANALYZER.analyze(
        context_factory(
            {
                "app.py": "value = 1\n",
                "specs/test_app.py": "import pytest\n",
                config_name: "[pytest]\ntestpaths = specs\n",
            }
        )
    )

    assert _rule_findings(result, "RI-TEST-001") == []
    assert _metric_map(result)["testing.recognized_test_files"].value == 1


@pytest.mark.parametrize(
    ("test_lines", "expected_severity", "expected_impact"),
    [
        pytest.param(9, Severity.MEDIUM, 12.0, id="below-point-ten"),
        pytest.param(10, Severity.LOW, 6.0, id="exact-point-ten"),
        pytest.param(24, Severity.LOW, 6.0, id="below-point-twenty-five"),
        pytest.param(25, None, None, id="exact-point-twenty-five"),
    ],
)
def test_test_source_ratio_uses_exact_band_boundaries(
    context_factory: ContextFactory,
    test_lines: int,
    expected_severity: Severity | None,
    expected_impact: float | None,
) -> None:
    result = ANALYZER.analyze(
        context_factory(
            {
                "src/app.py": "value = 1\n" * 100,
                "tests/test_app.py": "assert True\n" * test_lines,
            }
        )
    )

    findings = _rule_findings(result, "RI-TEST-002")
    if expected_severity is None:
        assert findings == []
    else:
        assert [(findings[0].severity, findings[0].score_impact)] == [
            (expected_severity, expected_impact)
        ]
        assert "never measured runtime coverage" in findings[0].limitations[0]
    assert _metric_map(result)["testing.test_source_ratio"].value == test_lines / 100
    assert _metric_map(result)["testing.test_source_ratio"].unit == "ratio"


def test_zero_source_loc_makes_ratio_unavailable_without_a_ratio_finding(
    context_factory: ContextFactory,
) -> None:
    result = ANALYZER.analyze(
        context_factory({"tests/test_only.py": "import unittest\nassert True\n"})
    )
    ratio = _metric_map(result)["testing.test_source_ratio"]

    assert ratio.value is None
    assert ratio.completeness is Completeness.UNAVAILABLE
    assert _rule_findings(result, "RI-TEST-002") == []


def test_runner_evidence_uses_test_ast_or_static_configuration(
    context_factory: ContextFactory,
) -> None:
    missing = ANALYZER.analyze(
        context_factory({"app.py": "value = 1\n", "tests/test_app.py": "assert True\n"})
    )
    assert len(_rule_findings(missing, "RI-TEST-004")) == 1
    assert _metric_map(missing)["testing.framework_evidence"].value is False

    unittest_evidence = ANALYZER.analyze(
        context_factory({"app.py": "value = 1\n", "tests/test_app.py": "import unittest\n"})
    )
    assert _rule_findings(unittest_evidence, "RI-TEST-004") == []
    assert _metric_map(unittest_evidence)["testing.framework_evidence"].value is True

    tox_evidence = ANALYZER.analyze(
        context_factory(
            {
                "app.py": "value = 1\n",
                "tests/test_app.py": "assert True\n",
                "tox.ini": "[testenv]\ncommands = python -m unittest\n",
            }
        )
    )
    assert _rule_findings(tox_evidence, "RI-TEST-004") == []


def test_malformed_test_ast_suppresses_missing_runner_claim_but_inventory_rules_continue(
    context_factory: ContextFactory,
) -> None:
    result = ANALYZER.analyze(
        context_factory(
            {
                "app.py": "value = 1\n",
                "tests/test_broken.py": "def broken(\n",
            }
        )
    )

    assert result.status.completeness is Completeness.PARTIAL
    assert _rule_findings(result, "RI-TEST-001") == []
    assert _rule_findings(result, "RI-TEST-004") == []
    assert len(_rule_findings(result, "RI-TEST-006")) == 1
    framework = _metric_map(result)["testing.framework_evidence"]
    assert framework.value is False
    assert framework.completeness is Completeness.PARTIAL


def test_ci_rule_requires_existing_ci_and_a_conservative_test_command(
    context_factory: ContextFactory,
) -> None:
    missing_ci = ANALYZER.analyze(
        context_factory({"app.py": "value = 1\n", "tests/test_app.py": "import pytest\n"})
    )
    assert _rule_findings(missing_ci, "RI-TEST-005") == []

    ci_without_tests = ANALYZER.analyze(
        context_factory(
            {
                "app.py": "value = 1\n",
                "tests/test_app.py": "import pytest\n",
                ".github/workflows/ci.yml": "steps:\n  - run: python -m build\n",
            }
        )
    )
    assert len(_rule_findings(ci_without_tests, "RI-TEST-005")) == 1
    assert _metric_map(ci_without_tests)["testing.ci_test_evidence"].value is False

    ci_with_tests = ANALYZER.analyze(
        context_factory(
            {
                "app.py": "value = 1\n",
                "tests/test_app.py": "import pytest\n",
                ".github/workflows/ci.yml": "steps:\n  - run: python -m pytest -q\n",
            }
        )
    )
    assert _rule_findings(ci_with_tests, "RI-TEST-005") == []
    assert _metric_map(ci_with_tests)["testing.ci_test_evidence"].value is True


def test_ci_installing_a_test_dependency_is_not_a_test_invocation(
    context_factory: ContextFactory,
) -> None:
    result = ANALYZER.analyze(
        context_factory(
            {
                "app.py": "value = 1\n",
                "tests/test_app.py": "import pytest\n",
                ".github/workflows/ci.yml": "steps:\n  - run: pip install pytest\n",
            }
        )
    )

    assert len(_rule_findings(result, "RI-TEST-005")) == 1
    assert _metric_map(result)["testing.ci_test_evidence"].value is False


def test_constructed_unavailable_test_ast_is_not_upgraded_by_retained_records(
    context_factory: ContextFactory,
) -> None:
    result = ANALYZER.analyze(
        context_factory(
            {"app.py": "value = 1\n", "tests/test_app.py": "assert True\n"},
            index_completeness=Completeness.UNAVAILABLE,
        )
    )

    assert result.status.completeness is Completeness.PARTIAL
    framework = _metric_map(result)["testing.framework_evidence"]
    assert framework.value is None
    assert framework.completeness is Completeness.UNAVAILABLE
    assert _rule_findings(result, "RI-TEST-004") == []


def test_skipped_recognized_test_suppresses_no_tests_and_ratio_findings(
    context_factory: ContextFactory,
) -> None:
    result = ANALYZER.analyze(
        context_factory(
            {
                "app.py": "x = 1\n",
                "tests/test_app.py": "assert True\n" * 4,
            },
            config_overrides={"analysis": {"max_file_bytes": 16}},
        )
    )

    assert _rule_findings(result, "RI-TEST-001") == []
    assert _rule_findings(result, "RI-TEST-002") == []
    ratio = _metric_map(result)["testing.test_source_ratio"]
    assert ratio.completeness is Completeness.PARTIAL


def test_skipped_recognized_test_suppresses_nonstandard_layout_claim(
    context_factory: ContextFactory,
) -> None:
    result = ANALYZER.analyze(
        context_factory(
            {
                "app.py": "x = 1\n",
                "specs/test_app.py": "assert 1\n",
                "tests/test_hidden.py": "assert True\n" * 4,
            },
            config_overrides={"analysis": {"max_file_bytes": 16}},
        )
    )

    assert _rule_findings(result, "RI-TEST-001") == []
    assert _rule_findings(result, "RI-TEST-003") == []


def test_skipped_runner_ci_and_coverage_evidence_suppress_absence_findings(
    context_factory: ContextFactory,
) -> None:
    result = ANALYZER.analyze(
        context_factory(
            {
                "app.py": "x = 1\n",
                "tests/test_app.py": "assert 1\n",
                "tests/test_runner.py": "import pytest\n" * 3,
                ".github/workflows/build.yml": "run: build\n",
                ".github/workflows/tests.yml": "run: pytest\n" * 3,
                ".coveragerc": "[run]\nbranch = true\n" * 3,
            },
            config_overrides={"analysis": {"max_file_bytes": 24}},
        )
    )

    assert _rule_findings(result, "RI-TEST-004") == []
    assert _rule_findings(result, "RI-TEST-005") == []
    assert _rule_findings(result, "RI-TEST-006") == []


def test_testing_broad_discovery_limit_suppresses_all_absence_deductions(
    context_factory: ContextFactory,
) -> None:
    context = context_factory({"app.py": "x = 1\n"})
    inventory = replace(
        context.inventory,
        completeness=Completeness.PARTIAL,
        limitations=(
            Limitation(
                code="file-discovery-limit",
                message="Repository discovery stopped at the configured file limit",
            ),
        ),
    )

    result = ANALYZER.analyze(replace(context, inventory=inventory))

    assert result.findings == ()
    assert _metric_map(result)["testing.test_source_ratio"].completeness is Completeness.PARTIAL


def test_coverage_rule_recognizes_config_and_disabled_rule_keeps_boolean_metric(
    context_factory: ContextFactory,
) -> None:
    missing = ANALYZER.analyze(
        context_factory({"app.py": "value = 1\n", "tests/test_app.py": "import pytest\n"})
    )
    assert len(_rule_findings(missing, "RI-TEST-006")) == 1
    assert _metric_map(missing)["testing.coverage_evidence"].value is False

    configured = ANALYZER.analyze(
        context_factory(
            {
                "app.py": "value = 1\n",
                "tests/test_app.py": "import pytest\n",
                ".coveragerc": "[run]\nbranch = True\n",
            }
        )
    )
    assert _rule_findings(configured, "RI-TEST-006") == []

    disabled = ANALYZER.analyze(
        context_factory(
            {"app.py": "value = 1\n", "tests/test_app.py": "import pytest\n"},
            config_overrides={"rules": {"disabled": ["RI-TEST-006"]}},
        )
    )
    assert _rule_findings(disabled, "RI-TEST-006") == []
    assert _metric_map(disabled)["testing.coverage_evidence"].value is False


def test_testing_metrics_catalog_shape_completeness_and_deterministic_order(
    context_factory: ContextFactory,
) -> None:
    result = ANALYZER.analyze(
        context_factory(
            {
                "app.py": "value = 1\n" * 4,
                "tests/test_app.py": "import pytest\nassert True\n",
            },
            inventory_completeness=Completeness.PARTIAL,
        )
    )
    expected_ids = {
        "testing.source_loc",
        "testing.test_loc",
        "testing.test_source_ratio",
        "testing.test_files",
        "testing.recognized_test_files",
        "testing.framework_evidence",
        "testing.ci_test_evidence",
        "testing.coverage_evidence",
    }
    assert [metric.id for metric in result.metrics] == sorted(expected_ids)
    assert all(metric.analyzer_id == "testing" and metric.provenance for metric in result.metrics)
    assert all(metric.completeness is Completeness.PARTIAL for metric in result.metrics)
    assert [finding.rule_id for finding in result.findings] == sorted(
        finding.rule_id for finding in result.findings
    )
    catalog = {rule.id: rule for rule in RULE_CATALOG}
    for finding in result.findings:
        rule = catalog[finding.rule_id]
        assert finding.title == rule.title
        assert finding.remediation == rule.remediation
        assert finding.limitations[0] == rule.limitations
