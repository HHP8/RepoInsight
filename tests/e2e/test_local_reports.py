from __future__ import annotations

import json
from pathlib import Path

import pytest

from repoinsight.cli import main
from repoinsight.exit_codes import ExitCode


def test_local_json_and_html_reports_share_the_same_score(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    root = tmp_path / "repository"
    root.mkdir()
    (root / "README.md").write_text(
        "# Demo\n\n## Overview\nDemo.\n\n## Installation\n`pip install demo`\n\n"
        "## Usage\n```python\nimport demo\n```\n",
        encoding="utf-8",
    )
    (root / "demo.py").write_text('"""Demo."""\nvalue = 1\n', encoding="utf-8")
    output = tmp_path / "reports"

    result = main(["analyze", str(root), "--output", str(output), "--format", "all"])
    capsys.readouterr()
    data = json.loads((output / "repoinsight-report.json").read_text(encoding="utf-8"))
    html = (output / "repoinsight-report.html").read_text(encoding="utf-8")

    assert result == ExitCode.SUCCESS
    assert data["schema_version"] == "1.0"
    assert f">{data['scorecard']['overall_score']:.1f}<" in html
    assert "<!doctype html>" in html
