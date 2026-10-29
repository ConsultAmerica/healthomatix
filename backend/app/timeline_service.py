"""Merged patient Health Timeline from documents, labs, visits, and appointments."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.fhir_store import search_resources
from app.models import Appointment, MedicalDocument, ProviderAvailability, ProviderProfile

EventKind = Literal["observation", "document", "encounter", "appointment", "session"]


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _obs_title(resource: dict[str, Any]) -> str:
    code = resource.get("code") or {}
    text = code.get("text") if isinstance(code, dict) else None
    if text:
        return str(text)
    return "Lab observation"


def _obs_summary(resource: dict[str, Any]) -> str:
    qty = resource.get("valueQuantity") or {}
    if isinstance(qty, dict) and qty.get("value") is not None:
        unit = qty.get("unit") or ""
        return f"{qty['value']} {unit}".strip()
    if resource.get("valueString"):
        return str(resource["valueString"])
    return resource.get("status") or "recorded"


def build_health_timeline(
    session: Session,
    *,
    tenant_id: str,
    patient_user_id: str,
    limit: int = 50,
) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []

    observations = search_resources(
        session,
        tenant_id=tenant_id,
        resource_type="Observation",
        patient_id=patient_user_id,
        limit=limit,
    )
    for resource in observations:
        occurred = _parse_dt(resource.get("effectiveDateTime")) or _parse_dt(
            (resource.get("meta") or {}).get("lastUpdated")
        )
        if occurred is None:
            continue
        source_doc = None
        for ref in resource.get("derivedFrom") or []:
            if isinstance(ref, dict):
                reference = str(ref.get("reference") or "")
                if reference.startswith("DocumentReference/"):
                    source_doc = reference.split("/", 1)[1]
                    break
        events.append(
            {
                "event_id": f"observation:{resource.get('id')}",
                "kind": "observation",
                "title": _obs_title(resource),
                "summary": _obs_summary(resource),
                "status": str(resource.get("status") or "final"),
                "occurred_at": occurred,
                "resource_type": "Observation",
                "resource_id": str(resource.get("id") or ""),
                "source_document_id": source_doc,
                "href_hint": "trends",
            }
        )

    documents = session.execute(
        select(MedicalDocument)
        .where(
            MedicalDocument.tenant_id == tenant_id,
            MedicalDocument.patient_user_id == patient_user_id,
            MedicalDocument.lifecycle_state == "stored",
        )
        .order_by(MedicalDocument.created_at.desc())
        .limit(limit)
    ).scalars().all()
    for document in documents:
        events.append(
            {
                "event_id": f"document:{document.id}",
                "kind": "document",
                "title": document.original_filename,
                "summary": f"{document.content_type} · {document.size_bytes} bytes",
                "status": document.lifecycle_state,
                "occurred_at": _as_utc(document.created_at),
                "resource_type": "DocumentReference",
                "resource_id": document.id,
                "source_document_id": document.id,
                "href_hint": "records",
            }
        )

    encounters = search_resources(
        session,
        tenant_id=tenant_id,
        resource_type="Encounter",
        patient_id=patient_user_id,
        limit=limit,
    )
    for resource in encounters:
        period = resource.get("period") or {}
        occurred = _parse_dt(period.get("start")) or _parse_dt(
            (resource.get("meta") or {}).get("lastUpdated")
        )
        if occurred is None:
            continue
        class_code = ""
        klass = resource.get("class")
        if isinstance(klass, dict):
            class_code = str(klass.get("code") or klass.get("display") or "")
        events.append(
            {
                "event_id": f"encounter:{resource.get('id')}",
                "kind": "encounter",
                "title": "Clinical visit",
                "summary": class_code or str(resource.get("status") or "finished"),
                "status": str(resource.get("status") or "finished"),
                "occurred_at": occurred,
                "resource_type": "Encounter",
                "resource_id": str(resource.get("id") or ""),
                "source_document_id": None,
                "href_hint": "visits",
            }
        )

    appointments = session.execute(
        select(Appointment, ProviderAvailability, ProviderProfile)
        .join(
            ProviderAvailability,
            (ProviderAvailability.tenant_id == Appointment.tenant_id)
            & (ProviderAvailability.id == Appointment.availability_id),
        )
        .outerjoin(
            ProviderProfile,
            ProviderProfile.user_id == ProviderAvailability.provider_user_id,
        )
        .where(
            Appointment.tenant_id == tenant_id,
            Appointment.patient_user_id == patient_user_id,
        )
        .order_by(ProviderAvailability.starts_at.desc())
        .limit(limit)
    ).all()
    for appointment, slot, provider_profile in appointments:
        provider_name = (
            provider_profile.display_name
            if provider_profile and provider_profile.display_name
            else "Provider"
        )
        events.append(
            {
                "event_id": f"appointment:{appointment.id}",
                "kind": "appointment",
                "title": f"Appointment · {provider_name}",
                "summary": f"{slot.starts_at.astimezone(UTC).strftime('%Y-%m-%d %H:%M')} UTC",
                "status": appointment.status,
                "occurred_at": _as_utc(slot.starts_at),
                "resource_type": "Appointment",
                "resource_id": appointment.id,
                "source_document_id": None,
                "href_hint": "appointments",
            }
        )

    events.sort(key=lambda item: item["occurred_at"], reverse=True)
    return events[:limit]
