"""Credential boundary and response validation around optional enrichment."""

from __future__ import annotations

import json
import os
import re
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from jsonschema import Draft202012Validator
from pydantic import ValidationError

from ..errors import EnrichmentError, InvalidUsageError
from ..redaction import REDACTION_MARKER, redact_text, safe_exception_message
from .contracts import MAX_GUIDANCE_ITEMS, MAX_GUIDANCE_WORDS, canonical_json, guidance_schema
from .models import AIReport, Guidance
from .payload import PreparedRequest
from .provider import (
    MAX_RESPONSE_BYTES,
    OpenAIProvider,
    Provider,
    ProviderResponseError,
    ProviderResult,
)
from .reporting import prepare_output_directory, write_ai_reports

_CITATION = re.compile(
    r"https?://|(?:[A-Za-z]:[\\/]|(?:\.{1,2}|[A-Za-z0-9_-]+)[/\\])[\w.-]+|"
    r"\b[\w.-]+\.(?:py|md|toml|yaml|yml|json|js|ts|txt)\b|\bline(?:s)?\s+\d+",
    re.IGNORECASE,
)
_CLAIM = re.compile(
    r"\b(?:tests? (?:passed|pass)|confirmed vulnerabilit(?:y|ies)|"
    r"verified fix(?:es)?|measured (?:runtime )?coverage)\b",
    re.IGNORECASE,
)
# Exempt only complete prose terms, never components of longer filesystem paths.
# A sentence-ending period is allowed; a filename extension is not.
_PROSE_TERMS = re.compile(
    r"(?<![\w./\\:-])(?:issue/(?:pull-request|PR)|test/source|source/runtime)"
    r"(?![\w/\\-]|\.[\w./\\-])",
    re.IGNORECASE,
)
_NEGATED_CLAIM = re.compile(
    r"\b(?:not\s+|(?:do\s+not|don['\u2019]t)\s+(?:treat|interpret|regard)\s+"
    r"(?:this|these|it|them)\s+as\s+|"
    r"(?:(?:do|does|did|could)\s+not|cannot|can['\u2019]t)\s+"
    r"(?:establish|demonstrate|prove)\s+(?:untrusted\s+inputs?\s+or\s+)?)"
    r"(?:a\s+)?"
    r"(?:confirmed (?:defects?|vulnerabilit(?:y|ies))|"
    r"verified fix(?:es)?|measured (?:runtime )?coverage)"
    r"(?:\s*(?:,\s*(?:(?:and|or)\s+)?|\s+(?:and|or)\s+)"
    r"(?:confirmed (?:defects?|vulnerabilit(?:y|ies))|defects?|vulnerabilit(?:y|ies)|"
    r"runtime results|verified fix(?:es)?|measured (?:runtime )?coverage))*\b",
    re.IGNORECASE,
)
LIMITATIONS = (
    "AI guidance is variable and unverified; a developer must review suggested changes.",
    "Only saved static evidence was used. Current source and runtime behavior were not checked.",
    "Redaction is heuristic and cannot guarantee removal of all confidential information.",
    "Token estimates are conservative, not exact prices. Retries may incur additional charges.",
)


def _scrub(text: str, api_key: str) -> str:
    return redact_text(text.replace(api_key, REDACTION_MARKER))


def _scrub_json(text: str, api_key: str) -> str:
    def scrub(value: object) -> object:
        if isinstance(value, str):
            return _scrub(value, api_key)
        if isinstance(value, dict):
            return {key: scrub(item) for key, item in value.items()}
        if isinstance(value, list):
            return [scrub(item) for item in value]
        return value

    return canonical_json(scrub(json.loads(text)))


