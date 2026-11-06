from uuid import uuid4

import pytest
from pydantic import ValidationError

from apps.ai_adapters.mock import MockASR, MockLLM
from apps.api.pipeline_settings import pipeline_snapshot
from apps.core.analysis import (
    AnalysisCandidate,
    Scorecard,
    Transcript,
    score_results,
    validate_evidence,
)


@pytest.fixture
def sample():
    transcript = MockASR().transcribe(
        {
            "call_id": uuid4(),
            "run_id": uuid4(),
            "duration_ms": 60000,
            "audio_sha256": "a" * 64,
        }
    )
    scorecard = Scorecard.model_validate(pipeline_snapshot("mock")["scorecard"])
    candidate = MockLLM().analyze(transcript, scorecard)
    return transcript, scorecard, candidate


def test_unknown_roles_produce_null_score_and_zero_coverage(sample):
    transcript, scorecard, candidate = sample
    validated = validate_evidence(candidate, transcript, scorecard)
    assert all(result.status == "unknown" for result in validated.criterion_results)
    assert score_results(validated.criterion_results, scorecard) == (None, 0.0)
    assert transcript.is_mock and transcript.asr_provider == "mock"


def test_score_is_deterministic_and_excludes_unknown_and_na(sample):
    _, scorecard, candidate = sample
    results = candidate.criterion_results
    results[3].status = "fail"
    assert score_results(results, scorecard) == (70.0, 1.0)
    results[3].status = "not_applicable"
    assert score_results(results, scorecard) == (100.0, 1.0)
    results[4].status = "unknown"
    assert score_results(results, scorecard) == (100.0, 0.7143)
    for result in results:
        result.status = "not_applicable"
    assert score_results(results, scorecard) == (None, None)


def test_invalid_evidence_and_incomplete_criteria_are_rejected(sample):
    transcript, scorecard, candidate = sample
    candidate.criterion_results[0].evidence_segment_ids = ["invented"]
    with pytest.raises(ValueError, match="Unknown evidence"):
        validate_evidence(candidate, transcript, scorecard)
    candidate.criterion_results.pop()
    with pytest.raises(ValueError, match="Criteria"):
        validate_evidence(candidate, transcript, scorecard)


def test_known_role_can_be_scored_but_missing_evidence_cannot(sample):
    transcript, scorecard, candidate = sample
    payload = transcript.model_dump()
    payload["diarization_available"] = True
    for segment in payload["segments"]:
        segment["speaker_role"] = "manager"
    labeled = Transcript.model_validate(payload)
    candidate.criterion_results[0].evidence_segment_ids = []
    result = validate_evidence(candidate, labeled, scorecard)
    assert result.criterion_results[0].status == "unknown"
    assert all(item.status == "pass" for item in result.criterion_results[1:])
    assert score_results(result.criterion_results, scorecard) == (100.0, 0.9)


def test_transcript_rejects_bad_times_duplicate_ids_and_unjustified_roles(sample):
    transcript, _, _ = sample
    for invalid in ("times", "duplicate", "role"):
        payload = transcript.model_dump()
        if invalid == "times":
            payload["segments"][0]["end_ms"] = transcript.duration_ms + 1
        elif invalid == "duplicate":
            payload["segments"][1]["segment_id"] = payload["segments"][0]["segment_id"]
        else:
            payload["segments"][0]["speaker_role"] = "manager"
        with pytest.raises(ValidationError):
            Transcript.model_validate(payload)


@pytest.mark.parametrize("duration", [1, 3, 50])
def test_short_audio_has_valid_nonempty_segment_intervals(duration):
    transcript = MockASR().transcribe(
        {
            "call_id": uuid4(),
            "run_id": uuid4(),
            "duration_ms": duration,
            "audio_sha256": "b" * 64,
        }
    )
    assert len(transcript.segments) <= duration
    assert transcript.segments[-1].end_ms == duration


def test_candidate_cannot_supply_score_identity_or_mock_flag(sample):
    _, _, candidate = sample
    for field, value in [("score", 100), ("run_id", str(uuid4())), ("is_mock", False)]:
        with pytest.raises(ValidationError):
            AnalysisCandidate.model_validate({**candidate.model_dump(), field: value})


def test_scorer_rejects_duplicate_or_incomplete_criteria(sample):
    _, scorecard, candidate = sample
    results = candidate.criterion_results
    with pytest.raises(ValueError):
        score_results(results[:-1], scorecard)
    with pytest.raises(ValueError):
        score_results([*results, results[0]], scorecard)
