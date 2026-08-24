from __future__ import annotations

import pytest

from repoinsight.analyzers._shared import make_finding, make_result
from repoinsight.analyzers.base import Analyzer
from repoinsight.analyzers.catalog import RULE_CATALOG
from repoinsight.analyzers.documentation import ANALYZER as DOCUMENTATION
from repoinsight.analyzers.maintainability import ANALYZER as MAINTAINABILITY
from repoinsight.analyzers.security import ANALYZER as SECURITY
from repoinsight.config import load_config
from repoinsight.models import (
    AnalyzerResult,
    AnalyzerState,
    Completeness,
    EffectiveConfig,
    Finding,
)
from repoinsight.normalization import normalize_results
from repoinsight.scoring import score_evidence


def _config(overrides: dict[str, object] | None = None) -> EffectiveConfig:
    return load_config(None, None, overrides or {})


def _result(
    analyzer: Analyzer,
    completeness: Completeness = Completeness.AVAILABLE,
    findings: tuple[Finding, ...] = (),
) -> AnalyzerResult:
    result = make_result(analyzer.metadata, completeness, findings=findings)
    if completeness is Completeness.UNAVAILABLE:
        result = result.model_copy(
            update={
                "status": result.status.model_copy(
                    update={
                        "state": AnalyzerState.SKIPPED,
                        "completeness": Completeness.UNAVAILABLE,
                    }
                )
            }
        )
    return result


def test_scoring_traces_caps_and_clamps_categories() -> None:
    findings = tuple(
        make_finding(
            MAINTAINABILITY.metadata,
            "RI-MAINT-001",
            score_impact=15,
            evidence=f"unit {index}",
        )
        for index in range(8)
    )
    evidence = normalize_results(
        (_result(MAINTAINABILITY, findings=findings),),
        RULE_CATALOG,
        _config(),
    )

    scorecard = score_evidence(evidence, _config())
    category = next(
        item for item in scorecard.categories if item.category.value == "maintainability"
    )
    impact = next(item for item in category.impacts if item.rule_id == "RI-MAINT-001")

    assert category.score == 85.0
    assert impact.finding_count == 8
    assert impact.raw_deduction == 120.0
    assert impact.applied_deduction == 15.0
    assert impact.cap == 15.0


def test_unavailable_categories_are_null_and_weights_are_renormalized() -> None:
    evidence = normalize_results(
        (
            _result(MAINTAINABILITY),
            _result(DOCUMENTATION, Completeness.UNAVAILABLE),
        ),
        RULE_CATALOG,
        _config(),
    )

    scorecard = score_evidence(evidence, _config())
    maintainability = next(
        item for item in scorecard.categories if item.category.value == "maintainability"
    )
    documentation = next(
        item for item in scorecard.categories if item.category.value == "documentation"
    )

    assert maintainability.score == 100.0
    assert documentation.score is None
    assert scorecard.available_weight == 25.0
    assert scorecard.overall_score == 100.0


def test_partial_category_remains_scored_with_visible_completeness() -> None:
    evidence = normalize_results(
        (_result(MAINTAINABILITY, Completeness.PARTIAL),),
        RULE_CATALOG,
        _config(),
    )

    category = score_evidence(evidence, _config()).categories[0]

    assert category.completeness is Completeness.PARTIAL
    assert category.score == 100.0


def test_decimal_rounding_occurs_once_and_rating_uses_unrounded_value() -> None:
    maintainability_finding = make_finding(
        MAINTAINABILITY.metadata,
        "RI-MAINT-001",
        score_impact=10,
        evidence="ten point deduction",
    )
    documentation_finding = make_finding(
        DOCUMENTATION.metadata,
        "RI-DOC-002",
        score_impact=11,
        evidence="eleven point deduction",
    )
    config = _config(
        {
            "scoring.weights": {
                "maintainability": 95,
                "testing": 0,
                "documentation": 5,
                "security_hygiene": 0,
                "repository_hygiene": 0,
                "maintenance": 0,
            }
        }
    )
    evidence = normalize_results(
        (
            _result(MAINTAINABILITY, findings=(maintainability_finding,)),
            _result(DOCUMENTATION, findings=(documentation_finding,)),
        ),
        RULE_CATALOG,
        config,
    )

    scorecard = score_evidence(evidence, config)

    assert scorecard.overall_score == 90.0
    assert scorecard.rating == "Strong"
    assert scorecard.rounding == "Decimal ROUND_HALF_UP to one decimal; rating uses unrounded score"


def test_no_available_positive_weight_produces_no_overall_score() -> None:
    evidence = normalize_results((), RULE_CATALOG, _config())

    scorecard = score_evidence(evidence, _config())

    assert scorecard.available_weight == 0.0
    assert scorecard.overall_score is None
    assert scorecard.rating is None


def test_category_score_is_clamped_at_zero() -> None:
    findings = tuple(
        make_finding(
            SECURITY.metadata,
            rule.id,
            score_impact=rule.per_rule_cap,
            evidence=rule.id,
        )
        for rule in RULE_CATALOG
        if rule.category.value == "security_hygiene"
    )
    config = _config(
        {
            "scoring.weights": {
                "maintainability": 0,
                "testing": 0,
                "documentation": 0,
                "security_hygiene": 1,
                "repository_hygiene": 0,
                "maintenance": 0,
            }
        }
    )
    evidence = normalize_results(
        (_result(SECURITY, findings=findings),),
        RULE_CATALOG,
        config,
    )

    scorecard = score_evidence(evidence, config)

    assert scorecard.overall_score == 0.0
    assert scorecard.rating == "High maintenance risk"


@pytest.mark.parametrize(
    ("impacts", "expected_score", "expected_rating"),
    [
        pytest.param((10,), 90.0, "Excellent", id="excellent"),
        pytest.param((20,), 80.0, "Strong", id="strong"),
        pytest.param((30,), 70.0, "Healthy", id="healthy"),
        pytest.param((30, 20), 50.0, "Needs improvement", id="needs-improvement"),
        pytest.param((30, 21), 49.0, "High maintenance risk", id="high-risk"),
    ],
)
def test_rating_boundaries(
    impacts: tuple[float, ...],
    expected_score: float,
    expected_rating: str,
) -> None:
    rule_ids = ("RI-SEC-001", "RI-SEC-003")
    findings = tuple(
        make_finding(
            SECURITY.metadata,
            rule_ids[index],
            score_impact=impact,
            evidence=f"deduction {index}",
        )
        for index, impact in enumerate(impacts)
    )
    config = _config(
        {
            "scoring.weights": {
                "maintainability": 0,
                "testing": 0,
                "documentation": 0,
                "security_hygiene": 1,
                "repository_hygiene": 0,
                "maintenance": 0,
            }
        }
    )
    evidence = normalize_results(
        (_result(SECURITY, findings=findings),),
        RULE_CATALOG,
        config,
    )

    scorecard = score_evidence(evidence, config)

    assert scorecard.overall_score == expected_score
    assert scorecard.rating == expected_rating
