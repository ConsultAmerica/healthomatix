"""Deterministic laboratory row parsing for synthetic/demo OCR text.

Preserves raw evidence separately from normalized fields. Ambiguous layouts
are returned with low confidence and require_review=True rather than invented.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


_FLAG_MAP = {
    "H": "high",
    "L": "low",
    "HH": "critical_high",
    "LL": "critical_low",
    "C": "critical",
    "A": "abnormal",
    "N": "normal",
    "HIGH": "high",
    "LOW": "low",
    "CRITICAL": "critical",
    "NORMAL": "normal",
}

_ANALYTE_NAMES = (
    r"Glucose|Hemoglobin A1c|HbA1c|Glycated Hemoglobin|Hemoglobin|Total Cholesterol|"
    r"Cholesterol|LDL(?:[- ]?C)?|HDL(?:[- ]?C)?|Triglycerides|Creatinine|TSH|WBC|"
    r"Platelets|Sodium|Potassium|BMI|Blood Pressure|Systolic|Diastolic|"
    r"Comprehensive Metabolic Panel|CMP"
)

# Classic single-line: Glucose 112 H 70-99 mg/dL  OR Glucose: 112 mg/dL (70-99)
_LINE = re.compile(
    rf"^(?P<name>{_ANALYTE_NAMES})\s*[:=]?\s*"
    rf"(?P<value>[<>]?\d+(?:\.\d+)?(?:/\d+(?:\.\d+)?)?|[A-Za-z][\w\-+/]*)\s*"
    rf"(?:(?P<flag>HH|LL|H|L|C|A|N|HIGH|LOW|CRITICAL|NORMAL)\b\s*)?"
    rf"(?P<rest>.*)$",
    re.I,
)

_RANGE_INLINE = re.compile(
    r"(?:\((?P<paren>[^)]+)\)|(?P<open>(?:<|>|≤|≥)?\s*\d+(?:\.\d+)?\s*[-–—to]+\s*\d+(?:\.\d+)?|"
    r"(?:<|>|≤|≥)\s*\d+(?:\.\d+)?))",
    re.I,
)
_UNIT = re.compile(
    r"\b(?P<unit>%|mg/dL|mmol/L|g/dL|ng/mL|mIU/L|K/uL|mmHg|kg/m2|U/L|mcg/dL)\b",
    re.I,
)
_DATE = re.compile(r"(20\d{2}-\d{2}-\d{2})")
_WRAP_RANGE_TAIL = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*(?:mg/dL|%|g/dL|mmol/L)?\s*$", re.I)
_PARTIAL_RANGE = re.compile(
    r"(?P<low>\d+(?:\.\d+)?)\s*[-–—]\s*$"
)


@dataclass
class ParsedLabObservation:
    test_name_raw: str
    value_raw: str
    value_numeric: float | None
    value_text: str | None
    unit_raw: str
    reference_range_raw: str
    abnormal_flag_raw: str
    abnormal_flag: str
    collection_date: str
    source_page: int
    source_text: str
    source_coordinates: dict[str, Any]
    confidence: float
    confidence_metadata: dict[str, Any] = field(default_factory=dict)
    require_review: bool = False
    verification_status: str = "pending"

    def as_field_dict(self) -> dict[str, Any]:
        """Backward-compatible Extraction.fields shape plus V1.3 extensions."""
        return {
            "name": self.test_name_raw,
            "value": self.value_raw,
            "unit": self.unit_raw,
            "reference_range": self.reference_range_raw,
            "effective_date": self.collection_date,
            "confidence": self.confidence,
            "source_region": {
                "page": self.source_page,
                "text": self.source_text,
                **self.source_coordinates,
            },
            "test_name_raw": self.test_name_raw,
            "value_raw": self.value_raw,
            "value_numeric": self.value_numeric,
            "value_text": self.value_text,
            "unit_raw": self.unit_raw,
            "reference_range_raw": self.reference_range_raw,
            "abnormal_flag_raw": self.abnormal_flag_raw,
            "abnormal_flag": self.abnormal_flag,
            "collection_date": self.collection_date,
            "source_page": self.source_page,
            "source_text": self.source_text,
            "source_coordinates": self.source_coordinates,
            "confidence_metadata": self.confidence_metadata,
            "require_review": self.require_review,
            "verification_status": self.verification_status,
            "original_extracted": {
                "value_raw": self.value_raw,
                "unit_raw": self.unit_raw,
                "reference_range_raw": self.reference_range_raw,
                "abnormal_flag_raw": self.abnormal_flag_raw,
            },
        }


def _parse_numeric(value: str) -> float | None:
    try:
        cleaned = value.lstrip("<>").strip()
        if "/" in cleaned:
            return None
        return float(cleaned)
    except ValueError:
        return None


def _flag_norm(raw: str) -> str:
    return _FLAG_MAP.get(raw.upper(), "unknown" if raw else "unknown")


def _extract_range_and_unit(rest: str) -> tuple[str, str]:
    unit = ""
    um = _UNIT.search(rest)
    if um:
        unit = um.group("unit")
    rm = _RANGE_INLINE.search(rest)
    if rm:
        return (rm.group("paren") or rm.group("open") or "").strip(), unit
    # Bare "70-99" without parens
    bare = re.search(r"(\d+(?:\.\d+)?\s*[-–—to]+\s*\d+(?:\.\d+)?)", rest)
    if bare:
        return bare.group(1).replace("–", "-").replace("—", "-").replace(" to ", "-"), unit
    return "", unit


def parse_lab_ocr_text(
    text: str,
    *,
    page: int = 1,
    regions: list[dict[str, Any]] | None = None,
) -> list[ParsedLabObservation]:
    """Parse OCR/full text into laboratory observations with source evidence."""
    lines = [line.rstrip() for line in text.splitlines()]
    date_match = _DATE.search(text)
    collection_date = date_match.group(1) if date_match else ""
    observations: list[ParsedLabObservation] = []
    seen: set[str] = set()
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        i += 1
        if not line or re.match(r"^(test|result|flag|reference|lab report)\b", line, re.I):
            continue

        match = _LINE.match(line)
        if not match:
            continue

        name = match.group("name").strip()
        key = name.lower()
        if key in seen:
            continue

        value_raw = match.group("value").strip()
        flag_raw = (match.group("flag") or "").strip()
        rest = (match.group("rest") or "").strip()

        # Critical wrap case: "Glucose 112 H 70 -" then next line "99"
        range_raw, unit_raw = _extract_range_and_unit(rest)
        confidence = 0.55
        require_review = False
        meta: dict[str, Any] = {"parser": "lab_parser_v1", "line": line}

        partial = _PARTIAL_RANGE.search(rest)
        if partial and i < len(lines):
            nxt = lines[i].strip()
            tail = _WRAP_RANGE_TAIL.match(nxt)
            if tail:
                # Never treat the wrapped high bound as the result value.
                low = partial.group("low")
                high = tail.group(1)
                range_raw = f"{low}-{high}"
                i += 1
                confidence = 0.88
                meta["wrap_range_joined"] = True
                meta["joined_from"] = [line, nxt]
                # Ensure value stays the analyte result, not the wrapped high.
                if value_raw == high:
                    require_review = True
                    confidence = 0.35
                    meta["ambiguous_value_vs_range"] = True

        if not range_raw and not unit_raw and not flag_raw:
            require_review = True
            confidence = min(confidence, 0.4)
            meta["sparse_row"] = True
        elif range_raw and unit_raw:
            confidence = max(confidence, 0.9)
        elif range_raw or unit_raw:
            confidence = max(confidence, 0.72)

        # If rest starts with a dangling low bound without next-line join
        if partial and not meta.get("wrap_range_joined"):
            require_review = True
            confidence = min(confidence, 0.45)
            meta["incomplete_range"] = True

        if not _UNIT.search(unit_raw) and unit_raw == "":
            inferred = {
                "glucose": "mg/dL",
                "hba1c": "%",
                "hemoglobin a1c": "%",
                "hemoglobin": "g/dL",
                "total cholesterol": "mg/dL",
                "cholesterol": "mg/dL",
                "ldl": "mg/dL",
                "hdl": "mg/dL",
                "creatinine": "mg/dL",
            }.get(key)
            if inferred and range_raw:
                unit_raw = inferred
                meta["unit_inferred"] = True
                confidence = min(confidence, 0.7)

        numeric = _parse_numeric(value_raw)
        text_value = None if numeric is not None else value_raw
        if numeric is None and not re.match(r"^[A-Za-z]", value_raw):
            require_review = True
            confidence = min(confidence, 0.4)

        coords = {"x": 0.0, "y": 0.0, "width": 1.0, "height": 0.05}
        if regions:
            for region in regions:
                if name.lower() in str(region.get("text", "")).lower():
                    coords = {
                        "x": float(region.get("x", 0)),
                        "y": float(region.get("y", 0)),
                        "width": float(region.get("width", 1)),
                        "height": float(region.get("height", 0.05)),
                    }
                    break

        source_text = line
        if meta.get("joined_from"):
            source_text = "\n".join(meta["joined_from"])

        seen.add(key)
        observations.append(
            ParsedLabObservation(
                test_name_raw=name if name.lower() != "hba1c" else "HbA1c",
                value_raw=value_raw,
                value_numeric=numeric,
                value_text=text_value,
                unit_raw=unit_raw,
                reference_range_raw=range_raw.replace("–", "-").replace("—", "-"),
                abnormal_flag_raw=flag_raw,
                abnormal_flag=_flag_norm(flag_raw) if flag_raw else "unknown",
                collection_date=collection_date,
                source_page=page,
                source_text=source_text,
                source_coordinates=coords,
                confidence=round(confidence, 3),
                confidence_metadata=meta,
                require_review=require_review or confidence < 0.6,
            )
        )

    return observations


def classify_document_text(text: str) -> dict[str, Any]:
    """Heuristic document classification. Low confidence → reviewable."""
    lower = text.lower()
    scores = {
        "laboratory_report": 0.0,
        "imaging_report": 0.0,
        "prescription": 0.0,
        "discharge_summary": 0.0,
        "clinical_note": 0.0,
        "other_medical_document": 0.1,
        "unknown": 0.05,
    }
    lab_hits = sum(
        1
        for token in (
            "glucose",
            "hemoglobin",
            "cholesterol",
            "reference range",
            "mg/dl",
            "lab report",
            "specimen",
            "hba1c",
        )
        if token in lower
    )
    scores["laboratory_report"] = min(0.95, 0.25 + lab_hits * 0.18)
    if "mri" in lower or "radiology" in lower or "imaging" in lower:
        scores["imaging_report"] = 0.7
    if "rx" in lower or "dispense" in lower or "prescription" in lower:
        scores["prescription"] = 0.65
    if "discharge" in lower:
        scores["discharge_summary"] = 0.7
    if "progress note" in lower or "assessment/plan" in lower:
        scores["clinical_note"] = 0.6

    category = max(scores, key=scores.get)
    confidence = scores[category]
    return {
        "category": category,
        "confidence": round(confidence, 3),
        "scores": scores,
        "auto_extract_lab": category == "laboratory_report" and confidence >= 0.5,
        "requires_classification_review": confidence < 0.5,
    }
