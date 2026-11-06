import logging
import signal
import threading

import psycopg

from apps.api.media import MediaError, validate_decode
from apps.api.settings import get_settings
from apps.api.storage import LocalStorage
from apps.worker.jobs import claim_job, finish, heartbeat
from apps.worker.pipeline import process_mock

logger = logging.getLogger(__name__)


def run_once():
    job = claim_job()
    if job is None:
        return False
    stopped = threading.Event()

    def maintain_lease():
        while not stopped.wait(get_settings().job_lease_seconds / 3):
            try:
                if not heartbeat(job):
                    return
            except psycopg.Error:
                logger.warning("Worker heartbeat unavailable")

    thread = threading.Thread(target=maintain_lease, daemon=True)
    thread.start()
    try:
        path = LocalStorage(get_settings().audio_root).path(job["object_key"])
        validate_decode(path)
        if job["pipeline_profile"] == "mock":
            process_mock(job)
        else:
            finish(job)
    except MediaError as error:
        finish(job, error.code, retry=error.status == 503)
    except OSError:
        finish(job, "STORAGE_UNAVAILABLE", retry=True)
    except ValueError:
        finish(job, "INVALID_ANALYSIS")
    finally:
        stopped.set()
        thread.join(timeout=5)
    return True


def main():
    logging.basicConfig(level=logging.INFO)
    stopping = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stopping.set())
    signal.signal(signal.SIGINT, lambda *_: stopping.set())
    while not stopping.is_set():
        try:
            processed = run_once()
        except psycopg.Error:
            logger.warning("Worker database unavailable; will reconnect")
            processed = False
        if not processed:
            stopping.wait(get_settings().worker_poll_seconds)


if __name__ == "__main__":
    main()
