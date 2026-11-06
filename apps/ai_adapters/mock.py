from typing import Protocol
from uuid import uuid4

from apps.core.analysis import AnalysisCandidate, CriterionResult, Scorecard, Segment, Transcript


class ASRProvider(Protocol):
    def transcribe(self, asset: dict) -> Transcript: ...


class LLMProvider(Protocol):
    def analyze(self, transcript: Transcript, scorecard: Scorecard) -> AnalysisCandidate: ...


class MockASR:
    def transcribe(self, asset: dict) -> Transcript:
        texts = [
            "Здравствуйте! Это вымышленный пример разговора для тестирования интерфейса.",
            "Хочу узнать об условиях покупки.",
            "Какая задача для вас сейчас важнее всего?",
            "Мне кажется, это слишком дорого.",
            "Можем обсудить другой вариант комплектации.",
            "Давайте созвонимся завтра и уточним детали.",
        ]
        count = min(len(texts), asset["duration_ms"])
        return Transcript(
            id=uuid4(),
            call_id=asset["call_id"],
            run_id=asset["run_id"],
            audio_sha256=asset["audio_sha256"],
            duration_ms=asset["duration_ms"],
            asr_provider="mock",
            model_id="scripted-transcript-v1",
            is_mock=True,
            segments=[
                Segment(
                    segment_id=f"seg-{index + 1:04d}",
                    start_ms=index * asset["duration_ms"] // count,
                    end_ms=(index + 1) * asset["duration_ms"] // count,
                    text=texts[index],
                    speaker_role="unknown",
                )
                for index in range(count)
            ],
        )


class MockLLM:
    def analyze(self, transcript: Transcript, scorecard: Scorecard) -> AnalysisCandidate:
        ids = [segment.segment_id for segment in transcript.segments]
        evidence = {
            "greeting": 0,
            "introduction": 0,
            "needs_discovery": 2,
            "objection_handling": 4,
            "next_step": 5,
        }
        return AnalysisCandidate(
            topic_code="sales",
            outcome_code="next_step" if len(ids) == 6 else "unknown",
            summary=(
                "Вымышленный пример: обсуждение покупки, возражение о цене и следующий контакт. "
                "Это не содержание загруженной записи."
            ),
            objections=[{"code": "price", "evidence_segment_ids": [ids[3]]}]
            if len(ids) > 3
            else [],
            criterion_results=[
                CriterionResult(
                    criterion_key=criterion.key,
                    status="pass" if evidence[criterion.key] < len(ids) else "unknown",
                    evidence_segment_ids=[ids[evidence[criterion.key]]]
                    if evidence[criterion.key] < len(ids)
                    else [],
                    explanation=(
                        "Тестовая проверка вымышленного диалога; роли в записи не определены."
                    ),
                )
                for criterion in scorecard.criteria
            ],
        )
