from __future__ import annotations

from pathlib import Path

import pytest

from repoinsight.ai.models import Action, Explanation, Guidance
from repoinsight.application import AnalyzeService
from repoinsight.models import AnalysisRequest, OutputFormat


@pytest.fixture
def saved_report(tmp_path: Path) -> Path:
    root = tmp_path / "repository"
    root.mkdir()
    (root / "app.py").write_text(
        "import subprocess\nsubprocess.run('hello', shell=True)\n", encoding="utf-8"
    )
    outcome = AnalyzeService().analyze(
        AnalysisRequest(
            source=str(root),
            output_directory=tmp_path / "static",
            formats=(OutputFormat.JSON,),
            cli_overrides={},
        )
    )
    return outcome.output_paths[0]


@pytest.fixture
def guidance() -> Guidance:
    return Guidance(
        summary="Static evidence indicates opportunities for improvement.",
        explanations=(
            Explanation(evidence_id="C001", text="Maintainability reflects static evidence."),
        ),
        actions=(
            Action(
                title="Review branch responsibilities",
                priority=1,
                effort="small",
                hypothesis=True,
                rationale="Static signals warrant developer review.",
                suggested_change="Consider extracting focused helpers after reviewing behavior.",
                verification="Add appropriate branch cases and run tests separately.",
                evidence_ids=("C001",),
            ),
        ),
        limitations=("Static evidence cannot verify runtime behavior.",),
    )
