"""Health Trends: Observation time-series + provenance → source Document links."""

from __future__ import annotations

import re
from typing import Any

from sqlalchemy.orm import Session

from app.fhir_store import search_resources

# Canonical test keys → display label + matching aliases (lowercased Observation.code.text)
TREND_TESTS: dict[str, dict[str, Any]] = {
    "glucose": {
        "label": "Blood glucose",
        "aliases": ("glucose", "blood glucose", "blood sugar", "fbg", "rbs"),
        "default_unit": "mg/dL",
    },
    "hba1c": {
        "label": "HbA1c",
        "aliases": ("hba1c", "hemoglobin a1c", "glycated hemoglobin", "a1c"),
        "default_unit": "%",
    },
    "cholesterol": {
        "label": "Total cholesterol",
        "aliases": ("cholesterol", "total cholesterol"),
        "default_unit": "mg/dL",
    },
    "ldl": {
        "label": "LDL cholesterol",
        "aliases": ("ldl", "ldl cholesterol", "ldl-c"),
        "default_unit": "mg/dL",
    },
    "hdl": {
        "label": "HDL cholesterol",
        "aliases": ("hdl", "hdl cholesterol", "hdl-c"),
        "default_unit": "mg/dL",
    },
    "hemoglobin": {
        "label": "Hemoglobin",
        "aliases": ("hemoglobin", "haemoglobin", "hgb"),
        "default_unit": "g/dL",
    },
    "triglycerides": {
        "label": "Triglycerides",
        "aliases": ("triglycerides", "trig", "tg"),
        "default_unit": "mg/dL",
    },
    "creatinine": {
        "label": "Creatinine",
        "aliases": ("creatinine", "creat"),
        "default_unit": "mg/dL",
    },
}

_RANGE = re.compile(
    r"(?P<low>-?\d+(?:\.\d+)?)\s*[-–—to]+\s*(?P<high>-?\d+(?:\.\d+)?)",
    re.I,
)


def list_supported_tests() -> list[dict[str, str]]:
    return [
        {"code": code, "label": meta["label"], "unit": meta["default_unit"]}
        for code, meta in TREND_TESTS.items()
    ]


def normalize_test_code(raw: str) -> str | None:
    lowered = raw.strip().lower()
    compact = lowered.replace(" ", "").replace("-", "").replace("_", "")
    for code, meta in TREND_TESTS.items():
        if compact == code:
            return code
        aliases_compact = {
            a.replace(" ", "").replace("-", "").replace("_", "") for a in meta["aliases"]
        }
        if compact in aliases_compact or lowered in meta["aliases"]:
            return code
    return None


def _code_text(obs: dict[str, Any]) -> str:
    code = obs.get("code") or {}
    if isinstance(code, dict) and code.get("text"):
        return str(code["text"])
    for coding in code.get("coding") or []:
        if isinstance(coding, dict) and coding.get("display"):
            return str(coding["display"])
        if isinstance(coding, dict) and coding.get("code"):
            return str(coding["code"])
    return ""


def _matches_test(obs: dict[str, Any], test_code: str) -> bool:
    """Exact alias match only — avoids hemoglobin alias 'hb' colliding with HbA1c."""
    meta = TREND_TESTS[test_code]
    text = _code_text(obs).strip().lower()
    if not text:
        return False
    compact = text.replace(" ", "").replace("-", "").replace("_", "")
    if compact == test_code:
        return True
    for alias in meta["aliases"]:
        if text == alias:
            return True
        if compact == alias.replace(" ", "").replace("-", "").replace("_", ""):
            return True
    return False


def classify_observation(obs: dict[str, Any]) -> str | None:
    for code in TREND_TESTS:
        if _matches_test(obs, code):
            return code
    return None


def _numeric_value(obs: dict[str, Any]) -> tuple[float | None, str]:
    qty = obs.get("valueQuantity")
    if isinstance(qty, dict) and qty.get("value") is not None:
        try:
            return float(qty["value"]), str(qty.get("unit") or "")
        except (TypeError, ValueError):
            pass
    raw = obs.get("valueString")
    if isinstance(raw, str) and raw.strip():
        try:
            return float(raw.strip().split()[0]), ""
        except ValueError:
            pass
    return None, ""


