from __future__ import annotations

import importlib


def test_public_versions_are_stable() -> None:
    package = importlib.import_module("repoinsight")
    version = importlib.import_module("repoinsight.version")

    assert package.__version__ == "1.0.0"
    assert version.SCHEMA_VERSION == "1.0"
    assert version.SCORE_CONTRACT_VERSION == "1.0"


def test_exit_codes_match_the_public_process_contract() -> None:
    exit_codes = importlib.import_module("repoinsight.exit_codes")

    assert {member.name: member.value for member in exit_codes.ExitCode} == {
        "SUCCESS": 0,
        "THRESHOLD_FAILED": 10,
        "INVALID_USAGE": 20,
        "ACQUISITION_FAILED": 21,
        "ANALYSIS_FAILED": 22,
        "REPORT_FAILED": 23,
    }
