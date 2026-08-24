from __future__ import annotations

import importlib
import traceback
from pathlib import Path

import pytest


def test_configuration_defaults_match_the_public_contract() -> None:
    config_module = importlib.import_module("repoinsight.config")

    config = config_module.load_config(None, None, {})

    assert config.model_dump(mode="json") == {
        "analysis": {
            "exclude": [],
            "respect_gitignore": True,
            "max_file_bytes": 1048576,
            "max_files": 20000,
            "max_source_bytes": 104857600,
            "timeout_seconds": 120,
        },
        "git": {"remote_history_depth": 500, "clone_timeout_seconds": 60},
        "scoring": {
            "weights": {
                "maintainability": 25.0,
                "testing": 25.0,
                "documentation": 15.0,
                "security_hygiene": 15.0,
                "repository_hygiene": 10.0,
                "maintenance": 10.0,
            }
        },
        "rules": {"enabled": [], "disabled": []},
        "thresholds": {
            "complexity": 15,
            "function_loc": 75,
            "class_loc": 500,
            "module_loc": 1000,
            "nesting_depth": 5,
            "duplicate_statements": 8,
            "test_ratio_medium": 0.1,
            "test_ratio_low": 0.25,
            "public_docstring_rate": 0.5,
            "stale_days": 365,
            "activity_window_days": 180,
            "activity_min_commits": 2,
            "single_contributor_min_age_days": 180,
        },
        "output": {"format": "all", "directory": "repoinsight-report"},
        "ci": {"fail_under": 0.0},
    }


def test_project_toml_and_cli_precedence(tmp_path: Path) -> None:
    config_module = importlib.import_module("repoinsight.config")
    (tmp_path / ".repoinsight.toml").write_text(
        """
[analysis]
max_files = 100
[output]
format = "json"
[thresholds]
complexity = 20
""".strip(),
        encoding="utf-8",
    )

    config = config_module.load_config(
        tmp_path,
        None,
        {"analysis.max_files": 50, "thresholds": {"complexity": 25}},
    )

    assert config.analysis.max_files == 50
    assert config.thresholds.complexity == 25
    assert config.output.format == "json"
    assert config.analysis.max_file_bytes == 1048576


def test_explicit_config_wins_over_discovered_project_file(tmp_path: Path) -> None:
    config_module = importlib.import_module("repoinsight.config")
    (tmp_path / ".repoinsight.toml").write_text("[analysis]\nmax_files = 100\n", encoding="utf-8")
    explicit = tmp_path / "explicit.toml"
    explicit.write_text("[analysis]\nmax_files = 75\n", encoding="utf-8")

    config = config_module.load_config(tmp_path, explicit, {})

    assert config.analysis.max_files == 75


@pytest.mark.parametrize(
    "contents",
    [
        "[analysis]\nunknown = 1\n",
        "[unknown]\nvalue = 1\n",
        "[analysis]\nmax_files = 0\n",
        "[scoring.weights]\n"
        "maintainability = 0\n"
        "testing = 0\n"
        "documentation = 0\n"
        "security_hygiene = 0\n"
        "repository_hygiene = 0\n"
        "maintenance = 0\n",
        "[thresholds]\ntest_ratio_medium = 0.3\ntest_ratio_low = 0.2\n",
        '[rules]\nenabled = ["RI-SEC-001"]\ndisabled = ["RI-SEC-001"]\n',
        '[rules]\nenabled = ["RI-NOT-REAL"]\n',
        '[analysis]\nexclude = ["!"]\n',
    ],
)
def test_invalid_configuration_fails(contents: str, tmp_path: Path) -> None:
    config_module = importlib.import_module("repoinsight.config")
    path = tmp_path / "bad.toml"
    path.write_text(contents, encoding="utf-8")

    with pytest.raises(config_module.ConfigurationError):
        config_module.load_config(None, path, {})


def test_cli_unknown_key_fails() -> None:
    config_module = importlib.import_module("repoinsight.config")

    with pytest.raises(config_module.ConfigurationError):
        config_module.load_config(None, None, {"analysis.unknown": 1})


def test_configuration_read_failure_drops_unsafe_exception_chain(tmp_path: Path) -> None:
    config_module = importlib.import_module("repoinsight.config")
    secret = "hunter2-secret"
    missing = tmp_path / f"password={secret}.toml"

    with pytest.raises(config_module.ConfigurationError) as captured:
        config_module.load_config(None, missing, {})

    rendered = "".join(traceback.format_exception(captured.value))
    assert secret not in rendered
    assert captured.value.__cause__ is None
    assert captured.value.__context__ is None


def test_configuration_validation_failure_drops_underlying_exception() -> None:
    config_module = importlib.import_module("repoinsight.config")

    with pytest.raises(config_module.ConfigurationError) as captured:
        config_module.load_config(None, None, {"analysis.unknown": 1})

    assert captured.value.__cause__ is None
    assert captured.value.__context__ is None


def test_configuration_fingerprint_is_canonical_and_excludes_output() -> None:
    config_module = importlib.import_module("repoinsight.config")
    base = config_module.load_config(None, None, {})
    output_changed = config_module.load_config(
        None, None, {"output.format": "json", "output.directory": "elsewhere"}
    )
    analysis_changed = config_module.load_config(None, None, {"analysis.max_files": 999})

    assert config_module.configuration_fingerprint(base) == (
        config_module.configuration_fingerprint(output_changed)
    )
    assert config_module.configuration_fingerprint(base) != (
        config_module.configuration_fingerprint(analysis_changed)
    )
    assert len(config_module.configuration_fingerprint(base)) == 64