def _parse_reference_range(obs: dict[str, Any]) -> tuple[float | None, float | None, str]:
    ranges = obs.get("referenceRange") or []
    for item in ranges:
        if not isinstance(item, dict):
            continue
        low = item.get("low")
        high = item.get("high")
        if isinstance(low, dict) and isinstance(high, dict):
            try:
                return float(low["value"]), float(high["value"]), str(item.get("text") or "")
            except (KeyError, TypeError, ValueError):
                pass
        text = str(item.get("text") or "")
        m = _RANGE.search(text)
        if m:
            return float(m.group("low")), float(m.group("high")), text
    return None, None, ""


def _effective_at(obs: dict[str, Any]) -> str:
    for key in ("effectiveDateTime", "issued"):
        value = obs.get(key)
        if isinstance(value, str) and value:
            return value
    meta = obs.get("meta") or {}
    if isinstance(meta, dict) and meta.get("lastUpdated"):
        return str(meta["lastUpdated"])
    return ""


def _document_links_for_observations(
    session: Session,
    *,
    tenant_id: str,
    patient_id: str,
    observation_ids: set[str],
) -> dict[str, dict[str, str | None]]:
    """Map Observation.id → {document_reference_id, extraction_id} via Provenance."""
    if not observation_ids:
        return {}
    provenances = search_resources(
        session,
        tenant_id=tenant_id,
        resource_type="Provenance",
        patient_id=patient_id,
        limit=200,
    )
    links: dict[str, dict[str, str | None]] = {}
    for prov in provenances:
        targets = prov.get("target") or []
        obs_id: str | None = None
        for target in targets:
            if not isinstance(target, dict):
                continue
            ref = str(target.get("reference") or "")
            if ref.startswith("Observation/"):
                candidate = ref.split("/", 1)[1]
                if candidate in observation_ids:
                    obs_id = candidate
                    break
        if not obs_id:
            continue
        doc_id: str | None = None
        extraction_id: str | None = None
        for entity in prov.get("entity") or []:
            if not isinstance(entity, dict):
                continue
            what = entity.get("what") or {}
            ref = str(what.get("reference") or "")
            if ref.startswith("DocumentReference/"):
                doc_id = ref.split("/", 1)[1]
            elif ref.startswith("Extraction/"):
                extraction_id = ref.split("/", 1)[1]
        existing = links.get(obs_id) or {}
        links[obs_id] = {
            "document_reference_id": doc_id or existing.get("document_reference_id"),
            "extraction_id": extraction_id or existing.get("extraction_id"),
        }
    return links


def _derived_document_id(obs: dict[str, Any]) -> str | None:
    for item in obs.get("derivedFrom") or []:
        if not isinstance(item, dict):
            continue
        ref = str(item.get("reference") or "")
        if ref.startswith("DocumentReference/"):
            return ref.split("/", 1)[1]
    return None


def _patient_observations(
    session: Session,
    *,
    tenant_id: str,
    patient_id: str,
) -> list[dict[str, Any]]:
    return search_resources(
        session,
        tenant_id=tenant_id,
        resource_type="Observation",
        patient_id=patient_id,
        limit=200,
    )


def list_patient_trend_tests(
    session: Session,
    *,
    tenant_id: str,
    patient_id: str,
) -> list[dict[str, Any]]:
    """Supported tests annotated with how many numeric points the patient has."""
    observations = _patient_observations(
        session, tenant_id=tenant_id, patient_id=patient_id
    )
    counts: dict[str, int] = {code: 0 for code in TREND_TESTS}
    latest: dict[str, float | None] = {code: None for code in TREND_TESTS}
    latest_at: dict[str, str] = {code: "" for code in TREND_TESTS}
    for obs in observations:
        if obs.get("status") in {"entered-in-error", "cancelled"}:
            continue
        code = classify_observation(obs)
        if not code:
            continue
        value, _unit = _numeric_value(obs)
        if value is None:
            continue
        counts[code] += 1
        effective = _effective_at(obs)
        if effective >= latest_at[code]:
            latest_at[code] = effective
            latest[code] = value

    rows: list[dict[str, Any]] = []
    for code, meta in TREND_TESTS.items():
        rows.append(
            {
                "code": code,
                "label": meta["label"],
                "unit": meta["default_unit"],
                "point_count": counts[code],
                "latest_value": latest[code],
                "latest_at": latest_at[code] or None,
                "has_data": counts[code] > 0,
            }
        )
    # Prefer tests with data first, then catalog order
    rows.sort(key=lambda r: (0 if r["has_data"] else 1, -r["point_count"], r["label"]))
    return rows


