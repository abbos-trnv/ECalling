from uuid import uuid4

from psycopg.types.json import Jsonb

from apps.ai_adapters.mock import MockASR, MockLLM
from apps.core.analysis import (
    Analysis,
    AnalysisCandidate,
    Scorecard,
    Transcript,
    score_results,
    validate_evidence,
)
from apps.worker import jobs


def stage(job, name):
    with jobs.connect() as connection:
        valid = connection.execute(
            "SELECT id FROM jobs WHERE id=%s AND lease_token=%s AND status='processing' "
            "AND lease_until > now() FOR UPDATE",
            (job["id"], job["lease_token"]),
        ).fetchone()
        if valid is None:
            return False
        connection.execute("UPDATE processing_runs SET stage=%s WHERE id=%s", (name, job["run_id"]))
        return True


def build_result(job):
    settings = job["provider_settings"]
    if settings.get("profile") != "mock" or settings.get("fixture_version") != "1":
        raise ValueError("Unsupported provider settings snapshot")
    scorecard = Scorecard.model_validate(settings["scorecard"])
    if not stage(job, "transcribe"):
        return None
    transcript = MockASR().transcribe(job)
    transcript = Transcript.model_validate(transcript.model_dump())
    if not stage(job, "analyze"):
        return None
    candidate = MockLLM().analyze(transcript, scorecard)
    candidate = AnalysisCandidate.model_validate(candidate.model_dump())
    if not stage(job, "validate"):
        return None
    candidate = validate_evidence(candidate, transcript, scorecard)
    score, coverage = score_results(candidate.criterion_results, scorecard)
    analysis = Analysis(
        **candidate.model_dump(),
        id=uuid4(),
        transcript_id=transcript.id,
        run_id=job["run_id"],
        scorecard_version=scorecard.version,
        llm_provider="mock",
        model_id="scripted-analysis-v1",
        prompt_version="mock-v1",
        is_mock=True,
        score=score,
        coverage=coverage,
        needs_review=any(result.status == "unknown" for result in candidate.criterion_results),
        scorecard=scorecard,
    )
    return transcript, analysis, scorecard


def publish(job, transcript, analysis, scorecard):
    if (
        transcript.run_id != job["run_id"]
        or analysis.run_id != job["run_id"]
        or analysis.transcript_id != transcript.id
    ):
        raise ValueError("Result run IDs do not match")
    with jobs.connect() as connection:
        changed = connection.execute(
            "UPDATE jobs SET status='completed',lease_token=NULL,lease_until=NULL "
            "WHERE id=%s AND lease_token=%s AND status='processing' "
            "AND lease_until > now() RETURNING id",
            (job["id"], job["lease_token"]),
        ).fetchone()
        if changed is None:
            return False
        connection.execute(
            "INSERT INTO transcripts (id,run_id,asr_provider,asr_model,is_mock,payload_jsonb) "
            "VALUES (%s,%s,%s,%s,%s,%s)",
            (
                transcript.id,
                transcript.run_id,
                transcript.asr_provider,
                transcript.model_id,
                transcript.is_mock,
                Jsonb(transcript.model_dump(mode="json")),
            ),
        )
        connection.execute(
            "INSERT INTO analysis_runs (id,run_id,transcript_id,llm_provider,llm_model,is_mock,"
            "scorecard_snapshot,payload_jsonb) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
            (
                analysis.id,
                analysis.run_id,
                transcript.id,
                analysis.llm_provider,
                analysis.model_id,
                analysis.is_mock,
                Jsonb(scorecard.model_dump(mode="json")),
                Jsonb(analysis.model_dump(mode="json")),
            ),
        )
        jobs.set_run(connection, job["run_id"], "completed", "publish")
        return True


def process_mock(job):
    result = build_result(job)
    return publish(job, *result) if result is not None else False
