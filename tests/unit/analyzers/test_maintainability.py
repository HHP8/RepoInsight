from __future__ import annotations

from collections.abc import Callable

from repoinsight.analyzers.base import AnalysisContext
from repoinsight.analyzers.catalog import RULE_CATALOG
from repoinsight.analyzers.maintainability import ANALYZER
from repoinsight.models import AnalyzerResult, Completeness, Finding, Metric

ContextFactory = Callable[..., AnalysisContext]


def _function_with_ifs(name: str, branch_count: int) -> str:
    lines = [f"def {name}(flag):"]
    lines.extend("    if flag: pass" for _ in range(branch_count))
    lines.append("    return flag")
    return "\n".join(lines) + "\n"


def _span_block(kind: str, name: str, span: int) -> str:
    return f"{kind} {name}():\n" + "    pass\n" * (span - 1)


def _nested_function(name: str, depth: int) -> str:
    lines = [f"def {name}(flag):"]
    for level in range(depth):
        lines.append("    " * (level + 1) + "if flag:")
    lines.append("    " * (depth + 1) + "return flag")
    return "\n".join(lines) + "\n"


def _by_rule(result: AnalyzerResult, rule_id: str) -> list[Finding]:
    return [finding for finding in result.findings if finding.rule_id == rule_id]


def _metrics(result: AnalyzerResult) -> dict[str, Metric]:
    return {metric.id: metric for metric in result.metrics}


def test_complexity_uses_14_15_16_boundaries_and_disabled_rule_keeps_metric(
    context_factory: ContextFactory,
) -> None:
    source = "".join(
        (
            _function_with_ifs("below", 13),
            _function_with_ifs("boundary", 14),
            _function_with_ifs("above", 15),
        )
    )
    result = ANALYZER.analyze(context_factory({"module.py": source}))

    findings = _by_rule(result, "RI-MAINT-001")
    assert [
        (item.location.start_line if item.location else None, item.evidence) for item in findings
    ] == [
        (16, "boundary has static cyclomatic complexity 15"),
        (32, "above has static cyclomatic complexity 16"),
    ]
    metrics = _metrics(result)
    assert metrics["maintainability.function_count"].value == 3
    assert metrics["maintainability.max_complexity"].value == 16

    disabled = ANALYZER.analyze(
        context_factory(
            {"module.py": source},
            config_overrides={"rules": {"disabled": ["RI-MAINT-001"]}},
        )
    )
    assert _by_rule(disabled, "RI-MAINT-001") == []
    assert _metrics(disabled)["maintainability.max_complexity"].value == 16


def test_complexity_counts_extra_bool_operands_and_nondefault_match_cases(
    context_factory: ContextFactory,
) -> None:
    source = (
        "def boundary(a, b, c, value):\n"
        "    if a and b and c:\n"
        "        pass\n"
        "    match value:\n"
        "        case 1:\n"
        "            pass\n"
        "        case 2 if a:\n"
        "            pass\n"
        "        case _:\n"
        "            pass\n"
    )
    result = ANALYZER.analyze(
        context_factory(
            {"logic.py": source},
            config_overrides={"thresholds": {"complexity": 6}},
        )
    )

    assert [item.evidence for item in _by_rule(result, "RI-MAINT-001")] == [
        "boundary has static cyclomatic complexity 6"
    ]
    assert _metrics(result)["maintainability.max_complexity"].value == 6


def test_complexity_ignores_default_and_decorator_expression_branches(
    context_factory: ContextFactory,
) -> None:
    result = ANALYZER.analyze(
        context_factory(
            {"defaults.py": ("def plain(value=(first and second and third)):\n    return value\n")},
            config_overrides={"thresholds": {"complexity": 2}},
        )
    )

    assert _by_rule(result, "RI-MAINT-001") == []
    assert _metrics(result)["maintainability.max_complexity"].value == 1


def test_function_class_and_module_physical_spans_use_strict_greater_than_boundaries(
    context_factory: ContextFactory,
) -> None:
    result = ANALYZER.analyze(
        context_factory(
            {
                "functions.py": _span_block("def", "at_limit", 75)
                + _span_block("def", "over_limit", 76),
                "class-boundary.py": _span_block("class", "AtLimit", 500),
                "class-over.py": _span_block("class", "OverLimit", 501),
                "module-boundary.py": "value = 1\n" * 1000,
                "module-over.py": "value = 1\n" * 1001,
            }
        )
    )

    assert [item.evidence for item in _by_rule(result, "RI-MAINT-002")] == [
        "over_limit spans 76 physical lines"
    ]
    assert [item.evidence for item in _by_rule(result, "RI-MAINT-003")] == [
        "OverLimit spans 501 physical lines"
    ]
    assert [
        item.location.path if item.location else None for item in _by_rule(result, "RI-MAINT-004")
    ] == ["module-over.py"]
    metrics = _metrics(result)
    assert metrics["maintainability.max_function_loc"].value == 76
    assert metrics["maintainability.max_class_loc"].value == 501
    assert metrics["maintainability.max_module_loc"].value == 1001


