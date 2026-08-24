"""Strict TOML configuration discovery, precedence, and fingerprinting."""

from __future__ import annotations

import hashlib
import json
import tomllib
from collections.abc import Mapping
from copy import deepcopy
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from .errors import ConfigurationError
from .models import EffectiveConfig
from .redaction import safe_exception_message

_DEFAULTS: dict[str, Any] = {
    "analysis": {
        "exclude": [],
        "respect_gitignore": True,
        "max_file_bytes": 1_048_576,
        "max_files": 20_000,
        "max_source_bytes": 104_857_600,
        "timeout_seconds": 120,
    },
    "git": {"remote_history_depth": 500, "clone_timeout_seconds": 60},
    "scoring": {
        "weights": {
            "maintainability": 25,
            "testing": 25,
            "documentation": 15,
            "security_hygiene": 15,
            "repository_hygiene": 10,
            "maintenance": 10,
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
        "test_ratio_medium": 0.10,
        "test_ratio_low": 0.25,
        "public_docstring_rate": 0.50,
        "stale_days": 365,
        "activity_window_days": 180,
        "activity_min_commits": 2,
        "single_contributor_min_age_days": 180,
    },
    "output": {"format": "all", "directory": "repoinsight-report"},
    "ci": {"fail_under": 0},
}


def _merge(base: dict[str, Any], override: Mapping[str, object]) -> None:
    for key, value in override.items():
        if isinstance(value, Mapping) and isinstance(base.get(key), dict):
            _merge(base[key], value)
        else:
            base[key] = value


def _expand_cli_overrides(overrides: Mapping[str, object]) -> dict[str, object]:
    expanded: dict[str, object] = {}
    for raw_key, value in overrides.items():
        if not isinstance(raw_key, str) or not raw_key:
            raise ConfigurationError("CLI override keys must be nonempty strings")
        parts = raw_key.split(".")
        if any(not part for part in parts):
            raise ConfigurationError(f"Invalid CLI override key: {raw_key!r}")
        target: dict[str, object] = expanded
        for part in parts[:-1]:
            existing = target.get(part)
            if existing is None:
                nested: dict[str, object] = {}
                target[part] = nested
                target = nested
            elif isinstance(existing, dict):
                target = existing
            else:
                raise ConfigurationError(f"Conflicting CLI override key: {raw_key!r}")
        leaf = parts[-1]
        if leaf in target and isinstance(target[leaf], Mapping) != isinstance(value, Mapping):
            raise ConfigurationError(f"Conflicting CLI override key: {raw_key!r}")
        if isinstance(value, Mapping):
            nested_value = _expand_cli_overrides(value)
            existing_leaf = target.get(leaf)
            if isinstance(existing_leaf, dict):
                _merge(existing_leaf, nested_value)
            else:
                target[leaf] = nested_value
        else:
            target[leaf] = value
    return expanded


def _read_toml(path: Path) -> dict[str, object]:
    try:
        with path.open("rb") as stream:
            loaded = tomllib.load(stream)
    except (OSError, tomllib.TOMLDecodeError) as error:
        safe_message = f"Unable to read configuration {path}: {safe_exception_message(error)}"
    else:
        return loaded
    raise ConfigurationError(safe_message)


def load_config(
    source_root: Path | None,
    explicit_path: Path | None,
    cli_overrides: Mapping[str, object],
) -> EffectiveConfig:
    """Load defaults, then one TOML file, then CLI overrides."""
    merged = deepcopy(_DEFAULTS)
    config_path = explicit_path
    if config_path is None and source_root is not None:
        discovered = source_root / ".repoinsight.toml"
        if discovered.is_file():
            config_path = discovered
    if config_path is not None:
        _merge(merged, _read_toml(config_path))
    _merge(merged, _expand_cli_overrides(cli_overrides))
    try:
        serialized = json.dumps(merged, ensure_ascii=False)
        effective = EffectiveConfig.model_validate_json(serialized)
    except (TypeError, ValueError, ValidationError) as error:
        safe_message = f"Invalid configuration: {safe_exception_message(error)}"
    else:
        return effective
    raise ConfigurationError(safe_message)


def configuration_fingerprint(config: EffectiveConfig) -> str:
    """Hash every effective setting except report output selection and location."""
    payload = config.model_dump(mode="json")
    del payload["output"]
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


__all__ = ["ConfigurationError", "configuration_fingerprint", "load_config"]
