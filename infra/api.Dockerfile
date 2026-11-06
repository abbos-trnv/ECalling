FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.13.7 /uv /usr/local/bin/uv
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && rm -rf /var/lib/apt/lists/*
COPY pyproject.toml uv.lock ./
ENV UV_HTTP_TIMEOUT=120 UV_HTTP_RETRIES=10 UV_CONCURRENT_DOWNLOADS=2 UV_LINK_MODE=copy
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen
COPY apps ./apps
COPY tests ./tests
COPY alembic.ini ./
ENV PATH="/app/.venv/bin:$PATH"
CMD ["uvicorn", "apps.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
