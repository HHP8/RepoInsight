"""Deterministic category and weighted-overall score calculation."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from .analyzers._shared import is_rule_enabled
from .analyzers.catalog import RULE_CATALOG
from .models import (
    Category,
    CategoryScoreTrace,
    Completeness,
    EffectiveConfig,
    RuleImpactTrace,
    Scorecard,
)
from .normalization import NormalizedEvidence

_ROUNDING = "Decimal ROUND_HALF_UP to one decimal; rating uses unrounded score"


def _decimal(value: float) -> Decimal:
    return Decimal(str(value))


def _rating(score: Decimal) -> str:
    if score >= Decimal("90"):
        return "Excellent"
    if score >= Decimal("80"):
        return "Strong"
    if score >= Decimal("70"):
        return "Healthy"
    if score >= Decimal("50"):
        return "Needs improvement"
    return "High maintenance risk"


def score_evidence(evidence: NormalizedEvidence, config: EffectiveConfig) -> Scorecard:
    """Calculate traceable scores from normalized, already-capped evidence."""
    completeness = dict(evidence.category_completeness)
    raw = dict(evidence.raw_deductions)
    applied: dict[str, float] = {}
    counts: dict[str, int] = {}
    for finding in evidence.findings:
        counts[finding.rule_id] = counts.get(finding.rule_id, 0) + 1
        applied[finding.rule_id] = applied.get(finding.rule_id, 0.0) + finding.score_impact

    weights = config.scoring.weights.model_dump()
    categories: list[CategoryScoreTrace] = []
    unrounded_scores: dict[Category, Decimal] = {}
    for category in Category:
        state = completeness.get(category, Completeness.UNAVAILABLE)
        category_rules = tuple(
            rule
            for rule in RULE_CATALOG
            if rule.category is category and is_rule_enabled(config, rule.id)
        )
        impacts = tuple(
            RuleImpactTrace(
                rule_id=rule.id,
                finding_count=counts.get(rule.id, 0),
                raw_deduction=raw.get(rule.id, 0.0),
                applied_deduction=applied.get(rule.id, 0.0),
                cap=rule.per_rule_cap,
            )
            for rule in category_rules
        )
        category_limitations = tuple(
            sorted({item.message for item in evidence.limitations if item.category is category})
        )
        score: float | None
        if state in {Completeness.UNAVAILABLE, Completeness.SKIPPED}:
            score = None
            if not category_limitations:
                category_limitations = ("Category evidence is unavailable",)
        else:
            deduction = sum((_decimal(item.applied_deduction) for item in impacts), Decimal(0))
            unrounded = max(Decimal(0), min(Decimal(100), Decimal(100) - deduction))
            unrounded_scores[category] = unrounded
            score = float(unrounded)
        categories.append(
            CategoryScoreTrace(
                category=category,
                baseline=100.0,
                score=score,
                weight=float(weights[category.value]),
                completeness=state,
                impacts=impacts,
                limitations=category_limitations,
            )
        )

    available_weight = sum(
        _decimal(item.weight) for item in categories if item.score is not None and item.weight > 0
    )
    if available_weight == 0:
        overall_score = None
        rating = None
    else:
        weighted = sum(
            (
                unrounded_scores[item.category] * _decimal(item.weight)
                for item in categories
                if item.score is not None and item.weight > 0
            ),
            Decimal(0),
        )
        unrounded_overall = weighted / available_weight
        overall_score = float(unrounded_overall.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))
        rating = _rating(unrounded_overall)

    return Scorecard(
        categories=tuple(categories),
        overall_score=overall_score,
        rating=rating,
        available_weight=float(available_weight),
        rounding=_ROUNDING,
    )


__all__ = ["score_evidence"]
