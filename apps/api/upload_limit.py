from fastapi import HTTPException
from starlette.responses import JSONResponse

from apps.api.settings import get_settings


class UploadSizeLimit:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if (
            scope["type"] != "http"
            or scope["method"] != "POST"
            or not scope["path"].endswith("/calls")
        ):
            return await self.app(scope, receive, send)
        limit = get_settings().max_upload_bytes + 64 * 1024
        headers = dict(scope.get("headers", []))
        try:
            declared = int(headers.get(b"content-length", b"0"))
        except ValueError:
            declared = 0
        if declared > limit:
            return await JSONResponse(
                status_code=413, content={"detail": "Файл превышает допустимый размер"}
            )(scope, receive, send)
        received = 0

        async def bounded_receive():
            nonlocal received
            message = await receive()
            received += len(message.get("body", b""))
            if received > limit:
                raise HTTPException(413, "Файл превышает допустимый размер")
            return message

        await self.app(scope, bounded_receive, send)