def test_nesting_uses_4_5_boundary_without_descending_into_nested_callable(
    context_factory: ContextFactory,
) -> None:
    nested_scope = (
        "def shallow(flag):\n"
        "    def inner():\n"
        + "        if flag:\n"
        + "            if flag:\n"
        + "                if flag:\n"
        + "                    if flag:\n"
        + "                        if flag:\n"
        + "                            return flag\n"
        + "    return inner\n"
    )
    result = ANALYZER.analyze(
        context_factory(
            {
                "nesting.py": _nested_function("below", 4)
                + _nested_function("boundary", 5)
                + nested_scope
            }
        )
    )

    evidence = [item.evidence for item in _by_rule(result, "RI-MAINT-005")]
    assert evidence == [
        "boundary has lexical control-flow depth 5",
        "inner has lexical control-flow depth 5",
    ]
    assert all(not item.startswith("shallow ") for item in evidence)
    assert _metrics(result)["maintainability.max_nesting_depth"].value == 5


def test_duplicate_structure_normalizes_names_literals_but_preserves_operator_shape(
    context_factory: ContextFactory,
) -> None:
    source = (
        "def alpha(value):\n"
        "    a = value + 1\n"
        "    b = a * 2\n"
        "    c = b - 3\n"
        "    d = c / 4\n"
        "    e = d % 5\n"
        "    f = e ** 2\n"
        "    g = -f\n"
        "    return g\n\n"
        "def beta(item):\n"
        "    one = item + 10\n"
        "    two = one * 20\n"
        "    three = two - 30\n"
        "    four = three / 40\n"
        "    five = four % 50\n"
        "    six = five ** 3\n"
        "    seven = -six\n"
        "    return seven\n\n"
        "def changed(item):\n"
        "    one = item - 10\n"
        "    two = one * 20\n"
        "    three = two - 30\n"
        "    four = three / 40\n"
        "    five = four % 50\n"
        "    six = five ** 3\n"
        "    seven = -six\n"
        "    return seven\n\n"
        "def seven_a(value):\n"
        "    a = value + 1\n    b = a + 1\n    c = b + 1\n"
        "    d = c + 1\n    e = d + 1\n    f = e + 1\n    return f\n\n"
        "def seven_b(value):\n"
        "    a = value + 2\n    b = a + 2\n    c = b + 2\n"
        "    d = c + 2\n    e = d + 2\n    f = e + 2\n    return f\n"
    )
    result = ANALYZER.analyze(context_factory({"dupes.py": source}))

    findings = _by_rule(result, "RI-MAINT-006")
    assert len(findings) == 1
    assert findings[0].location is not None
    assert findings[0].location.start_line == 1
    assert findings[0].evidence == "duplicated-looking group: alpha, beta"
    assert "duplicated-looking" in findings[0].explanation.casefold()
    assert _metrics(result)["maintainability.duplicate_structure_groups"].value == 1


def test_possible_unused_private_definition_excludes_static_dynamic_and_export_proxies(
    context_factory: ContextFactory,
) -> None:
    source = (
        "__all__ = ['_exported']\n"
        "def decorator(value): return value\n"
        "def _unused(): return 1\n"
        "def _used(): return 2\n"
        "_used()\n"
        "@decorator\n"
        "def _decorated(): return 3\n"
        "def _exported(): return 4\n"
        "def __dunder__(): return 5\n"
    )
    result = ANALYZER.analyze(context_factory({"unused.py": source}))

    findings = _by_rule(result, "RI-MAINT-007")
    assert [item.evidence for item in findings] == ["possible unused definition: _unused"]
    assert "possible unused" in findings[0].explanation.casefold()
    assert _metrics(result)["maintainability.possible_unused_definitions"].value == 1


def test_dunder_all_exports_apply_only_to_the_defining_module(
    context_factory: ContextFactory,
) -> None:
    result = ANALYZER.analyze(
        context_factory(
            {
                "a.py": "__all__ = ['_shared']\ndef _shared(): return 1\n",
                "b.py": "def _shared(): return 2\n",
            }
        )
    )

    findings = _by_rule(result, "RI-MAINT-007")
    assert len(findings) == 1
    assert findings[0].location is not None
    assert findings[0].location.path == "b.py"


