"""A single fixed HTTPS endpoint, bounded transport, and no automatic SDK retries."""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from pydantic import ValidationError

from ..errors import EnrichmentError, InvalidUsageError
from .models import Usage

ENDPOINT = "https://api.openai.com/v1/responses"
MAX_RESPONSE_BYTES = 65536


@dataclass(frozen=True)
class ProviderResult:
    text: str
    usage: Usage | None


class ProviderResponseError(EnrichmentError):
    """A rejected response can still contain billable provider usage."""

    def __init__(self, message: str, usage: Usage | None) -> None:
        super().__init__(message)
        self.usage = usage


class Provider(Protocol):
    def generate(self, request_json: str, api_key: str, timeout_seconds: float) -> ProviderResult:
        """Generate advisory data, without exposing a credential in diagnostics."""


def decode_response(raw: bytes) -> ProviderResult:
    usage = None
    try:
        value = json.loads(raw)
        if isinstance(value, dict) and isinstance(value.get("usage"), dict):
            raw_usage = value["usage"]
            usage = Usage.model_validate(
                {
                    "input_tokens": raw_usage.get("input_tokens"),
                    "output_tokens": raw_usage.get("output_tokens"),
                }
            )
        if not isinstance(value, dict) or value.get("status") != "completed":
            if isinstance(value, dict) and value.get("incomplete_details") == {
                "reason": "max_output_tokens"
            }:
                raise EnrichmentError("Provider response exhausted the output-token limit")
            raise EnrichmentError("Provider response was incomplete or refused")
        output = value.get("output")
        if not isinstance(output, list):
            raise EnrichmentError("Provider response has no valid guidance")
        texts: list[str] = []
        for item in output:
            if not isinstance(item, dict):
                raise EnrichmentError("Provider returned invalid output")
            if item.get("type") == "reasoning":
                continue
            if item.get("type") != "message" or item.get("role") != "assistant":
                raise EnrichmentError("Provider returned unsupported output")
            if item.get("status") != "completed" or not isinstance(item.get("content"), list):
                raise EnrichmentError("Provider response was incomplete or refused")
            for content in item["content"]:
                if not isinstance(content, dict) or content.get("type") != "output_text":
                    raise EnrichmentError("Provider response was incomplete or refused")
                text = content.get("text")
                if not isinstance(text, str):
                    raise EnrichmentError("Provider returned invalid guidance")
                texts.append(text)
        if len(texts) != 1:
            raise EnrichmentError("Provider must return one structured guidance document")
        return ProviderResult(text=texts[0], usage=usage)
    except EnrichmentError as error:
        raise ProviderResponseError(str(error), usage) from None
    except (ValueError, TypeError, RecursionError, ValidationError):
        raise ProviderResponseError("Provider returned an invalid response", usage) from None


class OpenAIProvider:
    def __init__(
        self,
        *,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self._monotonic = monotonic

    def generate(self, request_json: str, api_key: str, timeout_seconds: float) -> ProviderResult:
        try:
            import httpx
        except ImportError:
            raise InvalidUsageError("Send mode requires: pip install 'repoinsight[ai]'") from None

        deadline = self._monotonic() + timeout_seconds
        with httpx.Client(verify=True, follow_redirects=False, trust_env=False) as client:
            for attempt in range(2):
                remaining = deadline - self._monotonic()
                if remaining <= 0:
                    raise EnrichmentError("AI request exceeded its time limit")
                try:
                    with client.stream(
                        "POST",
                        ENDPOINT,
                        headers={
                            "Authorization": f"Bearer {api_key}",
                            "Content-Type": "application/json",
                            "Accept-Encoding": "identity",
                        },
                        content=request_json.encode("utf-8"),
                        timeout=remaining,
                    ) as response:
                        status = response.status_code
                        if status in {401, 403}:
                            raise EnrichmentError("Provider rejected the credential or access")
                        if status == 429 or 500 <= status <= 599:
                            if attempt == 0:
                                continue
                            raise EnrichmentError("Provider is unavailable or rate limited")
                        if status != 200:
                            raise EnrichmentError(
                                "Provider rejected the request; check model/options"
                            )
                        if response.headers.get("content-encoding", "identity") != "identity":
                            raise EnrichmentError("Provider returned unsupported response encoding")
                        raw = bytearray()
                        for chunk in response.iter_raw(chunk_size=4096):
                            raw.extend(chunk)
                            if len(raw) > MAX_RESPONSE_BYTES:
                                raise EnrichmentError("Provider response exceeded its size limit")
                            if self._monotonic() >= deadline:
                                raise EnrichmentError("AI request exceeded its time limit")
                        return decode_response(bytes(raw))
                except httpx.HTTPError:
                    if attempt == 1:
                        raise EnrichmentError("Unable to complete the HTTPS request") from None
        raise EnrichmentError("Unable to complete the AI request")
