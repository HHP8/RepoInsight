from __future__ import annotations

import pytest

from repoinsight.analyzers._shared import make_finding, make_metric, make_result
from repoinsight.analyzers.catalog import RULE_CATALOG
from repoinsight.analyzers.maintainability import ANALYZER as MAINTAINABILITY
from repoinsight.config import load_config
from repoinsight.errors import AnalysisError
from repoinsight.models import (
    AnalyzerResult,
    AnalyzerStatus,
    Completeness,
    Limitation,
    Location,
    Metric,
    SkippedInput,
    WarningRecord,
)
from repoinsight.normalization import normalize_results


def _config(*, disabled: tuple[str, ...] = ()):  # type: ignore[no-untyped-def]
    return load_config(None, None, {"rules.disabled": disabled})


def test_normalization_is_permutation_stable_deduplicates_and_applies_caps() -> None:
    findings = [
        make_finding(
            MAINTAINABILITY.metadata,
            "RI-MAINT-008",
            location=Location(path="app.py", start_line=line),
            evidence=f"TODO at line {line}",
        )
        for line in (6, 2, 4, 1, 5, 3)
    ]
    alternate = make_finding(
        MAINTAINABILITY.metadata,
        "RI-MAINT-008",
        location=Location(path="app.py", start_line=4),
        evidence="TODO at line 4",
        explanation_detail="Alternate analyzer detail.",
    )
    duplicated = [*findings, findings[2], alternate]
    first = make_result(MAINTAINABILITY.metadata, Completeness.AVAILABLE, findings=duplicated)
    second = make_result(
        MAINTAINABILITY.metadata,
        Completeness.AVAILABLE,
        findings=reversed(duplicated),
    )

    normalized_a = normalize_results((first,), RULE_CATALOG, _config())
    normalized_b = normalize_results((second,), RULE_CATALOG, _config())

    assert normalized_a == normalized_b
    assert [item.location.start_line for item in normalized_a.findings if item.location] == [
        1,
        2,
        3,
        4,
        5,
        6,
    ]
    assert [item.score_impact for item in normalized_a.findings] == [1, 1, 1, 1, 1, 0]
    assert normalized_a.findings[-1].cap_applied is True
    assert normalized_a.raw_deductions == (("RI-MAINT-008", 6.0),)


def test_normalization_removes_disabled_rules_before_scoring() -> None:
    finding = make_finding(MAINTAINABILITY.metadata, "RI-MAINT-008", evidence="TODO")
    result = make_result(
        MAINTAINABILITY.metadata,
        Completeness.AVAILABLE,
        findings=(finding,),
    )

    normalized = normalize_results(
        (result,),
        RULE_CATALOG,
        _config(disabled=("RI-MAINT-008",)),
    )

    assert normalized.findings == ()
    assert normalized.raw_deductions == ()


def test_normalization_revalidates_untrusted_analyzer_output() -> None:
    valid = make_result(MAINTAINABILITY.metadata, Completeness.AVAILABLE)
    invalid_status = AnalyzerStatus.model_construct(
        analyzer_id="other",
        state=valid.status.state,
        completeness=valid.status.completeness,
        elapsed_seconds=0.0,
        message=None,
    )
    invalid = AnalyzerResult.model_construct(
        metadata=valid.metadata,
        status=invalid_status,
        metrics=(),
        findings=(),
        skipped_inputs=(),
        warnings=(),
        limitations=(),
    )

    with pytest.raises(AnalysisError, match="Invalid analyzer output"):
        normalize_results((invalid,), RULE_CATALOG, _config())


def test_normalization_rejects_duplicate_metric_identifiers() -> None:
    metric = make_metric(
        MAINTAINABILITY.metadata,
        "maintainability.functions",
        1,
        unit="count",
        provenance="AST",
        completeness=Completeness.AVAILABLE,
    )
    result = make_result(
        MAINTAINABILITY.metadata,
        Completeness.AVAILABLE,
        metrics=(metric, metric),
    )

    with pytest.raises(AnalysisError, match="Duplicate metric identifier"):
        normalize_results((result,), RULE_CATALOG, _config())


def test_normalization_redacts_and_sorts_all_diagnostic_collections() -> None:
    secret = "ghp_" + "abcdefghijklmnopqrstuvwxyz1234567890"
    raw_metric = Metric.model_construct(
        id="maintainability.value",
        analyzer_id=MAINTAINABILITY.metadata.id,
        category=MAINTAINABILITY.metadata.category,
        value=secret,
        unit=None,
        provenance=f"from {secret}",
        completeness=Completeness.AVAILABLE,
        limitations=(),
    )
    result = make_result(
        MAINTAINABILITY.metadata,
        Completeness.PARTIAL,
        metrics=(raw_metric,),
        skipped_inputs=(
            SkippedInput(path="z.py", reason="later"),
            SkippedInput(path="a.py", reason="first"),
        ),
        warnings=(
            WarningRecord(code="z", message=f"value {secret}"),
            WarningRecord(code="a", message="first"),
        ),
        limitations=(
            Limitation(code="z", message=f"value {secret}"),
            Limitation(code="a", message="first"),
        ),
    )

    normalized = normalize_results((result,), RULE_CATALOG, _config())
    serialized = repr(normalized)

    assert secret not in serialized
    assert [item.path for item in normalized.skipped_inputs] == ["a.py", "z.py"]
    assert [item.code for item in normalized.warnings] == ["a", "z"]
    assert [item.code for item in normalized.limitations] == ["a", "z"]
