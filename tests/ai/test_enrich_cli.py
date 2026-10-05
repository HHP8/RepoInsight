from __future__ import annotations

import builtins
import json
from pathlib import Path
from typing import Any

import pytest

from repoinsight.ai.models import Guidance
from repoinsight.ai.payload import prepare_request
from repoinsight.ai.provider import ProviderResult
from repoinsight.cli import main
from repoinsight.errors import EnrichmentError
from repoinsight.exit_codes import ExitCode


def test_preview_needs_no_key_or_http_dependency_and_outputs_exact_request(
    saved_report: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    original = builtins.__import__

    def reject_http(name: str, *args: Any, **kwargs: Any) -> Any:
        if name == "httpx":
            raise AssertionError("Preview must not import the HTTP transport")
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", reject_http)
    assert main(["enrich", str(saved_report), "--preview", "--model", "example-model"]) == 0
    captured = capsys.readouterr()
    assert captured.out.strip() == prepare_request(saved_report, model="example-model").request_json
    assert "Conservative input estimate" in captured.err
    assert json.loads(captured.out)["model"] == "example-model"


@pytest.mark.parametrize("flags", [[], ["--preview", "--send"]])
def test_explicit_mutually_exclusive_consent_is_required(
    saved_report: Path,
    flags: list[str],
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["enrich", str(saved_report), *flags, "--model", "example-model"]) == 20
    assert "exactly one" in capsys.readouterr().err


def test_send_missing_key_and_dependency_use_actionable_usage_errors(
    saved_report: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    args = ["enrich", str(saved_report), "--send", "--model", "example-model"]
    assert main(args) == ExitCode.INVALID_USAGE
    assert "OPENAI_API_KEY" in capsys.readouterr().err
    original = builtins.__import__

    def missing_http(name: str, *args: Any, **kwargs: Any) -> Any:
        if name == "httpx":
            raise ImportError("synthetic missing optional dependency")
        return original(name, *args, **kwargs)

    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-active-key")
    monkeypatch.setattr(builtins, "__import__", missing_http)
    assert main(args) == ExitCode.INVALID_USAGE
    captured = capsys.readouterr()
    assert "repoinsight[ai]" in captured.err
    assert "synthetic-active-key" not in captured.err


def test_cli_does_not_echo_active_key_used_as_model(
    saved_report: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "short-active-credential")
    assert (
        main(["enrich", str(saved_report), "--preview", "--model", "short-active-credential"]) == 20
    )
    assert "short-active-credential" not in capsys.readouterr().err


def test_repo_configuration_cannot_enable_ai(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / ".repoinsight.toml").write_text("[ai]\nsend = true\n", encoding="utf-8")
    assert main(["analyze", str(tmp_path), "--output", str(tmp_path / "reports")]) == 20
    assert "Invalid configuration" in capsys.readouterr().err


def test_cli_send_generates_reports_and_failure_uses_code_24(
    saved_report: Path,
    guidance: Guidance,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-active-key")
    before = saved_report.read_bytes()
    requests: list[str] = []

    def succeed(
        self: object, request_json: str, api_key: str, timeout_seconds: float
    ) -> ProviderResult:
        requests.append(request_json)
        return ProviderResult(text=guidance.model_dump_json(), usage=None)

    monkeypatch.setattr("repoinsight.ai.provider.OpenAIProvider.generate", succeed)
    output = tmp_path / "ai"
    args = [
        "enrich",
        str(saved_report),
        "--send",
        "--model",
        "example-model",
        "--output",
        str(output),
    ]
    assert main(args) == 0
    assert "AI guidance written" in capsys.readouterr().out
    assert requests == [prepare_request(saved_report, model="example-model").request_json]
    assert (output / "repoinsight-ai.html").is_file()

    def fail(
        self: object, request_json: str, api_key: str, timeout_seconds: float
    ) -> ProviderResult:
        raise EnrichmentError("synthetic-active-key failure")

    monkeypatch.setattr("repoinsight.ai.provider.OpenAIProvider.generate", fail)
    assert main(args) == 24
    assert "synthetic-active-key" not in capsys.readouterr().err
    assert json.loads((output / "repoinsight-ai.json").read_bytes())["status"] == "failed"
    assert saved_report.read_bytes() == before
