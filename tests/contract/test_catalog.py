import pytest
from pydantic import ValidationError

from repoinsight.analyzers import catalog

EXPECTED_IDS = (
    "RI-MAINT-001",
    "RI-MAINT-002",
    "RI-MAINT-003",
    "RI-MAINT-004",
    "RI-MAINT-005",
    "RI-MAINT-006",
    "RI-MAINT-007",
    "RI-MAINT-008",
    "RI-MAINT-009",
    "RI-TEST-001",
    "RI-TEST-002",
    "RI-TEST-003",
    "RI-TEST-004",
    "RI-TEST-005",
    "RI-TEST-006",
    "RI-DOC-001",
    "RI-DOC-002",
    "RI-DOC-003",
    "RI-DOC-004",
    "RI-DOC-005",
    "RI-DOC-006",
    "RI-SEC-001",
    "RI-SEC-002",
    "RI-SEC-003",
    "RI-SEC-004",
    "RI-SEC-005",
    "RI-SEC-006",
    "RI-SEC-007",
    "RI-REPO-001",
    "RI-REPO-002",
    "RI-REPO-003",
    "RI-REPO-004",
    "RI-REPO-005",
    "RI-REPO-006",
    "RI-REPO-007",
    "RI-REPO-008",
    "RI-HIST-001",
    "RI-HIST-002",
    "RI-HIST-003",
    "RI-HIST-004",
    "RI-HIST-005",
)


def test_catalog_contains_exactly_the_41_stable_rules_in_order() -> None:
    assert tuple(rule.id for rule in catalog.RULE_CATALOG) == EXPECTED_IDS
    assert frozenset(EXPECTED_IDS) == catalog.RULE_IDS


def test_every_catalog_record_has_complete_immutable_metadata() -> None:
    for rule in catalog.RULE_CATALOG:
        assert rule.title
        assert rule.evidence_definition
        assert rule.remediation
        assert rule.default_enabled is True
        assert rule.default_deduction >= 0
        assert rule.per_rule_cap >= rule.default_deduction
        assert rule.confidence.value in {"low", "medium", "high"}
        assert rule.severity.value in {"info", "low", "medium", "high", "critical"}
        with pytest.raises(ValidationError, match="frozen"):
            rule.title = "changed"  # type: ignore[misc]


def test_threshold_and_heuristic_metadata_matches_key_contract_entries() -> None:
    by_id = {rule.id: rule for rule in catalog.RULE_CATALOG}

    complexity = by_id["RI-MAINT-001"]
    assert complexity.threshold_key == "complexity"
    assert complexity.threshold_value == 15
    assert complexity.default_deduction == 3
    assert complexity.per_rule_cap == 15
    assert complexity.heuristic is True

    secrets = by_id["RI-SEC-001"]
    assert secrets.severity.value == "high"
    assert secrets.default_deduction == 10
    assert secrets.per_rule_cap == 30
    assert secrets.heuristic is True
    assert "Possible secret" in secrets.evidence_definition
    assert "redact" in secrets.limitations.lower()

    partial_history = by_id["RI-HIST-004"]
    assert partial_history.default_deduction == 0
    assert partial_history.per_rule_cap == 0
    assert partial_history.heuristic is False
