"""Validate one or more RepoInsight JSON files against the packaged schema."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from jsonschema import Draft202012Validator

from repoinsight.schema import report_json_schema


def validate_paths(paths: tuple[Path, ...]) -> None:
    """Raise when any supplied JSON report violates the public contract."""
    validator = Draft202012Validator(report_json_schema())
    for path in paths:
        payload = json.loads(path.read_text(encoding="utf-8"))
        validator.validate(payload)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("reports", nargs="+", type=Path)
    arguments = parser.parse_args()
    validate_paths(tuple(arguments.reports))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
