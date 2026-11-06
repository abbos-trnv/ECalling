import io
import os
import shutil
import subprocess
import sys
import wave
from uuid import uuid4

import pytest
from psycopg.conninfo import make_conninfo

from apps.api.settings import get_settings
from apps.worker import jobs
from apps.worker.__main__ import run_once

pytestmark = pytest.mark.integration


def wav(seconds=1, value=0):
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(16000)
        audio.writeframes(value.to_bytes(2, "little", signed=True) * 16000 * seconds)
    return buffer.getvalue()


@pytest.fixture
def setup(client, database, monkeypatch, tmp_path):
    if not shutil.which("ffprobe") or not shutil.which("ffmpeg"):
        pytest.skip("Install ffmpeg or run media tests inside the API Docker image")
    monkeypatch.setattr(get_settings(), "audio_root", tmp_path)
    monkeypatch.setattr(get_settings(), "profile", "preprocess")
    monkeypatch.setattr(jobs, "connect", database[0])
    company = client.post("/api/v1/companies", json={"name": "Аудио-тест"}).json()["id"]
    return client, company, tmp_path


def upload(setup, content=None, key="sample", employee=None, filename="test.wav"):
    client, company, _ = setup
    return client.post(
        f"/api/v1/companies/{company}/calls",
        files={"file": (filename, wav() if content is None else content, "audio/wav")},
        data={"employee_id": employee} if employee else {},
        headers={"Idempotency-Key": key},
    )


def test_upload_idempotency_and_company_scope(setup):
    client, company, root = setup
    response = upload(setup, filename="../../renamed.exe")
    assert response.status_code == 202, response.text
    identifier = response.json()["call_id"]
    assert upload(setup).json()["call_id"] == identifier
    assert upload(setup, wav(value=1)).status_code == 409
    assert len(list(root.rglob("original.wav"))) == 1
    assert not list(root.rglob("*.tmp"))
    path = f"/api/v1/companies/{company}/calls/{identifier}"
    detail = client.get(path).json()
    assert detail["audio_format"] == "wav"
    assert detail["filename_safe"] == "renamed.exe"
    assert detail["status"] == "queued"
    assert "object_key" not in detail
    assert client.get(path + "/audio").content == wav()
    partial = client.get(path + "/audio", headers={"Range": "bytes=0-9"})
    assert partial.status_code == 206
    assert partial.content == wav()[:10]
    other = client.post("/api/v1/companies", json={"name": "Другая"}).json()["id"]
    assert client.get(f"/api/v1/companies/{other}/calls/{identifier}").status_code == 404
    assert client.get(f"/api/v1/companies/{other}/calls/{identifier}/audio").status_code == 404
    assert client.get(f"/api/v1/companies/{other}/calls").json() == []


def test_bad_files_limits_and_foreign_employee(setup, monkeypatch):
    client, company, root = setup
    assert upload(setup, b"not audio").status_code == 422
    assert upload(setup, b"").status_code == 422
    monkeypatch.setattr(get_settings(), "max_duration_seconds", 1)
    assert upload(setup, wav(seconds=2)).status_code == 422
    monkeypatch.setattr(get_settings(), "max_upload_bytes", 100)
    assert upload(setup).status_code == 413
    other = client.post("/api/v1/companies", json={"name": "Другая"}).json()["id"]
    employee = client.post(
        f"/api/v1/companies/{other}/employees", json={"display_name": "Чужой"}
    ).json()["id"]
    assert upload(setup, employee=employee).status_code == 404
    assert client.get(f"/api/v1/companies/{company}/calls").json() == []
    assert not list(root.rglob("original.*"))
    assert not list(root.rglob("*.tmp"))
    response = client.post(
        f"/api/v1/companies/{company}/calls",
        content=iter([b"x" * 70000]),
        headers={"Content-Type": "multipart/form-data; boundary=x"},
    )
    assert response.status_code == 413


@pytest.mark.parametrize("extension", ["mp3", "m4a", "ogg"])
def test_formats_detected_by_content(setup, extension):
    _, _, root = setup
    source = root / "source.wav"
    source.write_bytes(wav())
    target = root / f"converted.{extension}"
    subprocess.run(["ffmpeg", "-v", "error", "-i", str(source), str(target)], check=True)
    response = upload(setup, target.read_bytes(), filename="wrong.wav")
    assert response.status_code == (415 if extension == "ogg" else 202), response.text


def test_worker_and_expired_lease_fencing(setup, database):
    client, company, _ = setup
    identifier = upload(setup).json()["call_id"]
    first = jobs.claim_job()
    assert first is not None
    assert jobs.claim_job() is None
    with database[0]() as connection:
        connection.execute("UPDATE jobs SET lease_until=now()-interval '1 second'")
    replacement = jobs.claim_job()
    assert replacement["attempt"] == 2
    assert not jobs.finish(first)
    assert jobs.finish(replacement)
    result = client.get(f"/api/v1/companies/{company}/calls/{identifier}").json()
    assert result["status"] == "awaiting_analysis"
    assert result["stage"] == "transcribe"
    assert not jobs.finish(replacement)


def test_worker_kill_then_recovery(setup, database):
    client, company, root = setup
    identifier = upload(setup).json()["call_id"]
    with database[0]() as connection:
        schema = connection.execute("SELECT current_schema() AS name").fetchone()["name"]
        dsn = make_conninfo(os.environ["TEST_DATABASE_URL"], options=f"-csearch_path={schema}")
    environment = {**os.environ, "DATABASE_URL": dsn, "AUDIO_ROOT": str(root)}
    process = subprocess.Popen(
        [
            sys.executable,
            "-u",
            "-c",
            "from apps.worker.jobs import claim_job; import time; "
            "assert claim_job(); print('claimed', flush=True); time.sleep(60)",
        ],
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        assert process.stdout.readline().strip() == "claimed", process.stderr.read()
        process.kill()
        process.wait(timeout=10)
        with database[0]() as connection:
            connection.execute("UPDATE jobs SET lease_until=now()-interval '1 second'")
        assert run_once()
        result = client.get(f"/api/v1/companies/{company}/calls/{identifier}").json()
        assert result["status"] == "awaiting_analysis"
        assert result["attempt"] == 2
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=10)


