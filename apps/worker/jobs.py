from datetime import timedelta
from uuid import uuid4

import psycopg
from psycopg.rows import dict_row

from apps.api.settings import get_settings


def connect():
    return psycopg.connect(get_settings().database_url, row_factory=dict_row, connect_timeout=3)


def set_run(connection, run_id, status, stage, failure_code=None):
    result = connection.execute(
        "UPDATE processing_runs SET status=%s, stage=COALESCE(%s,stage), failure_code=%s "
        "WHERE id=%s RETURNING call_id",
        (status, stage, failure_code, run_id),
    ).fetchone()
    connection.execute("UPDATE calls SET status=%s WHERE id=%s", (status, result["call_id"]))


def claim_job():
    with connect() as connection:
        exhausted = connection.execute(
            "UPDATE jobs SET status='failed',lease_token=NULL,lease_until=NULL "
            "WHERE status='processing' AND lease_until < now() AND attempt >= max_attempts "
            "RETURNING run_id"
        ).fetchall()
        for job in exhausted:
            set_run(connection, job["run_id"], "failed", None, "WORKER_INTERRUPTED")
        job = connection.execute(
            "SELECT * FROM jobs WHERE (status='queued' AND available_at <= now()) "
            "OR (status='processing' AND lease_until < now() AND attempt < max_attempts) "
            "ORDER BY created_at,id FOR UPDATE SKIP LOCKED LIMIT 1"
        ).fetchone()
        if job is None:
            return None
        token = uuid4()
        connection.execute(
            "UPDATE jobs SET status='processing',attempt=attempt+1,lease_token=%s,"
            "lease_until=now()+%s WHERE id=%s",
            (token, timedelta(seconds=get_settings().job_lease_seconds), job["id"]),
        )
        set_run(connection, job["run_id"], "processing", "preprocess")
        asset = connection.execute(
            "SELECT c.object_key,c.id AS call_id,c.audio_sha256,c.duration_ms,"
            "r.pipeline_profile,r.provider_settings "
            "FROM calls c JOIN processing_runs r ON r.call_id=c.id "
            "WHERE r.id=%s",
            (job["run_id"],),
        ).fetchone()
        return {**job, **asset, "lease_token": token, "attempt": job["attempt"] + 1}


def heartbeat(job):
    with connect() as connection:
        result = connection.execute(
            "UPDATE jobs SET lease_until=now()+%s WHERE id=%s AND lease_token=%s "
            "AND status='processing' AND lease_until > now()",
            (timedelta(seconds=get_settings().job_lease_seconds), job["id"], job["lease_token"]),
        )
        return result.rowcount == 1


def finish(job, failure_code=None, retry=False):
    with connect() as connection:
        can_retry = retry and job["attempt"] < job["max_attempts"]
        job_status = "queued" if can_retry else "failed" if failure_code else "completed"
        changed = connection.execute(
            "UPDATE jobs SET status=%s,lease_token=NULL,lease_until=NULL,available_at=now()+%s "
            "WHERE id=%s AND lease_token=%s AND status='processing' "
            "AND lease_until > now() RETURNING run_id",
            (
                job_status,
                timedelta(seconds=min(30, 2 ** job["attempt"])),
                job["id"],
                job["lease_token"],
            ),
        ).fetchone()
        if changed is None:
            return False
        status = "queued" if can_retry else "failed" if failure_code else "awaiting_analysis"
        set_run(
            connection,
            job["run_id"],
            status,
            None if failure_code else "transcribe",
            failure_code,
        )
        return True
