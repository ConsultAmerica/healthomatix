"""Speech-to-text port. Fake adapter for CI/demos; production requires BAA STT."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class TranscriptChunk:
    speaker_label: str
    start_offset_ms: int
    end_offset_ms: int
    text: str
    confidence: float


class SpeechPort(Protocol):
    def transcribe_synthetic(
        self,
        *,
        session_id: str,
        clinician_notes: str,
    ) -> list[TranscriptChunk]: ...


class FakeSpeechAdapter:
    """Deterministic synthetic transcript — no real audio capture or network."""

    provider = "fake"

    def transcribe_synthetic(
        self,
        *,
        session_id: str,
        clinician_notes: str,
    ) -> list[TranscriptChunk]:
        base = clinician_notes.strip() or "Patient describes fatigue. Clinician documents exam findings."
        return [
            TranscriptChunk(
                speaker_label="patient",
                start_offset_ms=0,
                end_offset_ms=4000,
                text="I've been feeling more tired than usual this week.",
                confidence=0.92,
            ),
            TranscriptChunk(
                speaker_label="clinician",
                start_offset_ms=4200,
                end_offset_ms=9000,
                text=f"Thank you. Based on today's visit notes: {base[:180]}",
                confidence=0.9,
            ),
        ]


def build_speech_adapter() -> SpeechPort:
    return FakeSpeechAdapter()
