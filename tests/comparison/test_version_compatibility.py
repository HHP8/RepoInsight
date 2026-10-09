from __future__ import annotations

import builtins
import hashlib
import json
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator
from pydantic import ValidationError

from repoinsight.ai.payload import load_report as enrichment_loader
from repoinsight.ai.payload import prepare_request
from repoinsight.cli import main
from repoinsight.comparison import compare_reports
from repoinsight.comparison_models import InputSummary
from repoinsight.errors import InvalidUsageError
from repoinsight.models import AnalysisReport
from repoinsight.reporting.comparison import comparison_schema, serialize_comparison
from repoinsight.saved_reports import load_report
from repoinsight.schema import report_json_schema

from .conftest import ReportFactory, finding

SUPPORTED = ("1.0.0", "1.1.0", "1.2.0")


def _saved_version(path: Path, version: str) -> None:
    data = json.loads(path.read_bytes())
    data["tool"]["version"] = version
    path.write_bytes(json.dumps(data).encode("utf-8"))


@pytest.mark.parametrize("before_version", SUPPORTED)
@pytest.mark.parametrize("after_version", SUPPORTED)
def test_supported_report_pairs_preserve_evidence_and_disclose_tool_differences(
    report_factory: ReportFactory, before_version: str, after_version: str
) -> None:
    before = report_factory(findings=(finding(),))
    after = report_factory(findings=(finding(),))
    _saved_version(before, before_version)
    _saved_version(after, after_version)
    raw_before, raw_after = before.read_bytes(), after.read_bytes()
    for path, version in ((before, before_version), (after, after_version)):
        Draft202012Validator(report_json_schema()).validate(json.loads(path.read_bytes()))
        report, digest = load_report(path)
        assert report.tool.version == version
        assert enrichment_loader(path) == (report, digest)
        prepared = prepare_request(path, model="gpt-6-luna")
        assert prepared.base_report_hash == digest
        assert json.loads(prepared.request_json)["store"] is False
    result = compare_reports(before, after)
    assert result.before.tool_version == before_version
    assert result.after.tool_version == after_version
    assert result.before.sha256 == hashlib.sha256(raw_before).hexdigest()
    assert result.after.sha256 == hashlib.sha256(raw_after).hexdigest()
    assert result.counts.unchanged == 1 and result.counts.changed == result.counts.new == 0
    assert result.overall.delta == 0
    assert ("tool" in result.compatibility.differences) == (before_version != after_version)
    assert result.compatibility.scores_interpretable == (before_version == after_version)
    if before_version != after_version:
        assert "score-deltas-require-context" in result.warnings
    Draft202012Validator(comparison_schema()).validate(json.loads(serialize_comparison(result)))
    assert before.read_bytes() == raw_before and after.read_bytes() == raw_after


@pytest.mark.parametrize("future", ("1.3.0", "2.0.0"))
def test_future_tool_versions_fail_static_comparison_and_enrichment_boundaries(
    report_factory: ReportFactory, future: str
) -> None:
    supported = report_factory(findings=(finding(),))
    unknown = report_factory(findings=(finding(),))
    _saved_version(unknown, future)
    raw = unknown.read_bytes()
    assert not Draft202012Validator(report_json_schema()).is_valid(json.loads(raw))
    with pytest.raises(ValidationError):
        AnalysisReport.model_validate_json(raw, strict=False)
    for loader in (load_report, enrichment_loader):
        with pytest.raises(InvalidUsageError):
            loader(unknown)
    with pytest.raises(InvalidUsageError):
        compare_reports(supported, unknown)
    with pytest.raises(InvalidUsageError):
        prepare_request(unknown, model="gpt-6-luna")
    comparison = json.loads(serialize_comparison(compare_reports(supported, supported)))
    comparison["after"]["tool_version"] = future
    assert not Draft202012Validator(comparison_schema()).is_valid(comparison)
    with pytest.raises(ValidationError):
        InputSummary.model_validate_json(json.dumps(comparison["after"]), strict=False)
    assert unknown.read_bytes() == raw


def test_newly_analyzed_candidate_report_compares_and_previews_without_transport(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    root = tmp_path / "controlled"
    root.mkdir()
    (root / "module.py").write_text("value = 1\n", encoding="utf-8")
    output = tmp_path / "reports"
    assert main(["analyze", str(root), "--output", str(output), "--format", "json"]) == 0
    capsys.readouterr()
    saved = output / "repoinsight-report.json"
    raw = saved.read_bytes()
    report, digest = load_report(saved)
    assert report.tool.version == "1.2.0"
    assert report.schema_version == report.score_contract_version == "1.0"
    assert main(["compare", str(saved), str(saved), "--format", "json"]) == 0
    comparison = json.loads(capsys.readouterr().out)
    assert comparison["before"]["tool_version"] == comparison["after"]["tool_version"] == "1.2.0"
    Draft202012Validator(comparison_schema()).validate(comparison)
    original_import = builtins.__import__

    def no_transport(name: str, *args: Any, **kwargs: Any) -> Any:
        if name == "httpx":
            pytest.fail("Offline preview must not import the HTTP transport")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", no_transport)
    assert main(["enrich", str(saved), "--preview", "--model", "gpt-6-luna"]) == 0
    captured = capsys.readouterr()
    assert captured.out.strip() == prepare_request(saved, model="gpt-6-luna").request_json
    preview = json.loads(captured.out)
    assert preview["model"] == "gpt-6-luna" and preview["store"] is False
    assert preview["max_output_tokens"] == 1500
    assert saved.read_bytes() == raw and digest == hashlib.sha256(raw).hexdigest()
