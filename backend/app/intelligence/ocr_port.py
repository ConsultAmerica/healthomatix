from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class OcrPageRegion:
    page: int
    text: str
    # Bounding box in 0–1 normalized page coordinates when available
    x: float = 0.0
    y: float = 0.0
    width: float = 1.0
    height: float = 0.05


@dataclass(frozen=True)
class OcrResult:
    full_text: str
    regions: list[OcrPageRegion]


class OcrPort(Protocol):
    def extract_text(self, *, content: bytes, content_type: str) -> OcrResult: ...


class FakeOcrAdapter:
    """Deterministic OCR for tests and local development (not a production PHI processor)."""

    def extract_text(self, *, content: bytes, content_type: str) -> OcrResult:
        try:
            text = content.decode("utf-8", errors="replace")
        except Exception:
            text = "Lab Report\nGlucose 118 mg/dL (70-99)\nCollected 2026-01-15"
        if not text.strip():
            text = "Lab Report\nGlucose 118 mg/dL (70-99)\nCollected 2026-01-15"
        regions = [
            OcrPageRegion(page=1, text=line, y=0.1 * i)
            for i, line in enumerate(text.splitlines()[:20])
            if line.strip()
        ]
        return OcrResult(full_text=text, regions=regions)


def build_ocr_adapter() -> OcrPort:
    # Live Azure/AWS adapters require BAA-covered credentials; CI uses Fake.
    return FakeOcrAdapter()
