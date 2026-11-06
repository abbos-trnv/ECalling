import logging

import psycopg
from fastapi import FastAPI
from fastapi.responses import JSONResponse

from apps.api.calls import router as calls_router
from apps.api.organizations import router as organizations_router
from apps.api.settings import get_settings
from apps.api.upload_limit import UploadSizeLimit

logger = logging.getLogger(__name__)
app = FastAPI(title="Voice Analytics — local demo", version="0.1.0")
app.include_router(organizations_router)
app.include_router(calls_router)
app.add_middleware(UploadSizeLimit)


@app.exception_handler(psycopg.OperationalError)
async def database_unavailable(request, error):
    logger.warning("Database operation unavailable")
    return JSONResponse(status_code=503, content={"detail": "База временно недоступна"})


def check_database() -> None:
    with psycopg.connect(get_settings().database_url, connect_timeout=3) as connection:
        connection.execute("SELECT 1")


@app.get("/health/live")
def live() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/ready")
def ready() -> JSONResponse:
    try:
        check_database()
    except psycopg.Error:
        # Do not expose the DSN, credentials or database exception to the browser/logs.
        logger.warning("Database readiness check failed")
        return JSONResponse(status_code=503, content={"status": "unavailable", "db": "error"})
    return JSONResponse(content={"status": "ready", "db": "ok"})


@app.get("/api/v1/system")
def system() -> dict[str, str | bool]:
    return {
        "name": "Voice Analytics",
        "mode": "local_demo",
        "profile": get_settings().profile,
        "pipeline_available": True,
        "real_inference_available": False,
    }
