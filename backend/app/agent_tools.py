"""V2.0 agent tool gateway — server-side authorization, never trust model claims."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import ApiError
from app.authorization import require_clinic_patient
from app.consent_gate import require_patient_consent
from app.fhir_store import get_resource, search_resources
from app.models import TenantMembership, User
from app.ops_models import SupportTicket
from app.interop_models import IntegrationTransaction


ToolHandler = Callable[..., dict[str, Any]]

# Tools that must never execute autonomously as clinical/financial truth
FORBIDDEN_AUTONOMOUS = frozenset(
    {
        "clinical.diagnose",
        "clinical.prescribe",
        "clinical.sign_note",
        "clinical.approve_treatment",
        "identity.merge_patients",
        "lab.approve_observation",
        "billing.submit_claim",
        "billing.issue_refund",
        "billing.modify_ledger",
        "admin.change_privileges",
        "privacy.disclose_phi",
        "clinical.delete_records",
    }
)


def canonical_hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _patient_summary(
    session: Session,
    *,
    tenant_id: str,
    user: User,
    membership: TenantMembership,
    patient_id: str,
    request_id: str,
) -> dict[str, Any]:
    require_clinic_patient(session, tenant_id=tenant_id, user_id=patient_id)
    require_patient_consent(
        session,
        tenant_id=tenant_id,
        patient_id=patient_id,
        actor=user,
        membership=membership,
        request_id=request_id,
    )
    patient = get_resource(
        session, tenant_id=tenant_id, resource_type="Patient", resource_id=patient_id
    )
    return {
        "patient_id": patient_id,
        "resource_present": patient is not None,
        "name": (patient or {}).get("name"),
        "note": "Authorized demographic summary only — not a clinical diagnosis.",
    }


def _verified_observations(
    session: Session,
    *,
    tenant_id: str,
    user: User,
    membership: TenantMembership,
    patient_id: str,
    request_id: str,
) -> dict[str, Any]:
    require_clinic_patient(session, tenant_id=tenant_id, user_id=patient_id)
    require_patient_consent(
        session,
        tenant_id=tenant_id,
        patient_id=patient_id,
        actor=user,
        membership=membership,
        request_id=request_id,
    )
    rows = search_resources(
        session, tenant_id=tenant_id, resource_type="Observation", patient_id=patient_id, limit=20
    )
    verified = []
    unverified = []
    for obs in rows:
        extensions = obs.get("extension") or []
        is_unverified = any(
            e.get("valueString") == "imported_unverified" for e in extensions if isinstance(e, dict)
        )
        entry = {
            "id": obs.get("id"),
            "status": obs.get("status"),
            "code": obs.get("code"),
            "verification": "unverified_import" if is_unverified else "chart_observation",
            "source_type": "Observation",
            "source_id": obs.get("id"),
        }
        if is_unverified:
            unverified.append(entry)
        else:
            verified.append(entry)
    return {
        "patient_id": patient_id,
        "verified_or_chart": verified,
        "imported_unverified": unverified,
        "note": "Unverified imports are separated and must not be treated as final verified labs.",
    }


def _support_ticket_summary(
    session: Session, *, tenant_id: str, ticket_id: str
) -> dict[str, Any]:
    ticket = session.execute(
        select(SupportTicket).where(
            SupportTicket.tenant_id == tenant_id, SupportTicket.id == ticket_id
        )
    ).scalar_one_or_none()
    if ticket is None:
        raise ApiError("TICKET_NOT_FOUND", "Support ticket not found.", 404)
    return {
        "ticket_id": ticket.id,
        "ticket_number": ticket.ticket_number,
        "category": ticket.category,
        "status": ticket.status,
        "subject": ticket.subject,
        "note": "Operational metadata only — no clinical chart access.",
    }


def _integration_transaction_status(
    session: Session, *, tenant_id: str, transaction_id: str
) -> dict[str, Any]:
    txn = session.execute(
        select(IntegrationTransaction).where(
            IntegrationTransaction.tenant_id == tenant_id,
            IntegrationTransaction.id == transaction_id,
        )
    ).scalar_one_or_none()
    if txn is None:
        raise ApiError("TRANSACTION_NOT_FOUND", "Integration transaction not found.", 404)
    return {
        "transaction_id": txn.id,
        "status": txn.status,
        "message_type": txn.message_type,
        "error_code": txn.error_code,
        "payload_summary": txn.payload_summary or {},
        "note": "Safe metadata — clinical payloads not exposed to agents by default.",
    }


READ_TOOLS: dict[str, dict[str, Any]] = {
    "patient.get_authorized_summary": {
        "risk": "low",
        "permission": "clinical_read",
        "approval_required": False,
        "roles": ("provider", "staff", "tenant_admin"),
        "handler": _patient_summary,
    },
    "patient.get_verified_observations": {
        "risk": "medium",
        "permission": "clinical_read",
        "approval_required": False,
        "roles": ("provider", "staff", "tenant_admin"),
        "handler": _verified_observations,
    },
    "support.get_ticket_summary": {
        "risk": "low",
        "permission": "support_read",
        "approval_required": False,
        "roles": ("tenant_admin", "staff", "provider"),
        "handler": _support_ticket_summary,
    },
    "integration.get_transaction_status": {
        "risk": "low",
        "permission": "integration_read",
        "approval_required": False,
        "roles": ("tenant_admin", "staff"),
        "handler": _integration_transaction_status,
    },
}

PROPOSAL_TOOLS: dict[str, dict[str, Any]] = {
    "clinical.propose_note_draft": {
        "risk": "high",
        "permission": "clinical_write_propose",
        "approval_required": True,
        "required_role": "provider",
        "roles": ("provider",),
    },
    "messaging.propose_patient_message": {
        "risk": "medium",
        "permission": "messaging_propose",
        "approval_required": True,
        "required_role": "provider",
        "roles": ("provider", "staff"),
    },
    "billing.propose_claim_correction": {
        "risk": "high",
        "permission": "billing_propose",
        "approval_required": True,
        "required_role": "staff",
        "roles": ("tenant_admin", "staff"),
    },
    "integration.propose_retry": {
        "risk": "medium",
        "permission": "integration_propose",
        "approval_required": True,
        "required_role": "tenant_admin",
        "roles": ("tenant_admin", "staff"),
    },
    "support.propose_response": {
        "risk": "medium",
        "permission": "support_propose",
        "approval_required": True,
        "required_role": "staff",
        "roles": ("tenant_admin", "staff"),
    },
    "scheduling.propose_appointment_change": {
        "risk": "medium",
        "permission": "scheduling_propose",
        "approval_required": True,
        "required_role": "staff",
        "roles": ("tenant_admin", "staff", "provider"),
    },
}


def assert_tool_allowed(tool_code: str) -> None:
    if tool_code in FORBIDDEN_AUTONOMOUS:
        raise ApiError(
            "TOOL_FORBIDDEN",
            "This tool is permanently blocked from autonomous agent execution.",
            403,
        )


def authorize_tool_role(membership: TenantMembership, tool_meta: dict[str, Any]) -> None:
    allowed = tool_meta.get("roles") or ()
    if membership.role not in allowed:
        raise ApiError("TOOL_ROLE_DENIED", "You are not authorized to invoke this tool.", 403)


def execute_read_tool(
    session: Session,
    *,
    tool_code: str,
    tenant_id: str,
    user: User,
    membership: TenantMembership,
    request_id: str,
    params: dict[str, Any],
) -> dict[str, Any]:
    assert_tool_allowed(tool_code)
    meta = READ_TOOLS.get(tool_code)
    if meta is None:
        raise ApiError("TOOL_NOT_FOUND", "Unknown or non-read tool.", 404)
    if not meta.get("handler"):
        raise ApiError("TOOL_NOT_EXECUTABLE", "Tool handler unavailable.", 500)
    authorize_tool_role(membership, meta)
    if membership.tenant_id != tenant_id:
        raise ApiError("TENANT_NOT_FOUND", "Tenant not found.", 404)
    handler: ToolHandler = meta["handler"]
    # Pass only declared params — never trust open kwargs from the model
    if tool_code.startswith("patient."):
        patient_id = str(params.get("patient_id") or "")
        if not patient_id:
            raise ApiError("PATIENT_REQUIRED", "patient_id is required.", 422)
        return handler(
            session,
            tenant_id=tenant_id,
            user=user,
            membership=membership,
            patient_id=patient_id,
            request_id=request_id,
        )
    if tool_code == "support.get_ticket_summary":
        return handler(session, tenant_id=tenant_id, ticket_id=str(params.get("ticket_id") or ""))
    if tool_code == "integration.get_transaction_status":
        return handler(
            session, tenant_id=tenant_id, transaction_id=str(params.get("transaction_id") or "")
        )
    raise ApiError("TOOL_NOT_EXECUTABLE", "No handler path.", 500)
