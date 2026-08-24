from __future__ import annotations

import ast
from collections.abc import Callable

from repoinsight.analyzers._shared import (
    finding_sort_key,
    is_rule_enabled,
    lexical_control_depth,
    make_finding,
    make_location,
    make_metric,
    metric_sort_key,
    module_aliases,
    node_span,
    qualified_call_name,
)
from repoinsight.analyzers.base import AnalysisContext
from repoinsight.analyzers.maintainability import ANALYZER
from repoinsight.models import Completeness

ContextFactory = Callable[..., AnalysisContext]


def test_catalog_backed_finding_redacts_evidence_and_copies_contract_metadata(
    context_factory: ContextFactory,
) -> None:
    context = context_factory({"module.py": "def target():\n    return 1\n"})
    parsed = context.python_index.files[0]
    function = parsed.tree.body[0]
    assert isinstance(function, ast.FunctionDef)
    raw_secret = "ghp_" + "abcdefghijklmnopqrstuvwxyz123456"

    finding = make_finding(
        ANALYZER.metadata,
        "RI-MAINT-007",
        location=make_location(parsed, function),
        evidence=f"possible unused target near {raw_secret}",
        explanation_detail="Candidate: target.",
    )

    assert finding.title == "Possible unused private definition"
    assert finding.explanation.startswith(
        "A private definition has no static in-repository reference."
    )
    assert finding.remediation == "Review dynamic references before removing the definition."
    assert finding.score_impact == 1.0
    assert finding.confidence.value == "low"
    assert finding.limitations == (
        "Dynamic use is not resolved; this is only a possible unused definition.",
    )
    assert finding.location is not None
    assert finding.location.path == "module.py"
    assert finding.location.start_line == 1
    assert raw_secret not in finding.model_dump_json()
    assert "[REDACTED]" in finding.evidence
    assert finding.suppressed is False
    assert finding.cap_applied is False


def test_rule_enablement_and_metrics_keep_measurement_independent(
    context_factory: ContextFactory,
) -> None:
    enabled_context = context_factory()
    disabled_context = context_factory(config_overrides={"rules": {"disabled": ["RI-MAINT-008"]}})

    assert is_rule_enabled(enabled_context.config, "RI-MAINT-008") is True
    assert is_rule_enabled(disabled_context.config, "RI-MAINT-008") is False

    measured_zero = make_metric(
        ANALYZER.metadata,
        "maintainability.todo_fixme_markers",
        0,
        unit="count",
        provenance="Python token evidence",
        completeness=Completeness.AVAILABLE,
    )
    unavailable = make_metric(
        ANALYZER.metadata,
        "maintainability.todo_fixme_markers",
        None,
        unit="count",
        provenance="Python token evidence",
        completeness=Completeness.UNAVAILABLE,
        limitations=("Token evidence unavailable",),
    )

    assert measured_zero.value == 0
    assert measured_zero.completeness is Completeness.AVAILABLE
    assert unavailable.value is None
    assert unavailable.completeness is Completeness.UNAVAILABLE
    assert metric_sort_key(measured_zero) == (
        "maintainability.todo_fixme_markers",
        "maintainability",
    )


def test_qualified_call_resolution_handles_direct_module_and_from_aliases_only() -> None:
    tree = ast.parse(
        "import subprocess as sp\n"
        "from builtins import eval as dynamic\n"
        "eval('1')\n"
        "sp.run(['true'])\n"
        "dynamic('2')\n"
    )
    aliases = module_aliases(tree)
    calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)]

    assert [qualified_call_name(call, aliases) for call in calls] == [
        "eval",
        "subprocess.run",
        "builtins.eval",
    ]


def test_lexical_depth_and_span_ignore_nested_callable_scope() -> None:
    tree = ast.parse(
        "def outer(flag):\n"
        "    if flag:\n"
        "        for item in flag:\n"
        "            while item:\n"
        "                break\n"
        "    def inner():\n"
        "        if flag:\n"
        "            if flag:\n"
        "                if flag:\n"
        "                    if flag:\n"
        "                        if flag:\n"
        "                            return flag\n"
        "    return None\n"
    )
    outer = tree.body[0]
    assert isinstance(outer, ast.FunctionDef)

    assert lexical_control_depth(outer) == 3
    assert node_span(outer) == 13


def test_try_and_except_bodies_share_one_physical_nesting_level() -> None:
    tree = ast.parse(
        "def guarded(flag):\n"
        "    try:\n"
        "        if flag:\n"
        "            return 1\n"
        "    except ValueError:\n"
        "        if flag:\n"
        "            return 2\n"
    )
    function = tree.body[0]
    assert isinstance(function, ast.FunctionDef)

    assert lexical_control_depth(function) == 2


def test_finding_sort_key_uses_semantic_location_order(context_factory: ContextFactory) -> None:
    context = context_factory({"z.py": "# TODO first\n# TODO second\n"})
    parsed = context.python_index.files[0]
    first = make_finding(
        ANALYZER.metadata,
        "RI-MAINT-008",
        location=make_location(parsed, parsed.tree, line=2),
        evidence="TODO marker",
    )
    second = make_finding(
        ANALYZER.metadata,
        "RI-MAINT-008",
        location=make_location(parsed, parsed.tree, line=1),
        evidence="TODO marker",
    )

    assert [
        item.location.start_line if item.location else None
        for item in sorted((first, second), key=finding_sort_key)
    ] == [1, 2]
