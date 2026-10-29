"""FHIR R4 facade routes under /api/v1/fhir/R4."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy.orm import Session

from app.audit import append_audit_event
from app.auth import ApiError, get_current_user
from app.authorization import require_membership, require_role
from app.consent_gate import require_patient_consent
from app.db import get_session
from app.fhir_store import (
    CLINICAL_TYPES,
    bundle_search,
    create_resource,
    ensure_patient_for_user,
    get_resource,
    patient_id_from_resource,
    search_resources,
    write_provenance,
)
from app.models import TenantMembership, User
from app.roles import CLINICIAN_READ_ROLES

router = APIRouter(prefix="/api/v1/fhir/R4", tags=["fhir"])

PATIENT_SCOPED = frozenset(
    {
        "Observation",
        "Condition",
        "MedicationStatement",
        "AllergyIntolerance",
        "Encounter",
        "Appointment",
        "Composition",
        "Task",
        "DocumentReference",
        "Consent",
    }
)


def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", "")


def _ensure_tenant(membership: TenantMembership, tenant_id: str) -> None:
    if membership.tenant_id != tenant_id:
        raise ApiError("TENANT_NOT_FOUND", "Tenant not found.", 404)


@router.post("/tenants/{tenant_id}/{resource_type}", status_code=201)
def create_fhir_resource(
    tenant_id: str,
    resource_type: str,
    body: dict[str, Any],
    request: Request,
    response: Response,
    user: User = Depends(get_current_user),
    membership: TenantMembership = Depends(require_membership),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    _ensure_tenant(membership, tenant_id)
    if resource_type not in CLINICAL_TYPES:
        raise ApiError("FHIR_TYPE_UNSUPPORTED", f"Unsupported type {resource_type}.", 422)
    response.headers["Cache-Control"] = "no-store"

    if resource_type == "Patient":
        if membership.role not in CLINICIAN_READ_ROLES | {"patient"}:
            raise ApiError("ROLE_REQUIRED", "You are not authorized for this action.", 403)
        if membership.role == "patient":
            body = {**body, "id": user.id}
        created = create_resource(
            session, tenant_id=tenant_id, resource_type="Patient", body=body
        )
    elif resource_type == "Consent":
        if membership.role != "patient":
            raise ApiError("ROLE_REQUIRED", "Patients grant consent.", 403)
        body = {
            **body,
            "patient": {"reference": f"Patient/{user.id}"},
            "status": body.get("status") or "active",
        }
        ensure_patient_for_user(session, tenant_id=tenant_id, user_id=user.id)
        created = create_resource(
            session, tenant_id=tenant_id, resource_type="Consent", body=body
        )
    elif resource_type in PATIENT_SCOPED - {"Consent"}:
        if membership.role not in CLINICIAN_READ_ROLES:
            raise ApiError("ROLE_REQUIRED", "Clinician role required.", 403)
        patient_id = patient_id_from_resource(resource_type, body)
        if not patient_id:
            raise ApiError("FHIR_PATIENT_REQUIRED", "subject/patient reference required.", 422)
        require_patient_consent(
            session,
            tenant_id=tenant_id,
            patient_id=patient_id,
            actor=user,
            membership=membership,
            request_id=_request_id(request),
            subject_type=resource_type,
        )
        created = create_resource(
            session, tenant_id=tenant_id, resource_type=resource_type, body=body
        )
        write_provenance(
            session,
            tenant_id=tenant_id,
            target_type=resource_type,
            target_id=created["id"],
            patient_id=patient_id,
            agent_user_id=user.id,
        )
    else:
        if membership.role not in CLINICIAN_READ_ROLES:
            raise ApiError("ROLE_REQUIRED", "You are not authorized for this action.", 403)
        created = create_resource(
            session, tenant_id=tenant_id, resource_type=resource_type, body=body
        )

    append_audit_event(
        session,
        actor_user_id=user.id,
        tenant_id=tenant_id,
        action=f"fhir.{resource_type}.create",
        subject_type=resource_type,
        subject_id=created["id"],
        request_id=_request_id(request),
    )
    return created


@router.get("/tenants/{tenant_id}/{resource_type}/{resource_id}")
def read_fhir_resource(
    tenant_id: str,
    resource_type: str,
    resource_id: str,
    request: Request,
    response: Response,
    user: User = Depends(get_current_user),
    membership: TenantMembership = Depends(require_membership),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    _ensure_tenant(membership, tenant_id)
    response.headers["Cache-Control"] = "no-store"
    resource = get_resource(
        session, tenant_id=tenant_id, resource_type=resource_type, resource_id=resource_id
    )
    if resource is None:
        raise ApiError("FHIR_NOT_FOUND", "Resource not found.", 404)

    patient_id = patient_id_from_resource(resource_type, resource)
    if resource_type in PATIENT_SCOPED or resource_type == "Patient":
        pid = patient_id or (resource_id if resource_type == "Patient" else None)
        if pid:
            require_patient_consent(
                session,
                tenant_id=tenant_id,
                patient_id=pid,
                actor=user,
                membership=membership,
                request_id=_request_id(request),
                subject_type=resource_type,
                subject_id=resource_id,
            )

    append_audit_event(
        session,
        actor_user_id=user.id,
        tenant_id=tenant_id,
        action=f"fhir.{resource_type}.read",
        subject_type=resource_type,
        subject_id=resource_id,
        request_id=_request_id(request),
    )
    return resource


@router.get("/tenants/{tenant_id}/{resource_type}")
def search_fhir_resources(
    tenant_id: str,
    resource_type: str,
    request: Request,
    response: Response,
    patient: str | None = Query(default=None, description="Patient id or Patient/id"),
    user: User = Depends(get_current_user),
    membership: TenantMembership = Depends(require_membership),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    _ensure_tenant(membership, tenant_id)
    response.headers["Cache-Control"] = "no-store"
    if resource_type not in CLINICAL_TYPES:
        raise ApiError("FHIR_TYPE_UNSUPPORTED", f"Unsupported type {resource_type}.", 422)

    patient_id = None
    if patient:
        patient_id = patient.split("/", 1)[-1] if "/" in patient else patient
        require_patient_consent(
            session,
            tenant_id=tenant_id,
            patient_id=patient_id,
            actor=user,
            membership=membership,
            request_id=_request_id(request),
            subject_type="Patient",
            subject_id=patient_id,
        )
    elif resource_type in PATIENT_SCOPED and membership.role in CLINICIAN_READ_ROLES:
        raise ApiError(
            "FHIR_PATIENT_REQUIRED",
            "patient search parameter is required for clinician chart queries.",
            422,
        )
    elif membership.role == "patient":
        patient_id = user.id

    resources = search_resources(
        session,
        tenant_id=tenant_id,
        resource_type=resource_type,
        patient_id=patient_id,
    )
    append_audit_event(
        session,
        actor_user_id=user.id,
        tenant_id=tenant_id,
        action=f"fhir.{resource_type}.search",
        subject_type=resource_type,
        subject_id=patient_id or tenant_id,
        request_id=_request_id(request),
    )
    return bundle_search(resources)


@router.post("/tenants/{tenant_id}/Patient/$ensure", status_code=200)
def ensure_my_patient(
    tenant_id: str,
    response: Response,
    user: User = Depends(get_current_user),
    membership: TenantMembership = Depends(require_role("patient")),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    _ensure_tenant(membership, tenant_id)
    response.headers["Cache-Control"] = "no-store"
    return ensure_patient_for_user(session, tenant_id=tenant_id, user_id=user.id)
