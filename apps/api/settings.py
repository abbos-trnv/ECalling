from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql://voice:voice_local_demo@127.0.0.1:15432/voice_analytics"
    profile: Literal["mock", "preprocess"] = "mock"
    audio_root: Path = Path("data/audio")
    max_upload_bytes: int = Field(default=50 * 1024 * 1024, ge=1)
    max_duration_seconds: int = Field(default=1800, ge=1)
    ffprobe_command: str = "ffprobe"
    ffmpeg_command: str = "ffmpeg"
    media_timeout_seconds: int = Field(default=120, ge=1)
    job_lease_seconds: int = Field(default=60, ge=5)
    worker_poll_seconds: float = Field(default=2, gt=0)


@lru_cache
def get_settings() -> Settings:
    return Settings()
