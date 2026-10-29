from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.models import AuditEvent, new_id


def append_audit_event(
    session: Session,
    *,
    actor_user_id: str | None,
    tenant_id: str | None,
    action: str,
    subject_type: str,
    subject_id: str,
    request_id: str = "",
    fhir_outcome: str = "success",
) -> AuditEvent:
    values = (action, subject_type, subject_id)
    if any(not value or len(value) > limit for value, limit in zip(values, (128, 64, 128))):
        raise ValueError("Audit event fields must be non-empty bounded identifiers.")
    event = AuditEvent(
        actor_user_id=actor_user_id,
        tenant_id=tenant_id,
        action=action,
        subject_type=subject_type,
        subject_id=subject_id,
        request_id=request_id[:64],
    )
    session.add(event)
    if tenant_id:
        _append_fhir_audit_event(
            session,
            tenant_id=tenant_id,
            actor_user_id=actor_user_id,
            action=action,
            subject_type=subject_type,
            subject_id=subject_id,
            request_id=request_id,
            outcome=fhir_outcome,
        )
    return event


def _append_fhir_audit_event(
    session: Session,
    *,
    tenant_id: str,
    actor_user_id: str | None,
    action: str,
    subject_type: str,
    subject_id: str,
    request_id: str,
    outcome: str,
) -> None:
    # Lazy import to avoid circular imports at module load.
    from app.fhir_store import create_resource

    now = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    outcome_code = "0" if outcome == "success" else "8"
    body: dict[str, Any] = {
        "resourceType": "AuditEvent",
        "type": {
            "system": "http://terminology.hl7.org/CodeSystem/audit-event-type",
            "code": "rest",
            "display": action,
        },
        "action": "R" if "read" in action or "denied" in action else "C",
        "recorded": now,
        "outcome": outcome_code,
        "outcomeDesc": action,
        "agent": [
            {
                "who": {
                    "reference": f"Practitioner/{actor_user_id}"
                    if actor_user_id
                    else "Device/system"
                },
                "requestor": True,
            }
        ],
        "entity": [
            {
                "what": {"reference": f"{subject_type}/{subject_id}"},
            }
        ],
        "extension": [
            {"url": "urn:healthomatix:request-id", "valueString": request_id[:64]},
        ],
    }
    create_resource(
        session,
        tenant_id=tenant_id,
        resource_type="AuditEvent",
        resource_id=new_id(),
        body=body,
    )
