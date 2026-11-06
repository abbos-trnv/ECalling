from pathlib import Path

from apps.api.settings import get_settings
from apps.core.analysis import Scorecard


def pipeline_snapshot(profile=None):
    profile = profile or get_settings().profile
    if profile == "preprocess":
        return {"profile": "preprocess"}
    if profile != "mock":
        raise ValueError("Unsupported pipeline profile")
    scorecard = Scorecard.model_validate_json(
        (Path(__file__).parent / "config" / "scorecard-demo-v1.json").read_text(encoding="utf-8")
    )
    return {
        "profile": "mock",
        "asr_provider": "mock",
        "llm_provider": "mock",
        "fixture_version": "1",
        "scorecard": scorecard.model_dump(mode="json"),
    }
