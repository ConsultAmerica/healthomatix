from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import AuditEvent


def append_audit_event(
    session: Session,
    *,
    actor_user_id: str | None,
    tenant_id: str | None,
    action: str,
    subject_type: str,
    subject_id: str,
    request_id: str = "",
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
    return event

