import json
import math
import subprocess
from dataclasses import dataclass
from pathlib import Path

from apps.api.settings import get_settings


class MediaError(Exception):
    def __init__(self, code: str, message: str, status: int = 422):
        self.code, self.message, self.status = code, message, status


@dataclass(frozen=True)
class AudioInfo:
    format: str
    duration_ms: int


def probe(path: Path) -> AudioInfo:
    settings = get_settings()
    try:
        result = subprocess.run(
            [
                settings.ffprobe_command,
                "-v",
                "error",
                "-protocol_whitelist",
                "file,pipe",
                "-show_entries",
                "format=format_name,duration:stream=codec_type",
                "-of",
                "json",
                str(path),
            ],
            capture_output=True,
            timeout=min(settings.media_timeout_seconds, 15),
            check=True,
        )
        payload = json.loads(result.stdout)
        streams = payload.get("streams", [])
        if not any(item.get("codec_type") == "audio" for item in streams) or any(
            item.get("codec_type") == "video" for item in streams
        ):
            raise MediaError("UNSUPPORTED_AUDIO", "Нужен аудиофайл без видеодорожки", 415)
        containers = set(payload["format"]["format_name"].split(","))
        if "wav" in containers:
            extension = "wav"
        elif "mp3" in containers:
            extension = "mp3"
        elif containers & {"mov", "mp4", "m4a"}:
            extension = "m4a"
        else:
            raise MediaError("UNSUPPORTED_AUDIO", "Поддерживаются WAV, MP3 и M4A", 415)
        duration = float(payload["format"]["duration"])
        if not math.isfinite(duration) or duration <= 0:
            raise ValueError("Invalid duration")
        if duration > settings.max_duration_seconds:
            raise MediaError(
                "AUDIO_TOO_LONG",
                f"Запись должна быть не длиннее {settings.max_duration_seconds} секунд",
            )
        return AudioInfo(extension, max(1, round(duration * 1000)))
    except FileNotFoundError as error:
        raise MediaError(
            "VALIDATOR_UNAVAILABLE", "Проверка аудио временно недоступна", 503
        ) from error
    except (subprocess.SubprocessError, ValueError, KeyError, TypeError) as error:
        raise MediaError("INVALID_AUDIO", "Не удалось прочитать аудиозапись") from error


def validate_decode(path: Path) -> None:
    settings = get_settings()
    try:
        subprocess.run(
            [
                settings.ffmpeg_command,
                "-nostdin",
                "-v",
                "error",
                "-xerror",
                "-protocol_whitelist",
                "file,pipe",
                "-i",
                str(path),
                "-map",
                "0:a:0",
                "-f",
                "null",
                "-",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=settings.media_timeout_seconds,
            check=True,
        )
    except FileNotFoundError as error:
        raise MediaError("VALIDATOR_UNAVAILABLE", "Проверка аудио недоступна", 503) from error
    except subprocess.SubprocessError as error:
        raise MediaError(
            "DECODE_FAILED", "Аудиозапись повреждена или проверка превысила лимит времени"
        ) from error
