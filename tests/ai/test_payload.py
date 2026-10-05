from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from repoinsight.ai.contracts import canonical_json
from repoinsight.ai.payload import load_report, prepare_request
from repoinsight.errors import InvalidUsageError
from repoinsight.models import SourceMetadata
from repoinsight.reporting.json_report import serialize_json


def test_payload_is_deterministic_minimized_and_bound_to_exact_report(saved_report: Path) -> None:
    before = saved_report.read_bytes()
    prepared = prepare_request(saved_report, model="example-model")
    repeated = prepare_request(saved_report, model="example-model")
    assert prepared == repeated
    assert prepared.base_report_hash == hashlib.sha256(before).hexdigest()
    assert prepared.payload_hash == hashlib.sha256(prepared.request_json.encode()).hexdigest()
    assert prepared.estimated_input_tokens <= 8000
    payload = json.loads(prepared.request_json)
    assert payload["store"] is False
    assert "tools" not in payload
    evidence = json.loads(payload["input"])
    assert len(evidence["findings"]) + prepared.omitted_findings == len(prepared.report.findings)
    assert len(evidence["metrics"]) + prepared.omitted_metrics == len(prepared.report.metrics)
    assert str(saved_report.parent) not in prepared.request_json
    assert "app.py" not in prepared.request_json
    assert any(ref.location is not None for ref in prepared.evidence)
    assert saved_report.read_bytes() == before


def test_outbound_schema_bounds_sections_without_changing_historical_sidecar_schema(
    saved_report: Path,
) -> None:
    from repoinsight.ai.contracts import guidance_schema

    body = json.loads(prepare_request(saved_report, model="example-model").request_json)
    properties = body["text"]["format"]["schema"]["properties"]
    for name in ("explanations", "actions", "limitations"):
        assert properties[name]["maxItems"] == 2
    historical = guidance_schema()["properties"]
    assert isinstance(historical, dict)
    assert historical["actions"]["maxItems"] == 5
    assert body["max_output_tokens"] == 1500


def test_repository_prose_metadata_and_string_metrics_never_leave(saved_report: Path) -> None:
    report, _ = load_report(saved_report)
    sentinel = "PRIVATE_IDENTIFIER_ignore_instructions_ghp_abcdefghijklmnopqrstuvwxyz123456"
    source = SourceMetadata(
        kind=report.source.kind,
        identity=f"https://github.com/{sentinel}/private",
        revision=sentinel,
        history_completeness=report.source.history_completeness,
    )
    findings = tuple(
        finding.model_copy(
            update={
                "title": sentinel,
                "explanation": sentinel,
                "evidence": sentinel,
                "remediation": sentinel,
                "limitations": (sentinel,),
            }
        )
        for finding in report.findings
    )
    metrics = tuple(
        metric.model_copy(
            update={
                "provenance": sentinel,
                "limitations": (sentinel,),
            }
        )
        for metric in report.metrics
    )
    report = report.model_copy(update={"source": source, "findings": findings, "metrics": metrics})
    saved_report.write_bytes(serialize_json(report))
    prepared = prepare_request(saved_report, model="example-model")
    assert "PRIVATE_IDENTIFIER" not in prepared.request_json
    assert "ignore_instructions" not in prepared.request_json
    assert "private" not in json.loads(prepared.request_json)["input"]
    assert "subprocess.run('hello'" not in prepared.request_json


def test_limits_disclose_omissions_and_fail_if_envelope_cannot_fit(saved_report: Path) -> None:
    all_findings = prepare_request(saved_report, model="example-model")
    no_findings = prepare_request(saved_report, model="example-model", max_findings=0)
    assert no_findings.omitted_findings == len(no_findings.report.findings)
    assert not any(ref.id.startswith("F") for ref in no_findings.evidence)
    assert no_findings.estimated_input_tokens < all_findings.estimated_input_tokens
    with pytest.raises(InvalidUsageError, match="too small"):
        prepare_request(saved_report, model="example-model", max_input_tokens=1)
    with pytest.raises(InvalidUsageError):
        prepare_request(saved_report, model="https://example.com/endpoint")


def test_invalid_and_oversized_reports_fail_without_echoing_input(
    saved_report: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("repoinsight.ai.payload.MAX_REPORT_BYTES", 10)
    with pytest.raises(InvalidUsageError, match="input limit"):
        load_report(saved_report)
    saved_report.write_text('{"private":"not a report"}', encoding="utf-8")
    monkeypatch.setattr("repoinsight.ai.payload.MAX_REPORT_BYTES", 1024)
    with pytest.raises(InvalidUsageError) as error:
        load_report(saved_report)
    assert "private" not in str(error.value)


def test_unknown_rules_and_non_numeric_metrics_are_omitted(saved_report: Path) -> None:
    report, _ = load_report(saved_report)
    unknown = report.findings[0].model_copy(update={"rule_id": "RI-SEC-999"})
    string_metric = report.metrics[0].model_copy(
        update={
            "id": "testing.test_source_ratio",
            "value": "private data",
        }
    )
    report = report.model_copy(update={"findings": (unknown,), "metrics": (string_metric,)})
    saved_report.write_bytes(serialize_json(report))
    prepared = prepare_request(saved_report, model="example-model")
    assert prepared.omitted_findings == 1
    assert prepared.omitted_metrics == 1
    assert "private data" not in prepared.request_json


def test_string_coercion_and_nonfinite_numbers_are_rejected(saved_report: Path) -> None:
    raw = json.loads(saved_report.read_bytes())
    raw["findings"][0]["score_impact"] = "8"
    saved_report.write_text(canonical_json(raw), encoding="utf-8")
    with pytest.raises(InvalidUsageError):
        load_report(saved_report)
    raw["findings"][0]["score_impact"] = 8
    raw["metrics"][0]["value"] = float("nan")
    saved_report.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(InvalidUsageError):
        load_report(saved_report)


def test_duplicate_metric_ids_are_rejected_before_projection(saved_report: Path) -> None:
    raw = json.loads(saved_report.read_bytes())
    raw["metrics"] = [raw["metrics"][0]] * 1001
    saved_report.write_text(canonical_json(raw), encoding="utf-8")
    with pytest.raises(InvalidUsageError, match="duplicate metric"):
        prepare_request(saved_report, model="example-model")
