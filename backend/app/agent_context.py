"""V2.1.1 trusted server-side agent execution context."""

from __future__ import annotations

from datetime import timedelta
from typing import Any
from uuid import uuid4

from sqlalchemy.orm import Session

from app.agent_capabilities import capability_allowed_tools, get_enabled_capability
from app.agent_models import AiExecutionContextRecord
from app.auth import ApiError
from app.authorization import require_clinic_patient
from app.consent_gate import require_patient_consent
from app.models import TenantMembership, User, utcnow

POLICY_VERSION = "2.1.1"
DEFAULT_CONTEXT_TTL_MINUTES = 30


def _aware_compare_expired(expiration_at, now) -> bool:
    expires = expiration_at
    if expires.tzinfo is None and now.tzinfo is not None:
        expires = expires.replace(tzinfo=now.tzinfo)
    elif expires.tzinfo is not None and now.tzinfo is None:
        now = now.replace(tzinfo=expires.tzinfo)
    return expires < now


def create_execution_context(
    session: Session,
    *,
    organization_id: str,
    user: User,
    membership: TenantMembership,
    capability_code: str,
    capability_version: str | None = None,
    patient_id: str | None = None,
    encounter_id: str | None = None,
    agent_run_id: str | None = None,
    request_id: str = "",
    correlation_id: str | None = None,
) -> AiExecutionContextRecord:
    """Mint a trusted context after authZ — never trust client-supplied identity fields."""
    if membership.tenant_id != organization_id:
        raise ApiError("TENANT_NOT_FOUND", "Tenant not found.", 404)

    capability = get_enabled_capability(
        session, capability_code=capability_code, version=capability_version
    )
    tools = capability_allowed_tools(session, capability)

    if patient_id:
        require_clinic_patient(session, tenant_id=organization_id, user_id=patient_id)
        require_patient_consent(
            session,
            tenant_id=organization_id,
            patient_id=patient_id,
            actor=user,
            membership=membership,
            request_id=request_id,
        )

    auth_ref = f"authz-{uuid4().hex[:16]}"
    record = AiExecutionContextRecord(
        organization_id=organization_id,
        agent_run_id=agent_run_id,
        actor_id=user.id,
        patient_id=patient_id,
        encounter_id=encounter_id,
        capability_code=capability.capability_code,
        capability_version=capability.capability_version,
        authorization_reference=auth_ref,
        policy_version=POLICY_VERSION,
        correlation_id=correlation_id or uuid4().hex,
        context_reference=f"ctx-{uuid4().hex}",
        status="active",
        permitted_tools=tools,
        expiration_at=utcnow() + timedelta(minutes=DEFAULT_CONTEXT_TTL_MINUTES),
    )
    session.add(record)
    session.flush()
    return record


def revalidate_context(session: Session, *, context: AiExecutionContextRecord) -> AiExecutionContextRecord:
    if context.status == "revoked":
        raise ApiError("CONTEXT_REVOKED", "Execution context was revoked.", 403)
    if context.status != "active":
        raise ApiError("CONTEXT_INACTIVE", "Execution context is not active.", 403)
    if _aware_compare_expired(context.expiration_at, utcnow()):
        context.status = "expired"
        session.flush()
        raise ApiError("CONTEXT_EXPIRED", "Execution context has expired.", 410)
    return context


def revoke_context(session: Session, *, context: AiExecutionContextRecord) -> None:
    context.status = "revoked"
    session.flush()


def context_dict(row: AiExecutionContextRecord) -> dict[str, Any]:
    return {
        "execution_id": row.id,
        "organization_id": row.organization_id,
        "actor_id": row.actor_id,
        "patient_id": row.patient_id,
        "encounter_id": row.encounter_id,
        "capability_code": row.capability_code,
        "capability_version": row.capability_version,
        "authorization_reference": row.authorization_reference,
        "policy_version": row.policy_version,
        "correlation_id": row.correlation_id,
        "status": row.status,
        "permitted_tools": row.permitted_tools or [],
        "expiration_at": row.expiration_at.isoformat() if row.expiration_at else None,
    }
