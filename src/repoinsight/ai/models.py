"""Independent contracts for advisory output; static report models stay unchanged."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import Field, StrictBool, StrictInt, StrictStr, model_validator

from ..models import Location, StrictModel

EvidenceID = Annotated[StrictStr, Field(pattern=r"^[FCM][0-9]{3}$")]
Text = Annotated[StrictStr, Field(min_length=1, max_length=2000)]
ShortText = Annotated[StrictStr, Field(min_length=1, max_length=500)]
Digest = Annotated[StrictStr, Field(pattern=r"^[a-f0-9]{64}$")]
PromptVersion = Literal["1.0", "1.1", "1.2", "1.3"]


class Explanation(StrictModel):
    evidence_id: EvidenceID
    text: Text


class Action(StrictModel):
    title: ShortText
    priority: StrictInt = Field(ge=1, le=5)
    effort: Literal["small", "medium", "large"]
    hypothesis: StrictBool
    rationale: Text
    suggested_change: Text
    verification: Text
    evidence_ids: tuple[EvidenceID, ...] = Field(min_length=1, max_length=10)


class Guidance(StrictModel):
    summary: Text
    explanations: tuple[Explanation, ...] = Field(max_length=20)
    actions: tuple[Action, ...] = Field(max_length=5)
    limitations: tuple[ShortText, ...] = Field(min_length=1, max_length=10)


class EvidenceReference(StrictModel):
    id: EvidenceID
    label: ShortText
    location: Location | None


class Usage(StrictModel):
    input_tokens: StrictInt = Field(ge=0)
    output_tokens: StrictInt = Field(ge=0)


class AIReport(StrictModel):
    schema_version: Literal["1.0"]
    status: Literal["succeeded", "failed"]
    provider: Literal["openai"]
    model: StrictStr = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$")
    prompt_version: PromptVersion
    payload_hash: Digest
    base_report_hash: Digest
    base_revision: StrictStr | None
    base_generated_at: datetime
    generated_at: datetime
    estimated_input_tokens: StrictInt = Field(ge=0)
    omitted_findings: StrictInt = Field(ge=0)
    omitted_metrics: StrictInt = Field(ge=0)
    usage: Usage | None
    evidence: tuple[EvidenceReference, ...]
    limitations: tuple[ShortText, ...]
    guidance: Guidance | None
    error: ShortText | None

    @model_validator(mode="after")
    def validate_status_and_references(self) -> AIReport:
        if any(
            value.tzinfo is None or value.utcoffset() is None
            for value in (self.base_generated_at, self.generated_at)
        ):
            raise ValueError("AI timestamps must include a timezone")
        if self.status == "succeeded" and (self.guidance is None or self.error is not None):
            raise ValueError("successful AI reports require guidance and no error")
        if self.status == "failed" and (self.guidance is not None or self.error is None):
            raise ValueError("failed AI reports require an error and no guidance")
        identifiers = {item.id for item in self.evidence}
        if len(identifiers) != len(self.evidence):
            raise ValueError("duplicate evidence identifiers")
        if self.guidance is not None:
            cited = {item.evidence_id for item in self.guidance.explanations}
            cited.update(ref for action in self.guidance.actions for ref in action.evidence_ids)
            if not cited <= identifiers:
                raise ValueError("guidance cites unknown evidence")
        return self
