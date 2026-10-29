from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from app.intelligence.lab_parser import parse_lab_ocr_text
from app.intelligence.ocr_port import OcrResult


@dataclass(frozen=True)
class ExtractedField:
    name: str
    value: str
    unit: str
    reference_range: str
    effective_date: str
    confidence: float
    source_region: dict[str, Any]
    extras: dict[str, Any] | None = None

    def as_dict(self) -> dict[str, Any]:
        payload = {
            "name": self.name,
            "value": self.value,
            "unit": self.unit,
            "reference_range": self.reference_range,
            "effective_date": self.effective_date,
            "confidence": self.confidence,
            "source_region": self.source_region,
        }
        if self.extras:
            payload.update(self.extras)
        return payload


class ExtractionLlmPort(Protocol):
    def extract_fields(self, *, ocr: OcrResult) -> list[ExtractedField]: ...


class FakeExtractionAdapter:
    """Heuristic / deterministic lab extraction for tests — not production clinical AI."""

    def extract_fields(self, *, ocr: OcrResult) -> list[ExtractedField]:
        regions = [
            {
                "page": region.page,
                "text": region.text,
                "x": region.x,
                "y": region.y,
                "width": region.width,
                "height": region.height,
            }
            for region in (ocr.regions or [])
        ]
        parsed = parse_lab_ocr_text(ocr.full_text, page=1, regions=regions)
        fields: list[ExtractedField] = []
        for item in parsed:
            data = item.as_field_dict()
            fields.append(
                ExtractedField(
                    name=data["name"],
                    value=data["value"],
                    unit=data["unit"],
                    reference_range=data["reference_range"],
                    effective_date=data["effective_date"],
                    confidence=data["confidence"],
                    source_region=data["source_region"],
                    extras={
                        k: v
                        for k, v in data.items()
                        if k
                        not in {
                            "name",
                            "value",
                            "unit",
                            "reference_range",
                            "effective_date",
                            "confidence",
                            "source_region",
                        }
                    },
                )
            )
        if not fields:
            fields.append(
                ExtractedField(
                    name="Unparsed finding",
                    value="",
                    unit="",
                    reference_range="",
                    effective_date="",
                    confidence=0.2,
                    source_region={"page": 1, "text": ocr.full_text[:200]},
                    extras={
                        "require_review": True,
                        "verification_status": "pending",
                        "confidence_metadata": {"parser": "lab_parser_v1", "empty": True},
                    },
                )
            )
        return fields


def build_extraction_adapter() -> ExtractionLlmPort:
    return FakeExtractionAdapter()
