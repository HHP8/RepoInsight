from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from repoinsight.ai.contracts import ai_report_schema, canonical_json, generate_ai_report_schema
from repoinsight.ai.models import Guidance, PromptVersion, Usage
from repoinsight.ai.payload import prepare_request
from repoinsight.ai.provider import ProviderResponseError, ProviderResult
from repoinsight.ai.service import EnrichService
from repoinsight.errors import EnrichmentError, InvalidUsageError, ReportError


class FakeProvider:
    def __init__(self, text: str, error: Exception | None = None) -> None:
        self.text = text
        self.error = error
        self.requests: list[str] = []

    def generate(self, request_json: str, api_key: str, timeout_seconds: float) -> ProviderResult:
        self.requests.append(request_json)
        if self.error is not None:
            raise self.error
        return ProviderResult(text=self.text, usage=Usage(input_tokens=100, output_tokens=50))


def test_success_preserves_static_report_and_escapes_html(
    saved_report: Path,
    guidance: Guidance,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-active-key")
    before = saved_report.read_bytes()
    guidance = guidance.model_copy(update={"summary": "<script>alert('x')</script>"})
    provider = FakeProvider(guidance.model_dump_json())
    prepared = prepare_request(saved_report, model="example-model")
    paths = EnrichService(provider=provider, now=lambda: datetime(2026, 10, 2, tzinfo=UTC)).send(
        prepared,
        model="example-model",
        output_directory=tmp_path / "ai",
        base_path=saved_report,
    )
    assert provider.requests == [prepared.request_json]
    assert saved_report.read_bytes() == before
    payload = json.loads(paths[0].read_bytes())
    assert payload["status"] == "succeeded"
    assert payload["base_report_hash"] == prepared.base_report_hash
    assert Draft202012Validator(ai_report_schema()).is_valid(payload)
    html = paths[1].read_text(encoding="utf-8")
    assert "<script>" not in html
    assert "&lt;script&gt;" in html
    assert "default-src 'none'" in html
    assert "synthetic-active-key" not in html


@pytest.mark.parametrize("credential", ["short-secret", 'quote"secret', "slash\\secret"])
def test_active_credential_redaction_handles_json_escaping(
    saved_report: Path,
    guidance: Guidance,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    credential: str,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", credential)
    provider = FakeProvider(
        guidance.model_copy(update={"summary": f"Advice {credential}"}).model_dump_json()
    )
    paths = EnrichService(provider=provider).send(
        prepare_request(saved_report, model="example-model"),
        model="example-model",
        output_directory=tmp_path / "ai",
        base_path=saved_report,
    )
    assert credential not in json.loads(paths[0].read_bytes())["guidance"]["summary"]
    assert credential not in paths[1].read_text(encoding="utf-8")


@pytest.mark.parametrize(
    "bad",
    [
        {"summary": "tests passed"},
        {"summary": "confirmed vulnerability"},
        {"summary": "Review private/module.py at line 5"},
        {"summary": "See https://example.com"},
        {"explanations": [{"evidence_id": "F999", "text": "Invented citation"}]},
        {"unexpected": "field"},
        {"actions": [{"path": "invented.py"}]},
    ],
)
def test_invalid_guidance_records_failure_and_leaves_base_report_intact(
    saved_report: Path,
    guidance: Guidance,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    bad: dict[str, object],
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-active-key")
    before = saved_report.read_bytes()
    payload = guidance.model_dump(mode="json")
    payload.update(bad)
    provider = FakeProvider(canonical_json(payload))
    with pytest.raises(EnrichmentError):
        EnrichService(provider=provider).send(
            prepare_request(saved_report, model="example-model"),
            model="example-model",
            output_directory=tmp_path / "ai",
            base_path=saved_report,
        )
    assert saved_report.read_bytes() == before
    failed = json.loads((tmp_path / "ai" / "repoinsight-ai.json").read_bytes())
    assert failed["status"] == "failed"
    assert failed["guidance"] is None
    assert failed["usage"] == {"input_tokens": 100, "output_tokens": 50}
    assert Draft202012Validator(ai_report_schema()).is_valid(failed)


@pytest.mark.parametrize(
    "error",
    [
        EnrichmentError("Provider leaked synthetic-active-key"),
        RuntimeError("Provider leaked synthetic-active-key"),
    ],
)
def test_provider_errors_do_not_expose_active_credentials(
    saved_report: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    error: Exception,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-active-key")
    with pytest.raises(EnrichmentError) as raised:
        EnrichService(provider=FakeProvider("", error)).send(
            prepare_request(saved_report, model="example-model"),
            model="example-model",
            output_directory=tmp_path / "ai",
            base_path=saved_report,
        )
    assert "synthetic-active-key" not in str(raised.value)
    assert "synthetic-active-key" not in (tmp_path / "ai" / "repoinsight-ai.json").read_text()


def test_missing_key_and_model_mismatch_do_not_call_provider(
    saved_report: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = FakeProvider("unused")
    prepared = prepare_request(saved_report, model="example-model")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(InvalidUsageError, match="OPENAI_API_KEY"):
        EnrichService(provider=provider).send(
            prepared,
            model="example-model",
            output_directory=tmp_path / "ai",
            base_path=saved_report,
        )
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-active-key")
    with pytest.raises(InvalidUsageError, match="must match"):
        EnrichService(provider=provider).send(
            prepared,
            model="different-model",
            output_directory=tmp_path / "ai",
            base_path=saved_report,
        )
    assert not provider.requests


def test_output_cannot_replace_base_input_or_existing_alias(
    saved_report: Path,
    guidance: Guidance,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-active-key")
    renamed = saved_report.with_name("repoinsight-ai.json")
    saved_report.rename(renamed)
    before = renamed.read_bytes()
    provider = FakeProvider(guidance.model_dump_json())
    with pytest.raises(ReportError, match="base report"):
        EnrichService(provider=provider).send(
            prepare_request(renamed, model="example-model"),
            model="example-model",
            output_directory=renamed.parent,
            base_path=renamed,
        )
    assert renamed.read_bytes() == before
    assert not provider.requests


def test_invalid_output_directory_fails_before_provider_call(
    saved_report: Path,
    guidance: Guidance,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-active-key")
    invalid = tmp_path / "not-a-directory"
    invalid.write_text("preserve me", encoding="utf-8")
    provider = FakeProvider(guidance.model_dump_json())
    with pytest.raises(ReportError):
        EnrichService(provider=provider).send(
            prepare_request(saved_report, model="example-model"),
            model="example-model",
            output_directory=invalid,
            base_path=saved_report,
        )
    assert not provider.requests
    assert invalid.read_text() == "preserve me"


def test_guidance_resolves_finding_locations_locally(
    saved_report: Path,
    guidance: Guidance,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-active-key")
    prepared = prepare_request(saved_report, model="example-model")
    reference = next(ref for ref in prepared.evidence if ref.location is not None)
    action = guidance.actions[0].model_copy(update={"evidence_ids": (reference.id,)})
    guidance = guidance.model_copy(update={"actions": (action,)})
    paths = EnrichService(provider=FakeProvider(guidance.model_dump_json())).send(
        prepared,
        model="example-model",
        output_directory=tmp_path / "ai",
        base_path=saved_report,
    )
    assert reference.location is not None
    assert f"{reference.location.path}:{reference.location.start_line}" in paths[1].read_text()
    assert reference.location.path not in prepared.request_json


def test_checked_ai_schema_is_synchronized_and_rejects_unknown_fields() -> None:
    assert ai_report_schema() == generate_ai_report_schema()
    assert ai_report_schema()["additionalProperties"] is False


def test_incomplete_provider_failure_preserves_usage_in_sidecar(
    saved_report: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-active-key")
    provider = FakeProvider(
        "",
        ProviderResponseError("Output limit reached", Usage(input_tokens=123, output_tokens=1500)),
    )
    before = saved_report.read_bytes()
    with pytest.raises(EnrichmentError):
        EnrichService(provider=provider).send(
            prepare_request(saved_report, model="example-model"),
            model="example-model",
            output_directory=tmp_path / "ai",
            base_path=saved_report,
        )
    failed = json.loads((tmp_path / "ai/repoinsight-ai.json").read_bytes())
    assert failed["usage"] == {"input_tokens": 123, "output_tokens": 1500}
    assert failed["status"] == "failed"
    assert saved_report.read_bytes() == before


@pytest.mark.parametrize("separator", [" ", "\n", "\u00a0"])
def test_compact_word_limit_counts_all_narrative_fields_at_boundary(
    saved_report: Path, guidance: Guidance, separator: str
) -> None:
    from repoinsight.ai.service import validate_guidance

    rest = [
        *guidance.limitations,
        *(item.text for item in guidance.explanations),
        *(
            text
            for item in guidance.actions
            for text in (item.title, item.rationale, item.suggested_change, item.verification)
        ),
    ]
    summary_words = 180 - sum(len(text.split()) for text in rest)
    prepared = prepare_request(saved_report, model="example-model")
    boundary = guidance.model_copy(update={"summary": separator.join(["Review"] * summary_words)})
    result = ProviderResult(text=boundary.model_dump_json(), usage=None)
    assert validate_guidance(result, prepared, "synthetic-key") == boundary
    excessive = boundary.model_copy(update={"summary": boundary.summary + separator + "carefully"})
    with pytest.raises(EnrichmentError, match="180-word"):
        validate_guidance(
            ProviderResult(text=excessive.model_dump_json(), usage=None), prepared, "synthetic-key"
        )


@pytest.mark.parametrize("field", ["explanations", "actions", "limitations"])
def test_compact_section_limits_leave_older_prompt_contracts_replayable(
    saved_report: Path, guidance: Guidance, field: str
) -> None:
    from repoinsight.ai.service import validate_guidance

    excessive = guidance.model_copy(update={field: getattr(guidance, field) * 3})
    result = ProviderResult(text=excessive.model_dump_json(), usage=None)
    prepared = prepare_request(saved_report, model="example-model")
    with pytest.raises(EnrichmentError, match="section limits"):
        validate_guidance(result, prepared, "synthetic-key")
    legacy = replace(prepared, prompt_version="1.2")
    assert validate_guidance(result, legacy, "synthetic-key") == excessive


@pytest.mark.parametrize("version", ["1.0", "1.1", "1.2"])
def test_compact_word_limit_does_not_rewrite_historical_response_contract(
    saved_report: Path, guidance: Guidance, version: PromptVersion
) -> None:
    from repoinsight.ai.service import validate_guidance

    old_guidance = guidance.model_copy(update={"summary": "Review " * 181})
    prepared = replace(prepare_request(saved_report, model="example-model"), prompt_version=version)
    assert (
        validate_guidance(
            ProviderResult(text=old_guidance.model_dump_json(), usage=None),
            prepared,
            "synthetic-key",
        )
        == old_guidance
    )


def test_overlong_answer_records_failure_usage_without_another_paid_attempt(
    saved_report: Path, guidance: Guidance, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-active-key")
    provider = FakeProvider(
        guidance.model_copy(update={"summary": "Review " * 181}).model_dump_json()
    )
    prepared = prepare_request(saved_report, model="example-model")
    before = saved_report.read_bytes()
    with pytest.raises(EnrichmentError, match="180-word"):
        EnrichService(provider=provider).send(
            prepared,
            model="example-model",
            output_directory=tmp_path / "ai",
            base_path=saved_report,
        )
    failed = json.loads((tmp_path / "ai/repoinsight-ai.json").read_bytes())
    assert failed["status"] == "failed" and failed["guidance"] is None
    assert failed["usage"] == {"input_tokens": 100, "output_tokens": 50}
    assert provider.requests == [prepared.request_json]
    assert saved_report.read_bytes() == before


@pytest.mark.parametrize(
    "summary",
    [
        "Consider issue/pull-request templates.",
        "Consider issue/PR guidance.",
        "The test/source ratio is a static proxy.",
        "Static evidence only; no source/runtime verification, "
        "so matches are not confirmed defects.",
        "No source/runtime.",
        "No SOURCE/RUNTIME verification.",
    ],
)
def test_slash_separated_documentation_terms_are_not_file_citations(
    saved_report: Path,
    guidance: Guidance,
    summary: str,
) -> None:
    from repoinsight.ai.service import validate_guidance

    result = ProviderResult(
        text=guidance.model_copy(update={"summary": summary}).model_dump_json(), usage=None
    )
    assert (
        validate_guidance(
            result, prepare_request(saved_report, model="example-model"), "synthetic-key"
        ).summary
        == summary
    )


@pytest.mark.parametrize(
    "summary",
    [
        "Review issue/private.py.",
        "Review issue/PR/config.",
        "Review test/source.py.",
        "Review source/runtime.py.",
        "Review source/runtime.bak.",
        "Review source/runtime/config.",
        r"Review source/runtime\config.",
        "Review source/runtime-extra.",
        "Review source/runtime2.",
        "Review /source/runtime.",
        "Review ./source/runtime.",
        "Review ../source/runtime.",
        "Review other/source/runtime.",
        r"Review C:\source/runtime.",
        "Review C:source/runtime.",
        "Review /test/source.",
        "Review issue/PR-extra.",
    ],
)
def test_similar_actual_paths_remain_rejected(
    saved_report: Path,
    guidance: Guidance,
    summary: str,
) -> None:
    from repoinsight.ai.service import validate_guidance

    result = ProviderResult(
        text=guidance.model_copy(update={"summary": summary}).model_dump_json(), usage=None
    )
    with pytest.raises(EnrichmentError, match="unsupported"):
        validate_guidance(
            result, prepare_request(saved_report, model="example-model"), "synthetic-key"
        )


@pytest.mark.parametrize(
    "summary",
    [
        "The heuristic match is not a confirmed vulnerability.",
        "Findings are not confirmed defects, vulnerabilities, or verified fixes.",
        "Findings are not confirmed defects, runtime results, or verified fixes.",
        "This is not measured runtime coverage.",
        "Review configuration; do not treat this as measured coverage.",
        "Do not treat these as verified fixes.",
        "Do not treat it as a confirmed vulnerability.",
        "Do not interpret them as measured runtime coverage.",
        "Don't regard this as measured coverage.",
        "Don\u2019t treat it as a verified fix.",
        "DO NOT TREAT THIS AS MEASURED COVERAGE.",
        "Do not treat this as confirmed defects, vulnerabilities, or verified fixes.",
        "The match does not establish untrusted input or a confirmed vulnerability.",
        "This does not establish a confirmed vulnerability.",
        "Static evidence cannot demonstrate a confirmed vulnerability.",
        "Evidence does not prove verified fixes.",
        "Static evidence did not establish measured runtime coverage.",
        "The finding can't establish untrusted inputs or confirmed vulnerabilities.",
        "This can\u2019t establish a confirmed vulnerability.",
        "This could not establish a verified fix.",
    ],
)
def test_explicit_negative_verification_claims_are_accepted(
    saved_report: Path,
    guidance: Guidance,
    summary: str,
) -> None:
    from repoinsight.ai.service import validate_guidance

    result = ProviderResult(
        text=guidance.model_copy(update={"summary": summary}).model_dump_json(),
        usage=None,
    )
    assert (
        validate_guidance(
            result,
            prepare_request(saved_report, model="example-model"),
            "synthetic-key",
        ).summary
        == summary
    )


@pytest.mark.parametrize(
    "summary",
    [
        "This is a confirmed vulnerability.",
        "These are verified fixes.",
        "This is measured runtime coverage.",
        "Not a confirmed vulnerability, but tests passed.",
        "Not confirmed defects, vulnerabilities, or verified fixes; tests passed.",
        "Not confirmed defects, runtime results, or verified fixes; tests passed.",
        "Not a confirmed vulnerability. These are verified fixes.",
        "Not only a confirmed vulnerability, but a verified fix.",
        "Do not treat this as measured coverage, but tests passed.",
        "Do not treat this as measured coverage. These are verified fixes.",
        "Do not treat this as measured coverage; we have confirmed vulnerabilities.",
        "Don't regard it as a verified fix, but this is measured runtime coverage.",
        "Do not treat only this as measured coverage.",
        "Do not treat this only as measured coverage.",
        "Do not treat this as only measured coverage.",
        "Do not treat this as measured coverage, but it is measured coverage.",
        "I do not agree; treat this as measured coverage.",
        "Do not treat this as speculation: these are verified fixes.",
        "The match does not establish untrusted input or a confirmed vulnerability; tests passed.",
        "This does not establish a confirmed vulnerability, but these are verified fixes.",
        "This cannot demonstrate a confirmed vulnerability; this is measured runtime coverage.",
        "The match does not establish only untrusted input or a confirmed vulnerability.",
        "The match does not establish untrusted input, but a confirmed vulnerability exists.",
        "The match does not establish untrusted input and a confirmed vulnerability.",
        "No evidence; this establishes a confirmed vulnerability.",
        "This cannot demonstrate only a confirmed vulnerability.",
        "This does not always establish a confirmed vulnerability.",
        "This cannot establish untrusted input or only a confirmed vulnerability.",
        "This cannot establish context; confirmed vulnerabilities were found.",
    ],
)
def test_positive_claims_are_rejected_even_after_a_disclaimer(
    saved_report: Path,
    guidance: Guidance,
    summary: str,
) -> None:
    from repoinsight.ai.service import validate_guidance

    result = ProviderResult(
        text=guidance.model_copy(update={"summary": summary}).model_dump_json(),
        usage=None,
    )
    with pytest.raises(EnrichmentError, match="verification claims"):
        validate_guidance(
            result,
            prepare_request(saved_report, model="example-model"),
            "synthetic-key",
        )


def test_negative_interpretation_caveat_in_action_verification_is_accepted(
    saved_report: Path,
    guidance: Guidance,
) -> None:
    from repoinsight.ai.service import validate_guidance

    verification = (
        "Review configuration and workflow references; do not treat this as measured coverage."
    )
    action = guidance.actions[0].model_copy(update={"verification": verification})
    updated = guidance.model_copy(update={"actions": (action,)})
    result = ProviderResult(text=updated.model_dump_json(), usage=None)
    validated = validate_guidance(
        result, prepare_request(saved_report, model="example-model"), "synthetic-key"
    )
    assert validated.actions[0].verification == verification


@pytest.mark.parametrize(
    "prefix",
    [
        "Not",
        "Do not treat this as",
        "Don't regard it as",
        "This does not establish",
        "This cannot establish untrusted input or",
    ],
)
def test_negative_caveat_cannot_exempt_a_claim_in_another_field(
    saved_report: Path,
    guidance: Guidance,
    prefix: str,
) -> None:
    from repoinsight.ai.service import validate_guidance

    updated = guidance.model_copy(
        update={"summary": prefix, "limitations": ("measured runtime coverage.",)}
    )
    result = ProviderResult(text=updated.model_dump_json(), usage=None)
    with pytest.raises(EnrichmentError, match="verification claims"):
        validate_guidance(
            result, prepare_request(saved_report, model="example-model"), "synthetic-key"
        )


def test_negative_evidence_predicate_in_explanation_is_accepted(
    saved_report: Path,
    guidance: Guidance,
) -> None:
    from repoinsight.ai.service import validate_guidance

    text = "The match does not establish untrusted input or a confirmed vulnerability."
    explanation = guidance.explanations[0].model_copy(update={"text": text})
    updated = guidance.model_copy(update={"explanations": (explanation,)})
    result = ProviderResult(text=updated.model_dump_json(), usage=None)
    validated = validate_guidance(
        result, prepare_request(saved_report, model="example-model"), "synthetic-key"
    )
    assert validated.explanations[0].text == text


def test_saved_prompt_provenance_survives_offline_replay(
    saved_report: Path,
    guidance: Guidance,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-active-key")
    prepared = replace(prepare_request(saved_report, model="example-model"), prompt_version="1.0")
    paths = EnrichService(provider=FakeProvider(guidance.model_dump_json())).send(
        prepared,
        model="example-model",
        output_directory=tmp_path / "replay",
        base_path=saved_report,
    )
    assert json.loads(paths[0].read_bytes())["prompt_version"] == "1.0"
