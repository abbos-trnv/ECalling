import hashlib
import logging
import re
from datetime import datetime
from typing import Annotated
from uuid import UUID, uuid4

import psycopg
from fastapi import APIRouter, File, Form, Header, HTTPException, Query, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse
from psycopg.types.json import Jsonb
from pydantic import BaseModel

from apps.api.media import MediaError, probe
from apps.api.organizations import Connection, require_company
from apps.api.pipeline_settings import pipeline_snapshot
from apps.api.settings import get_settings
from apps.api.storage import LocalStorage
from apps.core.analysis import Analysis, Transcript

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/companies/{company_id}/calls", tags=["calls"])


class Call(BaseModel):
    id: UUID
    company_id: UUID
    employee_id: UUID | None
    filename_safe: str
    size_bytes: int
    duration_ms: int
    audio_format: str
    status: str
    created_at: datetime
    run_id: UUID
    stage: str
    failure_code: str | None
    attempt: int
    pipeline_profile: str
    is_mock: bool
    score: float | None
    coverage: float | None


SELECT_CALL = """
SELECT c.*, r.id AS run_id, r.stage, r.failure_code, j.attempt,r.pipeline_profile,
(r.pipeline_profile='mock') AS is_mock,
(a.payload_jsonb->>'score')::float AS score,(a.payload_jsonb->>'coverage')::float AS coverage
FROM calls c JOIN LATERAL (
    SELECT * FROM processing_runs WHERE call_id=c.id ORDER BY created_at DESC,id DESC LIMIT 1
) r ON true
JOIN jobs j ON j.run_id = r.id
LEFT JOIN analysis_runs a ON a.run_id=r.id
"""


def find_call(connection, company_id, call_id):
    result = connection.execute(
        SELECT_CALL
        + " WHERE c.company_id = %s AND c.id = %s ORDER BY r.created_at DESC, r.id DESC LIMIT 1",
        (company_id, call_id),
    ).fetchone()
    if result is None:
        raise HTTPException(404, "Звонок не найден")
    return result


@router.post("", status_code=202)
async def upload_call(
    company_id: UUID,
    connection: Connection,
    file: Annotated[UploadFile, File()],
    employee_id: Annotated[UUID | None, Form()] = None,
    idempotency_key: Annotated[str | None, Header(min_length=1, max_length=128)] = None,
):
    require_company(connection, company_id)
    if (
        employee_id is not None
        and not connection.execute(
            "SELECT id FROM employees WHERE id = %s AND company_id = %s", (employee_id, company_id)
        ).fetchone()
    ):
        raise HTTPException(404, "Сотрудник не найден в выбранной компании")
    connection.commit()
    settings = get_settings()
    try:
        storage = LocalStorage(settings.audio_root)
        temporary = storage.temporary()
    except OSError as error:
        raise HTTPException(503, "Хранилище аудио временно недоступно") from error
    object_key = None
    keep_file = False
    try:
        digest = hashlib.sha256()
        size = 0
        with temporary.open("wb") as output:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > settings.max_upload_bytes:
                    raise HTTPException(413, "Файл превышает допустимый размер")
                digest.update(chunk)
                output.write(chunk)
        info = await run_in_threadpool(probe, temporary)
        call_id, run_id, job_id = uuid4(), uuid4(), uuid4()
        object_key = f"{company_id}/{call_id}/original.{info.format}"
        storage.publish(temporary, object_key)
        filename = (
            re.sub(
                r"[\x00-\x1f\x7f]", "", (file.filename or "audio").replace("\\", "/").split("/")[-1]
            )[:200]
            or "audio"
        )
        inserted = connection.execute(
            "INSERT INTO calls (id, company_id, employee_id, filename_safe, object_key, "
            "audio_sha256, "
            "size_bytes, duration_ms, audio_format, status, idempotency_key) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,'queued',%s) "
            "ON CONFLICT (company_id, idempotency_key) DO NOTHING RETURNING id",
            (
                call_id,
                company_id,
                employee_id,
                filename,
                object_key,
                digest.hexdigest(),
                size,
                info.duration_ms,
                info.format,
                idempotency_key,
            ),
        ).fetchone()
        if inserted is None:
            existing = connection.execute(
                "SELECT * FROM calls WHERE company_id = %s AND idempotency_key = %s",
                (company_id, idempotency_key),
            ).fetchone()
            if (
                existing["audio_sha256"] != digest.hexdigest()
                or existing["employee_id"] != employee_id
            ):
                raise HTTPException(
                    409, "Этот ключ загрузки уже использован для другой записи или сотрудника"
                )
            current = find_call(connection, company_id, existing["id"])
            connection.commit()
            return {
                "call_id": current["id"],
                "run_id": current["run_id"],
                "status": current["status"],
            }
        connection.execute(
            "INSERT INTO processing_runs "
            "(id,call_id,stage,status,pipeline_profile,provider_settings) "
            "VALUES (%s,%s,'preprocess','queued',%s,%s)",
            (run_id, call_id, settings.profile, Jsonb(pipeline_snapshot())),
        )
        connection.execute(
            "INSERT INTO jobs (id,run_id,status) VALUES (%s,%s,'queued')", (job_id, run_id)
        )
        connection.commit()
        keep_file = True
        return {"call_id": call_id, "run_id": run_id, "status": "queued"}
    except MediaError as error:
        raise HTTPException(error.status, error.message) from error
    except psycopg.errors.ForeignKeyViolation as error:
        raise HTTPException(
            409, "Компания или сотрудник были удалены; обновите страницу"
        ) from error
    except OSError as error:
        raise HTTPException(503, "Не удалось сохранить аудио") from error
    finally:
        await file.close()
        try:
            temporary.unlink(missing_ok=True)
            if object_key and not keep_file:
                storage.delete(object_key)
        except OSError:
            logger.error("Audio cleanup failed; inspect local storage for orphan files")


