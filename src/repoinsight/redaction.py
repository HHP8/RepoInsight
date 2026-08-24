"""Conservative redaction helpers for all diagnostic and model boundaries."""

from __future__ import annotations

import re
from collections.abc import Mapping
from enum import Enum
from typing import TypeAlias

REDACTION_MARKER = "[REDACTED]"

_PRIVATE_KEY = re.compile(
    r"-----BEGIN(?: [A-Z0-9]+)? PRIVATE KEY-----.*?"
    r"-----END(?: [A-Z0-9]+)? PRIVATE KEY-----",
    re.DOTALL,
)
_HIGH_SPECIFICITY_TOKEN = re.compile(
    r"(?<![A-Za-z0-9])(?:gh[pousr]_[A-Za-z0-9]{20,}|sk-(?:proj-)?[A-Za-z0-9_-]{16,}|"
    r"AKIA[A-Z0-9]{16})(?![A-Za-z0-9])"
)
_BEARER = re.compile(r"(?i)(\bBearer\s+)[^\s,;]+")
_NAMED_SECRET = re.compile(
    r"(\b(?:api[_-]?key|access[_-]?key(?:_id)?|secret(?:[_-]?key)?|"
    r"password|passwd|token|authorization)\b\s*[:=]\s*)"
    r"(\"(?:\\(?:[^\r\n]|$)|[^\"\\\r\n])*(?:\"|$)|"
    r"'(?:\\(?:[^\r\n]|$)|[^'\\\r\n])*(?:'|$)|[^\s,;\"'}]+)",
    re.IGNORECASE | re.MULTILINE,
)

Redactable: TypeAlias = object


def redact_text(value: str) -> str:
    """Replace high-specificity secret material while preserving useful context."""
    value = _PRIVATE_KEY.sub(REDACTION_MARKER, value)
    value = _HIGH_SPECIFICITY_TOKEN.sub(REDACTION_MARKER, value)
    value = _BEARER.sub(rf"\1{REDACTION_MARKER}", value)

    def replace_named_secret(match: re.Match[str]) -> str:
        secret = match.group(2)
        quote = secret[0] if secret.startswith(('"', "'")) else ""
        preceding_backslashes = 0
        ends_with_quote = bool(quote and secret.endswith(quote))
        if ends_with_quote:
            for character in reversed(secret[:-1]):
                if character != "\\":
                    break
                preceding_backslashes += 1
        is_closed = bool(ends_with_quote and len(secret) > 1 and preceding_backslashes % 2 == 0)
        closing_quote = quote if is_closed else ""
        return f"{match.group(1)}{quote}{REDACTION_MARKER}{closing_quote}"

    return _NAMED_SECRET.sub(replace_named_secret, value)


def redact_data(value: Redactable) -> Redactable:
    """Recursively redact strings before typed model construction."""
    if isinstance(value, Enum):
        return value
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, Mapping):
        return {key: redact_data(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return tuple(redact_data(item) for item in value)
    if isinstance(value, list):
        return [redact_data(item) for item in value]
    return value


def safe_exception_message(error: BaseException) -> str:
    """Return a redacted exception message without trusting ``__str__``."""
    try:
        message = str(error)
    except BaseException:
        return type(error).__name__
    return redact_text(message) if message else type(error).__name__
