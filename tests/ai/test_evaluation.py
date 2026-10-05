from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pytest
from tools.ai_evaluation import MODEL, digest, generate, replay, send_case, write_json

from repoinsight.ai.models import Guidance


def test_curated_corpus_has_expected_evidence_and_private_previews(tmp_path: Path) -> None:
    generate(tmp_path / "corpus")
    entries = json.loads((tmp_path / "corpus/manifest.json").read_bytes())
    assert len(entries) == 20
    expected = {
        2: "RI-MAINT-001",
        3: "RI-MAINT-002",
        4: "RI-MAINT-005",
        5: "RI-MAINT-006",
        6: "RI-TEST-001",
        7: "RI-TEST-002",
        8: "RI-TEST-006",
        10: "RI-DOC-001",
        11: "RI-DOC-002",
        12: "RI-DOC-003",
        13: "RI-SEC-001",
        14: "RI-SEC-003",
        15: "RI-SEC-004",
        16: "RI-REPO-001",
    }
    for entry in entries:
        if entry["case"] in expected:
            assert expected[entry["case"]] in entry["rules"]
        assert entry["model"] == MODEL
        assert entry["estimated_input_tokens"] <= 8000
    assert any(
        m["metric"] == "testing.ci_test_evidence" and m["value"] is True
        for m in entries[8]["metrics"]
    )
    assert any(
        m["metric"] == "maintenance.git_available" and m["completeness"] == "partial"
        for m in entries[17]["metrics"]
    )
    bad = json.loads((tmp_path / "corpus/19-oversized-malformed/preview.json").read_bytes())
    assert json.loads(bad["input"])["skipped_input_count"] == 2


def test_live_audit_pins_preview_model_and_records_one_retry(
    saved_report: Path,
    guidance: Guidance,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from repoinsight.ai.payload import prepare_request

    case = tmp_path / "case"
    (case / "static").mkdir(parents=True)
    base = case / "static/repoinsight-report.json"
    base.write_bytes(saved_report.read_bytes())
    html = case / "static/repoinsight-report.html"
    html.write_text("unchanged static HTML", encoding="utf-8")
    prepared = prepare_request(base, model=MODEL)
    write_json(case / "preview.json", json.loads(prepared.request_json))
    entry = {
        "case": 1,
        "base_sha256": digest(base),
        "html_sha256": digest(html),
        "payload_sha256": prepared.payload_hash,
    }
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        assert json.loads(request.content)["model"] == MODEL
        assert request.content.decode() == prepared.request_json
        if len(calls) == 1:
            return httpx.Response(503)
        return httpx.Response(
            200,
            stream=httpx.ByteStream(
                json.dumps(
                    {
                        "status": "completed",
                        "output": [
                            {
                                "type": "message",
                                "role": "assistant",
                                "status": "completed",
                                "content": [
                                    {"type": "output_text", "text": guidance.model_dump_json()}
                                ],
                            }
                        ],
                        "usage": {"input_tokens": 100, "output_tokens": 50},
                    }
                ).encode()
            ),
        )

    client = httpx.Client

    def client_factory(**kwargs: Any) -> httpx.Client:
        return client(**kwargs, transport=httpx.MockTransport(handler))

    monkeypatch.setattr(httpx, "Client", client_factory)
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-evaluation-key")
    assert send_case(case, entry, "synthetic-evaluation-key") is False
    attempt = json.loads((case / "attempt.json").read_bytes())
    assert attempt["statuses"] == [503, 200]
    assert attempt["exit_code"] == 0
    assert len(attempt["requests"]) == 2
    assert attempt["base_unchanged"] and attempt["html_unchanged"]
    assert "synthetic-evaluation-key" not in (case / "attempt.json").read_text()


def test_live_audit_rejects_changed_preview_before_transmission(
    saved_report: Path,
    tmp_path: Path,
) -> None:
    case = tmp_path / "case"
    (case / "static").mkdir(parents=True)
    base = case / "static/repoinsight-report.json"
    base.write_bytes(saved_report.read_bytes())
    write_json(case / "preview.json", {"model": "unauthorized-model"})
    with pytest.raises(AssertionError):
        send_case(case, {"base_sha256": digest(base)}, "synthetic-key")
    assert not (case / "attempt.json").exists()


def test_replay_records_compact_rejection_continues_and_accepts_unknown_usage(
    saved_report: Path, guidance: Guidance, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from repoinsight.ai.payload import prepare_request
    from repoinsight.ai.provider import OpenAIProvider

    def forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError("Offline replay must not call the live provider")

    monkeypatch.setattr(OpenAIProvider, "generate", forbidden)
    entries: list[dict[str, object]] = []
    for number, response in enumerate(
        (guidance.model_copy(update={"summary": "Review " * 181}), guidance), 1
    ):
        case = tmp_path / f"{number:02}-synthetic"
        (case / "static").mkdir(parents=True)
        (case / "ai").mkdir()
        base = case / "static/repoinsight-report.json"
        base.write_bytes(saved_report.read_bytes())
        html = case / "static/repoinsight-report.html"
        html.write_text("unchanged static HTML", encoding="utf-8")
        prepared = prepare_request(base, model=MODEL)
        write_json(case / "preview.json", json.loads(prepared.request_json))
        write_json(case / "sanitized-response.json", response.model_dump(mode="json"))
        write_json(case / "ai/repoinsight-ai.json", {"usage": None, "status": "succeeded"})
        entries.append(
            {
                "case": number,
                "directory": case.name,
                "base_sha256": digest(base),
                "html_sha256": digest(html),
                "payload_sha256": prepared.payload_hash,
                "estimated_input_tokens": prepared.estimated_input_tokens,
                "prompt_version": prepared.prompt_version,
            }
        )
    write_json(tmp_path / "manifest.json", entries)
    replay(tmp_path)
    results = json.loads((tmp_path / "offline-replay-results.json").read_bytes())
    assert [item["status"] for item in results] == ["rejected", "accepted"]
    assert "180-word" in results[0]["reason"]
    for entry in entries:
        case = tmp_path / str(entry["directory"])
        assert digest(case / "static/repoinsight-report.json") == entry["base_sha256"]
        assert digest(case / "static/repoinsight-report.html") == entry["html_sha256"]
        sidecar = json.loads((case / "ai-offline-replay/repoinsight-ai.json").read_bytes())
        assert sidecar["usage"] is None
        assert json.loads((case / "ai/repoinsight-ai.json").read_bytes())["status"] == "succeeded"