def validate_guidance(result: ProviderResult, prepared: PreparedRequest, api_key: str) -> Guidance:
    if len(result.text.encode("utf-8")) > MAX_RESPONSE_BYTES:
        raise EnrichmentError("Guidance exceeded its size limit")
    try:
        safe_json = _scrub_json(result.text, api_key)
        if not Draft202012Validator(guidance_schema()).is_valid(json.loads(safe_json)):
            raise EnrichmentError("Provider guidance did not satisfy the required schema")
        guidance = Guidance.model_validate_json(safe_json, strict=False)
    except (ValueError, RecursionError, ValidationError):
        raise EnrichmentError("Provider guidance did not satisfy the required schema") from None
    known = {item.id for item in prepared.evidence}
    cited = {item.evidence_id for item in guidance.explanations}
    cited.update(ref for action in guidance.actions for ref in action.evidence_ids)
    if not cited <= known:
        raise EnrichmentError("Provider guidance cited unknown evidence")
    # Do not permit model prose to bypass the structured reference boundary.
    narrative_parts = [
        guidance.summary,
        *guidance.limitations,
        *(item.text for item in guidance.explanations),
        *(
            text
            for item in guidance.actions
            for text in (item.title, item.rationale, item.suggested_change, item.verification)
        ),
    ]
    narrative = " ".join(narrative_parts)
    # Apply new compactness rules only to their recorded prompt version. Older
    # saved responses remain replayable under the contract they were generated with.
    if prepared.prompt_version == "1.3":
        if any(
            len(items) > MAX_GUIDANCE_ITEMS
            for items in (guidance.explanations, guidance.actions, guidance.limitations)
        ):
            raise EnrichmentError("Provider guidance exceeded compact section limits")
        if len(narrative.split()) > MAX_GUIDANCE_WORDS:
            raise EnrichmentError("Provider guidance exceeded the 180-word narrative limit")
    # These fixed documentation terms use a slash without identifying a location.
    citation_text = _PROSE_TERMS.sub(lambda match: match.group().replace("/", " and "), narrative)
    if _CITATION.search(citation_text):
        raise EnrichmentError("Provider guidance used unsupported file, line, or URL citations")
    # Exempt explicit negative noun phrases, bounded interpretation instructions
    # and negative evidence predicates. Positive clauses remain visible; negation
    # cannot span fields or skip arbitrary text to reach a claim.
    if any(
        _CLAIM.search(_NEGATED_CLAIM.sub("unverified evidence", text)) for text in narrative_parts
    ):
        raise EnrichmentError("Provider guidance made unsupported verification claims")
    return guidance


class EnrichService:
    def __init__(
        self,
        *,
        provider: Provider | None = None,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._provider = provider or OpenAIProvider()
        self._now = now

    def send(
        self,
        prepared: PreparedRequest,
        *,
        model: str,
        output_directory: Path,
        base_path: Path,
        timeout_seconds: float = 30,
    ) -> tuple[Path, ...]:
        api_key = os.environ.get("OPENAI_API_KEY", "")
        if not api_key.strip() or any(ord(char) < 33 or ord(char) > 126 for char in api_key):
            raise InvalidUsageError("Set a valid OPENAI_API_KEY in the process environment")
        if api_key in prepared.request_json:
            raise InvalidUsageError("The active credential must not appear in the request payload")
        if json.loads(prepared.request_json)["model"] != model:
            raise InvalidUsageError("Prepared payload and selected model must match")
        if not 0 < timeout_seconds <= 120:
            raise InvalidUsageError("AI timeout must be between 0 and 120 seconds")
        prepare_output_directory(output_directory, base_path)
        usage = None
        guidance = None
        failure: EnrichmentError | None = None
        try:
            result = self._provider.generate(prepared.request_json, api_key, timeout_seconds)
            usage = result.usage
            guidance = validate_guidance(result, prepared, api_key)
        except InvalidUsageError:
            raise
        except EnrichmentError as error:
            if isinstance(error, ProviderResponseError):
                usage = error.usage
            # Use controlled diagnostics even if an injected provider includes a raw credential.
            failure = EnrichmentError(_scrub(safe_exception_message(error), api_key)[:500])
        except Exception:
            failure = EnrichmentError("AI provider failed to produce safe guidance")
        report = AIReport(
            schema_version="1.0",
            status="failed" if failure else "succeeded",
            provider="openai",
            model=model,
            prompt_version=prepared.prompt_version,
            payload_hash=prepared.payload_hash,
            base_report_hash=prepared.base_report_hash,
            base_revision=prepared.report.source.revision,
            base_generated_at=prepared.report.run.generated_at,
            generated_at=self._now(),
            estimated_input_tokens=prepared.estimated_input_tokens,
            omitted_findings=prepared.omitted_findings,
            omitted_metrics=prepared.omitted_metrics,
            usage=usage,
            evidence=prepared.evidence,
            limitations=LIMITATIONS,
            guidance=guidance,
            error=str(failure) if failure else None,
        )
        # Remove exact active-key values from local references/revision as well as provider prose.
        try:
            report = AIReport.model_validate_json(
                _scrub_json(report.model_dump_json(), api_key), strict=False
            )
        except ValidationError:
            raise EnrichmentError("AI report could not be safely redacted") from None
        paths = write_ai_reports(report, output_directory, base_path)
        if failure is not None:
            raise failure
        return paths