def test_todo_fixme_uses_comment_tokens_and_whole_words_only(
    context_factory: ContextFactory,
) -> None:
    source = (
        "text = 'TODO is data'\n"
        "TODO_value = 1\n"
        "# METHODTODO is not a marker\n"
        "# todo: tracked\n"
        "value = 2  # FIXME later\n"
    )
    result = ANALYZER.analyze(context_factory({"markers.py": source}))

    assert [
        (item.location.start_line if item.location else None, item.evidence)
        for item in _by_rule(result, "RI-MAINT-008")
    ] == [
        (4, "TODO marker in Python comment"),
        (5, "FIXME marker in Python comment"),
    ]
    assert _metrics(result)["maintainability.todo_fixme_markers"].value == 2


def test_import_issues_detect_three_families_and_exempt_optional_and_type_checking(
    context_factory: ContextFactory,
) -> None:
    source = (
        "from typing import TYPE_CHECKING\n"
        "import os\n"
        "import os\n"
        "from package import *\n"
        "if TYPE_CHECKING:\n"
        "    import types\n"
        "try:\n"
        "    import optional\n"
        "except (ImportError, ModuleNotFoundError):\n"
        "    pass\n"
        "if runtime_flag:\n"
        "    import json\n"
        "def local():\n"
        "    import sys\n"
        "class Container:\n"
        "    import decimal\n"
    )
    result = ANALYZER.analyze(context_factory({"imports.py": source}))

    findings = _by_rule(result, "RI-MAINT-009")
    assert [item.evidence for item in findings] == [
        "duplicate import: import os",
        "wildcard import: from package import *",
        "non-top-level import: import json",
        "non-top-level import: import sys",
        "non-top-level import: import decimal",
    ]
    assert _metrics(result)["maintainability.import_issues"].value == 5


def test_maintainability_emits_exact_metrics_catalog_metadata_and_stable_order(
    context_factory: ContextFactory,
) -> None:
    result = ANALYZER.analyze(
        context_factory({"module.py": "def _unused():\n    pass\n# TODO: review\n"})
    )
    expected_ids = {
        "maintainability.function_count",
        "maintainability.max_complexity",
        "maintainability.max_function_loc",
        "maintainability.max_class_loc",
        "maintainability.max_module_loc",
        "maintainability.max_nesting_depth",
        "maintainability.duplicate_structure_groups",
        "maintainability.possible_unused_definitions",
        "maintainability.todo_fixme_markers",
        "maintainability.import_issues",
    }
    assert {metric.id for metric in result.metrics} == expected_ids
    assert all(metric.analyzer_id == "maintainability" for metric in result.metrics)
    assert all(metric.provenance for metric in result.metrics)
    units = {metric.id: metric.unit for metric in result.metrics}
    assert units["maintainability.max_function_loc"] == "lines"
    assert units["maintainability.max_class_loc"] == "lines"
    assert units["maintainability.max_module_loc"] == "lines"
    assert [metric.id for metric in result.metrics] == sorted(expected_ids)
    assert [finding.rule_id for finding in result.findings] == sorted(
        finding.rule_id for finding in result.findings
    )
    catalog = {rule.id: rule for rule in RULE_CATALOG}
    for finding in result.findings:
        rule = catalog[finding.rule_id]
        assert finding.title == rule.title
        assert finding.remediation == rule.remediation
        assert finding.score_impact == rule.default_deduction
        assert finding.confidence is rule.confidence
        assert finding.limitations[0] == rule.limitations


def test_malformed_python_keeps_token_metric_but_marks_ast_metrics_unavailable(
    context_factory: ContextFactory,
) -> None:
    context = context_factory({"broken.py": "def broken(\n# TODO: still visible\n"})
    applicability = ANALYZER.applies(context)
    result = ANALYZER.analyze(context)

    assert applicability.applies is True
    assert applicability.completeness is Completeness.UNAVAILABLE
    assert _metrics(result)["maintainability.function_count"].value is None
    assert (
        _metrics(result)["maintainability.function_count"].completeness is Completeness.UNAVAILABLE
    )
    assert _metrics(result)["maintainability.todo_fixme_markers"].value == 1
    marker = _by_rule(result, "RI-MAINT-008")[0]
    assert marker.location is not None
    assert marker.location.path == "broken.py"
