from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import httpx
import pytest

from repoinsight.ai.models import Guidance
from repoinsight.ai.provider import (
    ENDPOINT,
    MAX_RESPONSE_BYTES,
    OpenAIProvider,
    ProviderResponseError,
    decode_response,
)
from repoinsight.errors import EnrichmentError


def envelope(guidance: Guidance) -> bytes:
    return json.dumps(
        {
            "status": "completed",
            "output": [
                {
                    "type": "message",
                    "role": "assistant",
                    "status": "completed",
                    "content": [{"type": "output_text", "text": guidance.model_dump_json()}],
                }
            ],
            "usage": {"input_tokens": 100, "output_tokens": 50},
        }
    ).encode()


def install_transport(
    monkeypatch: pytest.MonkeyPatch,
    handler: Callable[[httpx.Request], httpx.Response],
) -> list[httpx.Request]:
    real_client = httpx.Client
    requests: list[httpx.Request] = []

    def wrapped(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return handler(request)

    def client(**kwargs: Any) -> httpx.Client:
        assert kwargs["follow_redirects"] is False
        assert kwargs["trust_env"] is False
        assert kwargs["verify"] is True
        return real_client(transport=httpx.MockTransport(wrapped), **kwargs)

    monkeypatch.setattr(httpx, "Client", client)
    return requests


def test_fixed_endpoint_and_exact_request_are_sent_once(
    guidance: Guidance,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requests = install_transport(
        monkeypatch,
        lambda request: httpx.Response(
            200,
            stream=httpx.ByteStream(envelope(guidance)),
        ),
    )
    result = OpenAIProvider().generate('{"exact":"body"}', "synthetic-key", 30)
    assert result.text == guidance.model_dump_json()
    assert result.usage is not None and result.usage.output_tokens == 50
    assert len(requests) == 1
    assert str(requests[0].url) == ENDPOINT
    assert requests[0].content == b'{"exact":"body"}'
    assert requests[0].headers["authorization"] == "Bearer synthetic-key"


@pytest.mark.parametrize("status", [401, 403, 302, 400])
def test_authentication_and_redirects_are_never_retried(
    monkeypatch: pytest.MonkeyPatch,
    status: int,
) -> None:
    requests = install_transport(
        monkeypatch,
        lambda request: httpx.Response(
            status,
            headers={"location": "https://example.com/steal"},
            stream=httpx.ByteStream(b"synthetic-key must not be exposed"),
        ),
    )
    with pytest.raises(EnrichmentError) as error:
        OpenAIProvider().generate("{}", "synthetic-key", 30)
    assert len(requests) == 1
    assert "synthetic-key" not in str(error.value)


@pytest.mark.parametrize("status", [429, 500, 503])
def test_transient_failures_have_at_most_one_retry(
    monkeypatch: pytest.MonkeyPatch,
    status: int,
) -> None:
    requests = install_transport(
        monkeypatch,
        lambda request: httpx.Response(
            status,
            stream=httpx.ByteStream(b"ignored"),
        ),
    )
    with pytest.raises(EnrichmentError):
        OpenAIProvider().generate("{}", "synthetic-key", 30)
    assert len(requests) == 2


def test_transport_exceptions_are_not_echoed(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("Authorization: synthetic-key", request=request)

    requests = install_transport(monkeypatch, fail)
    with pytest.raises(EnrichmentError) as error:
        OpenAIProvider().generate("{}", "synthetic-key", 30)
    assert len(requests) == 2
    assert "synthetic-key" not in str(error.value)


def test_oversized_response_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    install_transport(
        monkeypatch,
        lambda request: httpx.Response(
            200,
            stream=httpx.ByteStream(b"x" * (MAX_RESPONSE_BYTES + 1)),
        ),
    )
    with pytest.raises(EnrichmentError, match="size limit"):
        OpenAIProvider().generate("{}", "synthetic-key", 30)


def test_stream_deadline_is_enforced(
    guidance: Guidance,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_transport(
        monkeypatch,
        lambda request: httpx.Response(
            200,
            stream=httpx.ByteStream(envelope(guidance)),
        ),
    )
    clock = iter([0.0, 0.0, 31.0])
    with pytest.raises(EnrichmentError, match="time limit"):
        OpenAIProvider(monotonic=lambda: next(clock)).generate("{}", "synthetic-key", 30)


@pytest.mark.parametrize(
    "raw",
    [
        b"not json",
        b"[]",
        b'{"status":"incomplete"}',
        b'{"status":"completed","output":[{"type":"function_call"}]}',
        b'{"status":"completed","output":[{"type":"message","role":"assistant",'
        b'"status":"completed","content":[{"type":"refusal","refusal":"no"}]}]}',
    ],
)
def test_invalid_incomplete_and_tool_responses_fail_safely(raw: bytes) -> None:
    with pytest.raises(EnrichmentError):
        decode_response(raw)


@pytest.mark.parametrize("status", ["incomplete", "completed"])
def test_rejected_responses_retain_billable_usage(status: str) -> None:
    raw = json.dumps(
        {
            "status": status,
            "output": [],
            "incomplete_details": {"reason": "max_output_tokens"},
            "usage": {"input_tokens": 123, "output_tokens": 1500},
        }
    ).encode()
    with pytest.raises(ProviderResponseError) as raised:
        decode_response(raw)
    assert raised.value.usage is not None
    assert raised.value.usage.input_tokens == 123
    assert raised.value.usage.output_tokens == 1500
    if status == "incomplete":
        assert "output-token limit" in str(raised.value)