def build_trend_series(
    session: Session,
    *,
    tenant_id: str,
    patient_id: str,
    test_code: str,
    date_from: str | None = None,
    date_to: str | None = None,
) -> dict[str, Any]:
    meta = TREND_TESTS[test_code]
    observations = _patient_observations(
        session, tenant_id=tenant_id, patient_id=patient_id
    )
    matched: list[dict[str, Any]] = []
    for obs in observations:
        if obs.get("status") in {"entered-in-error", "cancelled"}:
            continue
        if not _matches_test(obs, test_code):
            continue
        value, _unit = _numeric_value(obs)
        if value is None:
            continue
        matched.append(obs)

    obs_ids = {str(o["id"]) for o in matched if o.get("id")}
    provenance_links = _document_links_for_observations(
        session, tenant_id=tenant_id, patient_id=patient_id, observation_ids=obs_ids
    )

    points: list[dict[str, Any]] = []
    ref_low: float | None = None
    ref_high: float | None = None
    ref_text = ""
    unit = meta["default_unit"]

    for obs in matched:
        value, obs_unit = _numeric_value(obs)
        assert value is not None
        low, high, text = _parse_reference_range(obs)
        effective = _effective_at(obs) or "1970-01-01T00:00:00Z"
        if date_from and effective < date_from:
            continue
        if date_to and effective > date_to:
            continue
        if obs_unit:
            unit = obs_unit
        obs_id = str(obs.get("id") or "")
        link = provenance_links.get(obs_id) or {}
        doc_id = link.get("document_reference_id") or _derived_document_id(obs)
        in_range: bool | None = None
        if low is not None and high is not None:
            in_range = low <= value <= high
        points.append(
            {
                "observation_id": obs_id,
                "effective_at": effective,
                "value": value,
                "unit": obs_unit or unit,
                "reference_low": low,
                "reference_high": high,
                "reference_range_text": text,
                "in_range": in_range,
                "document_reference_id": doc_id,
                "extraction_id": link.get("extraction_id"),
                "status": obs.get("status") or "final",
            }
        )

    points.sort(key=lambda p: p["effective_at"])

    for point in reversed(points):
        if point["reference_low"] is not None and point["reference_high"] is not None:
            ref_low = point["reference_low"]
            ref_high = point["reference_high"]
            ref_text = point["reference_range_text"] or ref_text
            break

    # Fill missing point-level ranges from series range for chart/insights consistency
    if ref_low is not None and ref_high is not None:
        for point in points:
            if point["reference_low"] is None or point["reference_high"] is None:
                point["reference_low"] = ref_low
                point["reference_high"] = ref_high
                point["reference_range_text"] = point["reference_range_text"] or ref_text
                point["in_range"] = ref_low <= point["value"] <= ref_high

    latest = points[-1] if points else None
    previous = points[-2] if len(points) >= 2 else None
    delta = None
    delta_pct = None
    if latest and previous:
        delta = latest["value"] - previous["value"]
        if previous["value"] != 0:
            delta_pct = (delta / abs(previous["value"])) * 100.0

    return {
        "patient_id": patient_id,
        "test_code": test_code,
        "test_label": meta["label"],
        "unit": unit,
        "reference_low": ref_low,
        "reference_high": ref_high,
        "reference_range_text": ref_text,
        "point_count": len(points),
        "latest_value": latest["value"] if latest else None,
        "latest_at": latest["effective_at"] if latest else None,
        "previous_value": previous["value"] if previous else None,
        "delta": delta,
        "delta_pct": delta_pct,
        "min_value": min((p["value"] for p in points), default=None),
        "max_value": max((p["value"] for p in points), default=None),
        "points": points,
    }
