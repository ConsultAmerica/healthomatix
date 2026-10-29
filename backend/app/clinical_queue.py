"""Clinic workboard aggregates for clinician dashboards (synthetic demos)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.fhir_models import ClinicalDraft, Extraction, VideoSession
from app.models import (
    Appointment,
    ClinicLocation,
    ClinicPatient,
    ProviderAvailability,
    ProviderProfile,
)


def build_clinical_workboard(
    session: Session,
    *,
    tenant_id: str,
    provider_user_id: str | None = None,
) -> dict:
    now = datetime.now(UTC)
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    day_end = day_start + timedelta(days=1)

    appt_stmt = (
        select(
            Appointment,
            ProviderAvailability,
            ClinicPatient,
            ProviderProfile.display_name,
            ClinicLocation.name,
            ClinicLocation.timezone,
        )
        .join(
            ProviderAvailability,
            (ProviderAvailability.tenant_id == Appointment.tenant_id)
            & (ProviderAvailability.id == Appointment.availability_id),
        )
        .join(
            ClinicPatient,
            (ClinicPatient.tenant_id == Appointment.tenant_id)
            & (ClinicPatient.id == Appointment.clinic_patient_id),
        )
        .join(
            ProviderProfile,
            ProviderProfile.user_id == ProviderAvailability.provider_user_id,
        )
        .join(
            ClinicLocation,
            (ClinicLocation.tenant_id == ProviderAvailability.tenant_id)
            & (ClinicLocation.id == ProviderAvailability.location_id),
        )
        .where(
            Appointment.tenant_id == tenant_id,
            Appointment.status == "booked",
            ProviderAvailability.starts_at >= day_start,
            ProviderAvailability.starts_at < day_end,
        )
        .order_by(ProviderAvailability.starts_at.asc())
        .limit(20)
    )
    if provider_user_id:
        appt_stmt = appt_stmt.where(ProviderAvailability.provider_user_id == provider_user_id)

    today_appointments = []
    for appointment, slot, clinic_patient, provider_name, location_name, timezone_name in session.execute(
        appt_stmt
    ).all():
        today_appointments.append(
            {
                "appointment_id": appointment.id,
                "clinic_patient_id": clinic_patient.id,
                "chart_number": clinic_patient.chart_number or "",
                "starts_at": slot.starts_at,
                "ends_at": slot.ends_at,
                "provider_user_id": slot.provider_user_id,
                "provider_name": provider_name or "",
                "location_name": location_name or "",
                "timezone": timezone_name or "UTC",
                "status": appointment.status,
                "appointment_type": "Visit",
            }
        )

    waiting = session.execute(
        select(VideoSession)
        .where(
            VideoSession.tenant_id == tenant_id,
            VideoSession.status.in_(("scheduled", "live")),
        )
        .order_by(VideoSession.created_at.desc())
        .limit(20)
    ).scalars().all()
    waiting_sessions = [
        {
            "session_id": row.id,
            "clinic_patient_id": row.clinic_patient_id,
            "status": row.status,
            "appointment_id": row.appointment_id,
            "provider_user_id": row.provider_user_id,
            "created_at": row.created_at,
        }
        for row in waiting
        if not provider_user_id or row.provider_user_id == provider_user_id
    ]

    pending_extractions = session.execute(
        select(Extraction, ClinicPatient)
        .outerjoin(
            ClinicPatient,
            (ClinicPatient.tenant_id == Extraction.tenant_id)
            & (ClinicPatient.patient_user_id == Extraction.patient_id),
        )
        .where(Extraction.tenant_id == tenant_id, Extraction.status == "draft")
        .order_by(Extraction.created_at.desc())
        .limit(20)
    ).all()
    extraction_rows = [
        {
            "extraction_id": extraction.id,
            "document_id": extraction.document_id,
            "patient_user_id": extraction.patient_id,
            "clinic_patient_id": clinic_patient.id if clinic_patient else None,
            "field_count": len(extraction.fields or []),
            "created_at": extraction.created_at,
        }
        for extraction, clinic_patient in pending_extractions
    ]

    pending_drafts = session.execute(
        select(ClinicalDraft)
        .where(ClinicalDraft.tenant_id == tenant_id, ClinicalDraft.status == "draft")
        .order_by(ClinicalDraft.created_at.desc())
        .limit(20)
    ).scalars().all()
    draft_rows = [
        {
            "draft_id": draft.id,
            "draft_type": draft.draft_type,
            "patient_id": draft.patient_id,
            "title": draft.title,
            "session_id": draft.session_id,
            "created_at": draft.created_at,
        }
        for draft in pending_drafts
    ]

    return {
        "today_appointments": today_appointments,
        "waiting_sessions": waiting_sessions,
        "pending_extractions": extraction_rows,
        "pending_drafts": draft_rows,
        "counts": {
            "today_appointments": len(today_appointments),
            "waiting_sessions": len(waiting_sessions),
            "pending_extractions": len(extraction_rows),
            "pending_drafts": len(draft_rows),
        },
    }