def test_attempt_limit_and_decode_failure(setup, database):
    client, company, root = setup
    identifier = upload(setup).json()["call_id"]
    job = jobs.claim_job()
    with database[0]() as connection:
        connection.execute(
            "UPDATE jobs SET attempt=max_attempts,lease_until=now()-interval '1 second'"
        )
    assert jobs.claim_job() is None
    assert not jobs.finish(job)
    assert (
        client.get(f"/api/v1/companies/{company}/calls/{identifier}").json()["failure_code"]
        == "WORKER_INTERRUPTED"
    )
    identifier = upload(setup, key=str(uuid4())).json()["call_id"]
    for path in root.rglob("original.wav"):
        path.write_bytes(b"broken")
    assert run_once()
    assert (
        client.get(f"/api/v1/companies/{company}/calls/{identifier}").json()["failure_code"]
        == "DECODE_FAILED"
    )


def test_mock_results_and_company_scoping(setup, monkeypatch):
    client, company, _ = setup
    monkeypatch.setattr(get_settings(), "profile", "mock")
    identifier = upload(setup).json()["call_id"]
    path = f"/api/v1/companies/{company}/calls/{identifier}"
    assert client.get(path + "/transcript").status_code == 409
    assert client.get(path + "/analysis").status_code == 409
    assert run_once()
    detail = client.get(path).json()
    assert detail["status"] == "completed"
    assert detail["is_mock"] is True
    transcript = client.get(path + "/transcript").json()
    analysis = client.get(path + "/analysis").json()
    assert transcript["asr_provider"] == analysis["llm_provider"] == "mock"
    assert analysis["transcript_id"] == transcript["id"]
    assert analysis["score"] is None and analysis["coverage"] == 0
    assert analysis["needs_review"] is True
    ids = {segment["segment_id"] for segment in transcript["segments"]}
    assert all(
        identifier in ids
        for item in analysis["objections"]
        for identifier in item["evidence_segment_ids"]
    )
    other = client.post("/api/v1/companies", json={"name": "Другая"}).json()["id"]
    assert client.get(f"/api/v1/companies/{other}/calls/{identifier}/analysis").status_code == 404


def test_retry_preserves_versions_and_does_not_duplicate_lists(setup, database):
    import psycopg

    client, company, _ = setup
    identifier = upload(setup).json()["call_id"]
    path = f"/api/v1/companies/{company}/calls/{identifier}"
    assert run_once()  # preprocess-only run
    first = client.post(path + "/retry").json()["run_id"]
    assert client.post(path + "/retry").json()["run_id"] == first
    assert run_once()
    original = client.get(path + "/analysis").json()
    second = client.post(path + "/retry").json()["run_id"]
    assert second != first
    assert client.get(path + "/analysis").status_code == 409
    assert client.get(path + f"/analysis?run_id={first}").json() == original
    assert run_once()
    assert len(client.get(f"/api/v1/companies/{company}/calls").json()) == 1
    assert len(client.get(path + "/runs").json()) == 3
    assert client.get(path + f"/analysis?run_id={first}").json() == original
    with database[0]() as connection:
        with pytest.raises(psycopg.errors.CheckViolation), connection.transaction():
            connection.execute("UPDATE analysis_runs SET payload_jsonb='{}'::jsonb")


def test_invalid_analysis_is_not_published(setup, monkeypatch, database):
    from apps.ai_adapters.mock import MockLLM

    client, company, _ = setup
    monkeypatch.setattr(get_settings(), "profile", "mock")
    original = MockLLM.analyze

    def invalid(self, transcript, scorecard):
        candidate = original(self, transcript, scorecard)
        candidate.criterion_results[0].evidence_segment_ids = ["does-not-exist"]
        return candidate

    monkeypatch.setattr(MockLLM, "analyze", invalid)
    identifier = upload(setup).json()["call_id"]
    assert run_once()
    result = client.get(f"/api/v1/companies/{company}/calls/{identifier}").json()
    assert result["status"] == "failed" and result["failure_code"] == "INVALID_ANALYSIS"
    assert result["stage"] == "validate"
    with database[0]() as connection:
        assert connection.execute("SELECT count(*) AS n FROM transcripts").fetchone()["n"] == 0
        assert connection.execute("SELECT count(*) AS n FROM analysis_runs").fetchone()["n"] == 0


def test_stale_mock_worker_cannot_publish(setup, monkeypatch, database):
    from apps.worker.pipeline import build_result, publish

    monkeypatch.setattr(get_settings(), "profile", "mock")
    assert upload(setup).status_code == 202
    old = jobs.claim_job()
    result = build_result(old)
    with database[0]() as connection:
        connection.execute("UPDATE jobs SET lease_until=now()-interval '1 second'")
    current = jobs.claim_job()
    assert not publish(old, *result)
    replacement = build_result(current)
    assert publish(current, *replacement)
    assert not publish(current, *replacement)
    with database[0]() as connection:
        assert connection.execute("SELECT count(*) AS n FROM transcripts").fetchone()["n"] == 1
        assert connection.execute("SELECT count(*) AS n FROM analysis_runs").fetchone()["n"] == 1
