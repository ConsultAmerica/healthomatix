"""V2.1.1 clinical context — authorized retrieval from existing clinical SoT (no second DB)."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.agent_models import AiClinicalContextAccessEvent, AiEvidenceReference
from app.agent_tools import execute_read_tool
from app.audit import append_audit_event
from app.auth import ApiError
from app.authorization import require_clinic_patient
from app.consent_gate import require_patient_consent
from app.fhir_store import get_resource, search_resources
from app.models import TenantMembership, User, utcnow


def _record_access(
    session: Session,
    *,
    organization_id: str,
    actor_id: str,
    patient_id: str | None,
    encounter_id: str | None,
    agent_run_id: str | None,
    resource_category: str,
    access_outcome: str,
) -> None:
    session.add(
        AiClinicalContextAccessEvent(
            organization_id=organization_id,
            actor_id=actor_id,
            patient_id=patient_id,
            encounter_id=encounter_id,
            agent_run_id=agent_run_id,
            resource_category=resource_category,
            access_outcome=access_outcome,
            policy_reference="2.1.1",
        )
    )


def _persist_evidence(
    session: Session,
    *,
    organization_id: str,
    agent_run_id: str | None,
    patient_id: str | None,
    source_type: str,
    source_resource_id: str,
    verification_status: str,
    source_location: str = "",
    source_version: str = "1",
) -> AiEvidenceReference:
    row = AiEvidenceReference(
        organization_id=organization_id,
        agent_run_id=agent_run_id,
        patient_id=patient_id,
        source_type=source_type,
        source_resource_id=source_resource_id,
        source_version=source_version,
        source_location=source_location,
        verification_status=verification_status,
    )
    session.add(row)
    session.flush()
    return row


def get_authorized_patient_context(
    session: Session,
    *,
    tenant_id: str,
    patient_id: str,
    user: User,
    membership: TenantMembership,
    request_id: str = "",
    agent_run_id: str | None = None,
    encounter_id: str | None = None,
) -> dict[str, Any]:
    if membership.tenant_id != tenant_id:
        _record_access(
            session,
            organization_id=tenant_id,
            actor_id=user.id,
            patient_id=patient_id,
            encounter_id=encounter_id,
            agent_run_id=agent_run_id,
            resource_category="patient",
            access_outcome="denied_tenant",
        )
        raise ApiError("TENANT_NOT_FOUND", "Tenant not found.", 404)

    try:
        require_clinic_patient(session, tenant_id=tenant_id, user_id=patient_id)
        require_patient_consent(
            session,
            tenant_id=tenant_id,
            patient_id=patient_id,
            actor=user,
            membership=membership,
            request_id=request_id,
        )
    except ApiError as exc:
        _record_access(
            session,
            organization_id=tenant_id,
            actor_id=user.id,
            patient_id=patient_id,
            encounter_id=encounter_id,
            agent_run_id=agent_run_id,
            resource_category="patient",
            access_outcome=f"denied_{exc.code.lower()}",
        )
        raise

    summary = execute_read_tool(
        session,
        tool_code="patient.get_authorized_summary",
        tenant_id=tenant_id,
        user=user,
        membership=membership,
        request_id=request_id,
        params={"patient_id": patient_id},
    )
    obs = execute_read_tool(
        session,
        tool_code="patient.get_verified_observations",
        tenant_id=tenant_id,
        user=user,
        membership=membership,
        request_id=request_id,
        params={"patient_id": patient_id},
    )

    observations: list[dict[str, Any]] = []
    evidence: list[dict[str, Any]] = []
    warnings: list[str] = []

    for item in obs.get("verified_or_chart") or []:
        status = item.get("verification") or "clinician_authored"
        mapped = "verified" if status == "chart_observation" else "clinician_authored"
        ref = _persist_evidence(
            session,
            organization_id=tenant_id,
            agent_run_id=agent_run_id,
            patient_id=patient_id,
            source_type="Observation",
            source_resource_id=str(item.get("id") or ""),
            verification_status=mapped,
            source_location="Observation.code",
        )
        observations.append(
            {
                "observation_reference": item.get("id"),
                "display": (item.get("code") or {}).get("text")
                if isinstance(item.get("code"), dict)
                else str(item.get("code") or "Observation"),
                "verification_status": mapped,
                "source_reference": ref.id,
                "value": None,
                "unit": None,
            }
        )
        evidence.append(
            {
                "evidence_id": ref.id,
                "source_type": "Observation",
                "source_resource_id": ref.source_resource_id,
                "verification_status": mapped,
            }
        )

    for item in obs.get("imported_unverified") or []:
        ref = _persist_evidence(
            session,
            organization_id=tenant_id,
            agent_run_id=agent_run_id,
            patient_id=patient_id,
            source_type="Observation",
            source_resource_id=str(item.get("id") or ""),
            verification_status="imported_pending_review",
            source_location="Observation.extension",
        )
        observations.append(
            {
                "observation_reference": item.get("id"),
                "display": "Imported observation",
                "verification_status": "imported_pending_review",
                "source_reference": ref.id,
                "value": None,
                "unit": None,
            }
        )
        warnings.append(
            f"Observation {item.get('id')} is imported pending review — not treated as verified."
        )
        evidence.append(
            {
                "evidence_id": ref.id,
                "source_type": "Observation",
                "source_resource_id": ref.source_resource_id,
                "verification_status": "imported_pending_review",
            }
        )

    # Document references (metadata only)
    docs = search_resources(
        session, tenant_id=tenant_id, resource_type="DocumentReference", patient_id=patient_id, limit=10
    )
    document_refs = []
    for doc in docs:
        document_refs.append(
            {
                "document_reference": doc.get("id"),
                "status": doc.get("status"),
                "verification_status": "authorized_reference",
            }
        )

    # Encounter if requested and present
    encounter_payload = None
    if encounter_id:
        enc = get_resource(
            session, tenant_id=tenant_id, resource_type="Encounter", resource_id=encounter_id
        )
        if enc is None:
            warnings.append("Requested encounter was not found; context continues without it.")
        else:
            encounter_payload = {
                "encounter_reference": encounter_id,
                "status": enc.get("status"),
                "verification_status": "clinician_authored",
            }

    if not observations:
        warnings.append("No laboratory observations available for this patient in authorized scope.")

    _record_access(
        session,
        organization_id=tenant_id,
        actor_id=user.id,
        patient_id=patient_id,
        encounter_id=encounter_id,
        agent_run_id=agent_run_id,
        resource_category="clinical_context",
        access_outcome="allowed",
    )
    append_audit_event(
        session,
        actor_user_id=user.id,
        tenant_id=tenant_id,
        action="ai.clinical_context_read",
        subject_type="Patient",
        subject_id=patient_id,
        request_id=request_id,
    )
    session.flush()

    return {
        "patient_reference": patient_id,
        "encounter_reference": encounter_id,
        "context_status": "complete" if summary.get("resource_present") else "partial",
        "demographics": {
            "resource_present": summary.get("resource_present"),
            "note": summary.get("note"),
        },
        "observations": observations,
        "documents": document_refs,
        "encounter": encounter_payload,
        "evidence": evidence,
        "warnings": warnings,
        "retrieved_at": utcnow().isoformat(),
        "note": "Missing clinical facts remain missing — nothing was invented.",
    }


def list_run_evidence(
    session: Session, *, tenant_id: str, agent_run_id: str
) -> list[dict[str, Any]]:
    from sqlalchemy import select

    rows = session.execute(
        select(AiEvidenceReference).where(
            AiEvidenceReference.organization_id == tenant_id,
            AiEvidenceReference.agent_run_id == agent_run_id,
        )
    ).scalars()
    return [
        {
            "evidence_id": r.id,
            "source_type": r.source_type,
            "source_resource_id": r.source_resource_id,
            "source_version": r.source_version,
            "source_location": r.source_location,
            "verification_status": r.verification_status,
            "patient_id": r.patient_id,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]