@router.get("", response_model=list[Call])
def list_calls(
    company_id: UUID,
    connection: Connection,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
    employee_id: UUID | None = None,
):
    require_company(connection, company_id)
    return connection.execute(
        SELECT_CALL + " WHERE c.company_id = %s AND (%s::uuid IS NULL OR c.employee_id = %s) "
        "ORDER BY c.created_at DESC, c.id DESC LIMIT %s OFFSET %s",
        (company_id, employee_id, employee_id, limit, offset),
    ).fetchall()


@router.get("/{call_id}", response_model=Call)
def call_detail(company_id: UUID, call_id: UUID, connection: Connection):
    return find_call(connection, company_id, call_id)


@router.get("/{call_id}/audio")
def audio(company_id: UUID, call_id: UUID, connection: Connection):
    item = find_call(connection, company_id, call_id)
    path = LocalStorage(get_settings().audio_root).path(item["object_key"])
    if not path.is_file():
        raise HTTPException(404, "Аудиофайл не найден")
    mime = {"wav": "audio/wav", "mp3": "audio/mpeg", "m4a": "audio/mp4"}[item["audio_format"]]
    return FileResponse(path, media_type=mime, headers={"X-Content-Type-Options": "nosniff"})


@router.post("/{call_id}/retry", status_code=202)
def retry_mock(company_id: UUID, call_id: UUID, connection: Connection):
    call = connection.execute(
        "SELECT id FROM calls WHERE id=%s AND company_id=%s FOR UPDATE", (call_id, company_id)
    ).fetchone()
    if call is None:
        raise HTTPException(404, "Звонок не найден")
    current = find_call(connection, company_id, call_id)
    if current["status"] in {"queued", "processing"}:
        return {"call_id": call_id, "run_id": current["run_id"], "status": current["status"]}
    run_id = uuid4()
    connection.execute(
        "INSERT INTO processing_runs (id,call_id,stage,status,pipeline_profile,provider_settings) "
        "VALUES (%s,%s,'preprocess','queued','mock',%s)",
        (run_id, call_id, Jsonb(pipeline_snapshot("mock"))),
    )
    connection.execute(
        "INSERT INTO jobs (id,run_id,status) VALUES (%s,%s,'queued')", (uuid4(), run_id)
    )
    connection.execute("UPDATE calls SET status='queued' WHERE id=%s", (call_id,))
    return {"call_id": call_id, "run_id": run_id, "status": "queued"}


def result_payload(connection, company_id, call_id, run_id, kind):
    current = find_call(connection, company_id, call_id)
    selected = run_id or current["run_id"]
    # kind is an internal constant, never user-provided SQL.
    table = "transcripts" if kind == "transcript" else "analysis_runs"
    row = connection.execute(
        f"SELECT p.payload_jsonb FROM {table} p JOIN processing_runs r ON r.id=p.run_id "
        "WHERE r.id=%s AND r.call_id=%s",
        (selected, call_id),
    ).fetchone()
    if row is None:
        exists = connection.execute(
            "SELECT id FROM processing_runs WHERE id=%s AND call_id=%s", (selected, call_id)
        ).fetchone()
        raise HTTPException(
            409 if exists else 404, "Результат ещё не готов" if exists else "Запуск не найден"
        )
    return row["payload_jsonb"]


@router.get("/{call_id}/transcript", response_model=Transcript)
def transcript(company_id: UUID, call_id: UUID, connection: Connection, run_id: UUID | None = None):
    return result_payload(connection, company_id, call_id, run_id, "transcript")


@router.get("/{call_id}/analysis", response_model=Analysis)
def analysis(company_id: UUID, call_id: UUID, connection: Connection, run_id: UUID | None = None):
    return result_payload(connection, company_id, call_id, run_id, "analysis")


@router.get("/{call_id}/runs")
def runs(company_id: UUID, call_id: UUID, connection: Connection):
    find_call(connection, company_id, call_id)
    return connection.execute(
        "SELECT id,status,stage,pipeline_profile,created_at FROM processing_runs "
        "WHERE call_id=%s ORDER BY created_at DESC,id DESC LIMIT 50",
        (call_id,),
    ).fetchall()
