from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

Status = Literal["pass", "fail", "unknown", "not_applicable"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Segment(StrictModel):
    segment_id: str = Field(min_length=1, max_length=80)
    start_ms: int = Field(ge=0)
    end_ms: int = Field(gt=0)
    text: str = Field(min_length=1, max_length=4000)
    speaker_role: Literal["manager", "customer", "unknown"] = "unknown"


class Transcript(StrictModel):
    schema_version: str = "1"
    id: UUID
    call_id: UUID
    run_id: UUID
    audio_sha256: str
    duration_ms: int = Field(gt=0)
    asr_provider: str
    model_id: str
    is_mock: bool
    language: str = "ru"
    diarization_available: bool = False
    segments: list[Segment] = Field(min_length=1, max_length=10000)

    @model_validator(mode="after")
    def valid_segments(self):
        identifiers = [segment.segment_id for segment in self.segments]
        if len(set(identifiers)) != len(identifiers):
            raise ValueError("Duplicate segment IDs")
        previous_end = 0
        for segment in self.segments:
            if not previous_end <= segment.start_ms < segment.end_ms <= self.duration_ms:
                raise ValueError("Invalid segment timestamps")
            previous_end = segment.end_ms
            if not self.diarization_available and segment.speaker_role != "unknown":
                raise ValueError("Speaker roles require explicit diarization")
        return self


class Criterion(StrictModel):
    key: str
    title: str
    weight: int = Field(gt=0)
    requires_manager: bool = True


class Scorecard(StrictModel):
    version: str
    criteria: list[Criterion] = Field(min_length=1, max_length=50)

    @model_validator(mode="after")
    def unique_keys(self):
        keys = [criterion.key for criterion in self.criteria]
        if len(keys) != len(set(keys)):
            raise ValueError("Duplicate criteria")
        return self


class CriterionResult(StrictModel):
    criterion_key: str
    status: Status
    evidence_segment_ids: list[str] = Field(default_factory=list, max_length=50)
    explanation: str = Field(max_length=1000)
    support: Literal["supported", "insufficient_evidence"] = "supported"


class CategoryEvidence(StrictModel):
    code: Literal["price", "timing", "other"]
    evidence_segment_ids: list[str] = Field(min_length=1, max_length=50)


class AnalysisCandidate(StrictModel):
    topic_code: Literal["sales", "other"]
    outcome_code: Literal["next_step", "no_agreement", "unknown"]
    summary: str = Field(min_length=1, max_length=4000)
    objections: list[CategoryEvidence] = Field(max_length=50)
    criterion_results: list[CriterionResult] = Field(max_length=50)


class Analysis(AnalysisCandidate):
    schema_version: str = "1"
    id: UUID
    transcript_id: UUID
    run_id: UUID
    scorecard_version: str
    taxonomy_version: str = "demo-v1"
    llm_provider: str
    model_id: str
    prompt_version: str
    is_mock: bool
    score: float | None = Field(ge=0, le=100)
    coverage: float | None = Field(ge=0, le=1)
    needs_review: bool
    scorecard: Scorecard


def validate_evidence(candidate: AnalysisCandidate, transcript: Transcript, scorecard: Scorecard):
    """Validate untrusted output and normalize unsupported attribution. No IO."""
    segments = {segment.segment_id: segment for segment in transcript.segments}
    criteria = {criterion.key: criterion for criterion in scorecard.criteria}
    keys = [result.criterion_key for result in candidate.criterion_results]
    if len(keys) != len(set(keys)) or set(keys) != set(criteria):
        raise ValueError("Criteria do not match scorecard")
    for item in [*candidate.objections, *candidate.criterion_results]:
        if any(identifier not in segments for identifier in item.evidence_segment_ids):
            raise ValueError("Unknown evidence segment")
    normalized = []
    for result in candidate.criterion_results:
        criterion = criteria[result.criterion_key]
        if result.status in {"pass", "fail"} and (
            result.support != "supported"
            or not result.evidence_segment_ids
            or (
                criterion.requires_manager
                and not any(
                    segments[identifier].speaker_role == "manager"
                    for identifier in result.evidence_segment_ids
                )
            )
        ):
            result = result.model_copy(
                update={
                    "status": "unknown",
                    "support": "insufficient_evidence",
                    "evidence_segment_ids": [],
                    "explanation": "Недостаточно подтверждений или не установлена роль говорящего.",
                }
            )
        if result.status == "unknown":
            result = result.model_copy(update={"support": "insufficient_evidence"})
        normalized.append(result)
    return candidate.model_copy(update={"criterion_results": normalized})


def score_results(results: list[CriterionResult], scorecard: Scorecard):
    """unknown and N/A never count as a failed criterion."""
    weights = {criterion.key: criterion.weight for criterion in scorecard.criteria}
    keys = [result.criterion_key for result in results]
    if len(keys) != len(set(keys)) or set(keys) != set(weights):
        raise ValueError("Scorer criteria do not match scorecard")
    evaluated = sum(
        weights[result.criterion_key] for result in results if result.status in {"pass", "fail"}
    )
    earned = sum(weights[result.criterion_key] for result in results if result.status == "pass")
    applicable = sum(
        weights[result.criterion_key] for result in results if result.status != "not_applicable"
    )
    return (
        round(100 * earned / evaluated, 2) if evaluated else None,
        round(evaluated / applicable, 4) if applicable else None,
    )
