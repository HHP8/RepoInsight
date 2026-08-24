from __future__ import annotations

import importlib

import pytest

AWS_TEST_KEY = "AKIA" + "ABCDEFGHIJKLMNOP"


@pytest.mark.parametrize(
    ("raw", "secret"),
    [
        ("api_key=super-secret-value", "super-secret-value"),
        ("Authorization: Bearer ghp_" + "abcdefghijklmnopqrstuvwxyz0123456789", "ghp_"),
        ("token: sk-" + "proj-abcdefghijklmnopqrstuvwxyz", "sk-proj-"),
        (f"AWS_ACCESS_KEY_ID={AWS_TEST_KEY}", AWS_TEST_KEY),
        (
            "-----BEGIN " + "PRIVATE KEY-----\nprivate-material\n-----END PRIVATE KEY-----",
            "private-material",
        ),
    ],
)
def test_redact_text_removes_suspected_secret_values(raw: str, secret: str) -> None:
    redaction = importlib.import_module("repoinsight.redaction")

    redacted = redaction.redact_text(raw)

    assert secret not in redacted
    assert "[REDACTED]" in redacted


def test_safe_exception_message_never_exposes_secret() -> None:
    redaction = importlib.import_module("repoinsight.redaction")
    error = RuntimeError("request failed with password=hunter2-secret")

    message = redaction.safe_exception_message(error)

    assert "hunter2-secret" not in message
    assert "[REDACTED]" in message


@pytest.mark.parametrize("quote", ['"', "'"])
def test_quoted_named_secret_is_redacted_in_full_at_model_boundary(quote: str) -> None:
    models = importlib.import_module("repoinsight.models")
    raw = f"password={quote}alpha beta{quote}"

    warning = models.WarningRecord(code="probe", message=raw)

    assert warning.message == f"password={quote}[REDACTED]{quote}"
    assert "alpha" not in warning.message
    assert "beta" not in warning.message


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (
            'password="alpha\\" beta, gamma; C:\\\\temp"',
            'password="[REDACTED]"',
        ),
        (
            "token='alpha\\' beta, gamma; C:\\\\temp'",
            "token='[REDACTED]'",
        ),
        (
            'password="alpha\\" beta, gamma; C:\\\\temp',
            'password="[REDACTED]',
        ),
        (
            "token='alpha\\' beta, gamma; C:\\\\temp",
            "token='[REDACTED]",
        ),
    ],
)
def test_escaped_or_unterminated_quoted_secret_never_leaks_tail(raw: str, expected: str) -> None:
    models = importlib.import_module("repoinsight.models")

    warning = models.WarningRecord(code="probe", message=raw)

    assert warning.message == expected
    for leaked_fragment in ("alpha", "beta", "gamma", "temp"):
        assert leaked_fragment not in warning.message


def test_safe_exception_message_survives_broken_exception_stringification() -> None:
    redaction = importlib.import_module("repoinsight.redaction")

    class BrokenError(Exception):
        def __str__(self) -> str:
            raise RuntimeError("password=secondary-secret")

    assert redaction.safe_exception_message(BrokenError()) == "BrokenError"
