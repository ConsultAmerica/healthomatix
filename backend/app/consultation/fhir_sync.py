"""Sync scheduling/visit events into the FHIR R4 facade."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.fhir_store import create_resource, get_resource, update_resource, write_provenance
from app.models import Appointment, ProviderAvailability


def _iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sync_fhir_slot_and_appointment(
    session: Session,
    *,
    tenant_id: str,
    appointment: Appointment,
    slot: ProviderAvailability,
) -> dict[str, Any]:
    """Mirror a booked SQL appointment as FHIR Slot + Appointment (same ids)."""
    slot_body = {
        "resourceType": "Slot",
        "status": "busy",
        "start": _iso(slot.starts_at),
        "end": _iso(slot.ends_at),
        "schedule": {"reference": f"Practitioner/{slot.provider_user_id}"},
        "extension": [
            {"url": "urn:healthomatix:location-id", "valueString": slot.location_id},
        ],
    }
    if get_resource(session, tenant_id=tenant_id, resource_type="Slot", resource_id=slot.id):
        update_resource(
            session,
            tenant_id=tenant_id,
            resource_type="Slot",
            resource_id=slot.id,
            body=slot_body,
        )
    else:
        create_resource(
            session,
            tenant_id=tenant_id,
            resource_type="Slot",
            resource_id=slot.id,
            body=slot_body,
        )

    appt_body = {
        "resourceType": "Appointment",
        "status": "booked" if appointment.status == "booked" else appointment.status,
        "start": _iso(slot.starts_at),
        "end": _iso(slot.ends_at),
        "slot": [{"reference": f"Slot/{slot.id}"}],
        "participant": [
            {
                "actor": {"reference": f"Patient/{appointment.patient_user_id}"},
                "status": "accepted",
            },
            {
                "actor": {"reference": f"Practitioner/{slot.provider_user_id}"},
                "status": "accepted",
            },
        ],
        "extension": [
            {
                "url": "urn:healthomatix:clinic-patient-id",
                "valueString": appointment.clinic_patient_id,
            }
        ],
    }
    # Appointment is patient-scoped via participant; set patient_id via subject-like field
    # by adding supportingInformation patient for our facade index:
    appt_body["supportingInformation"] = [
        {"reference": f"Patient/{appointment.patient_user_id}"}
    ]
    if get_resource(
        session, tenant_id=tenant_id, resource_type="Appointment", resource_id=appointment.id
    ):
        created = update_resource(
            session,
            tenant_id=tenant_id,
            resource_type="Appointment",
            resource_id=appointment.id,
            body=appt_body,
        ) or appt_body
    else:
        created = create_resource(
            session,
            tenant_id=tenant_id,
            resource_type="Appointment",
            resource_id=appointment.id,
            body=appt_body,
        )
    # Ensure patient_id index — create_resource uses patient_id_from_resource which
    # looks at subject/patient; patch row if needed via supportingInformation fallback.
    return created


def create_visit_encounter(
    session: Session,
    *,
    tenant_id: str,
    patient_id: str,
    provider_user_id: str,
    appointment_id: str,
    session_id: str,
    started_at: datetime,
    ended_at: datetime,
    follow_up_plan: str,
    actor_user_id: str,
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "resourceType": "Encounter",
        "status": "finished",
        "class": {
            "system": "http://terminology.hl7.org/CodeSystem/v3-ActCode",
            "code": "VR",
            "display": "virtual",
        },
        "type": [{"text": "Telehealth video visit"}],
        "subject": {"reference": f"Patient/{patient_id}"},
        "participant": [
            {
                "individual": {"reference": f"Practitioner/{provider_user_id}"},
            }
        ],
        "appointment": [{"reference": f"Appointment/{appointment_id}"}],
        "period": {"start": _iso(started_at), "end": _iso(ended_at)},
        "extension": [
            {"url": "urn:healthomatix:video-session-id", "valueString": session_id},
        ],
    }
    if follow_up_plan.strip():
        body["reasonCode"] = [{"text": "Follow-up plan documented"}]
        body["extension"].append(
            {
                "url": "urn:healthomatix:follow-up-plan",
                "valueString": follow_up_plan.strip()[:4000],
            }
        )
    encounter = create_resource(
        session, tenant_id=tenant_id, resource_type="Encounter", body=body
    )
    write_provenance(
        session,
        tenant_id=tenant_id,
        target_type="Encounter",
        target_id=encounter["id"],
        patient_id=patient_id,
        agent_user_id=actor_user_id,
        activity_code="CREATE",
        entity_refs=[
            ("Appointment", appointment_id),
            ("VideoSession", session_id),
        ],
    )
    return encounter
