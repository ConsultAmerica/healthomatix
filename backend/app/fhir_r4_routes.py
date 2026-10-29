"""FHIR R4 read/search server surface with CapabilityStatement (V1.7).

Uses /api/v1/fhir/r4 to align with existing API prefix conventions.
Existing create/read facade remains at /api/v1/fhir/R4.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy.orm import Session

from app.audit import append_audit_event
from app.auth import ApiError, get_current_user
from app.authorization import require_membership
from app.consent_gate import require_patient_consent
from app.db import get_session
from app.fhir_mapper import resolve_location, resolve_organization, resolve_practitioner
from app.fhir_store import (
    FHIR_R4_READ_TYPES,
    FHIR_R4_SEARCH_TYPES,
    bundle_search,
    get_resource,
    patient_id_from_resource,
    search_resources,
)
from app.models import TenantMembership, User
from app.roles import CLINICIAN_READ_ROLES

router = APIRouter(prefix="/api/v1/fhir/r4", tags=["fhir-r4"])

PATIENT_SCOPED = frozenset(
    {
        "Observation",
        "DiagnosticReport",
        "Encounter",
        "Appointment",
        "DocumentReference",
        "Provenance",
        "Patient",
    }
)


def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", "")


def _ensure_tenant(membership: TenantMembership, tenant_id: str) -> None:
    if membership.tenant_id != tenant_id:
        raise ApiError("TENANT_NOT_FOUND", "Tenant not found.", 404)


def _capability_statement() -> dict[str, Any]:
    rest_resources = []
    for rtype in sorted(FHIR_R4_READ_TYPES):
        interactions = [{"code": "read"}]
        search_params = []
        if rtype in FHIR_R4_SEARCH_TYPES:
            interactions.append({"code": "search-type"})
            if rtype == "Patient":
                search_params = [{"name": "_id", "type": "token"}]
            else:
                search_params = [{"name": "patient", "type": "reference"}]
        rest_resources.append(
            {
                "type": rtype,
                "interaction": interactions,
                "searchParam": search_params,
            }
        )
    return {
        "resourceType": "CapabilityStatement",
        "status": "active",
        "date": "2026-10-29",
        "kind": "instance",
        "fhirVersion": "4.0.1",
        "format": ["json"],
        "software": {"name": "Healthomatix", "version": "1.7.0"},
        "implementation": {
            "description": "Healthomatix FHIR R4 read/search facade (tenant-scoped).",
            "url": "/api/v1/fhir/r4",
        },
        "rest": [
            {
                "mode": "server",
                "security": {
                    "cors": True,
                    "service": [
                        {
                            "coding": [
                                {
                                    "system": "http://terminology.hl7.org/CodeSystem/restful-security-service",
                                    "code": "OAuth",
                                }
                            ]
                        }
                    ],
                    "description": "Bearer auth via Healthomatix session/OIDC. Tenant + patient authorization enforced.",
                },
                "resource": rest_resources,
                "interaction": [{"code": "search-system", "documentation": "Not supported."}],
            }
        ],
    }


@router.get("/metadata")
def capability_statement(response: Response) -> dict[str, Any]:
    response.headers["Cache-Control"] = "no-store"
    return _capability_statement()


@router.get("/tenants/{tenant_id}/metadata")
def tenant_capability_statement(
    tenant_id: str,
    response: Response,
    membership: TenantMembership = Depends(require_membership),
) -> dict[str, Any]:
    _ensure_tenant(membership, tenant_id)
    response.headers["Cache-Control"] = "no-store"
    return _capability_statement()


@router.get("/tenants/{tenant_id}/{resource_type}/{resource_id}")
def read_resource(
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
    if resource_type not in FHIR_R4_READ_TYPES:
        raise ApiError(
            "FHIR_NOT_SUPPORTED",
            f"Resource type {resource_type} is not supported for read.",
            404,
        )

    resource: dict[str, Any] | None = None
    if resource_type == "Organization" and resource_id == tenant_id:
        resource = resolve_organization(session, tenant_id=tenant_id)
    elif resource_type == "Location":
        resource = resolve_location(session, tenant_id=tenant_id, location_id=resource_id)
    elif resource_type == "Practitioner":
        resource = resolve_practitioner(
            session, tenant_id=tenant_id, practitioner_id=resource_id
        )
    else:
        resource = get_resource(
            session, tenant_id=tenant_id, resource_type=resource_type, resource_id=resource_id
        )

    if resource is None:
        raise ApiError("FHIR_NOT_FOUND", "Resource not found.", 404)

    if resource_type in PATIENT_SCOPED:
        pid = patient_id_from_resource(resource_type, resource) or (
            resource_id if resource_type == "Patient" else None
        )
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
        action=f"fhir.r4.{resource_type}.read",
        subject_type=resource_type,
        subject_id=resource_id,
        request_id=_request_id(request),
    )
    return resource


@router.get("/tenants/{tenant_id}/{resource_type}")
def search_resource(
    tenant_id: str,
    resource_type: str,
    request: Request,
    response: Response,
    patient: str | None = Query(default=None),
    _id: str | None = Query(default=None, alias="_id"),
    user: User = Depends(get_current_user),
    membership: TenantMembership = Depends(require_membership),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    _ensure_tenant(membership, tenant_id)
    response.headers["Cache-Control"] = "no-store"
    if resource_type not in FHIR_R4_SEARCH_TYPES:
        raise ApiError(
            "FHIR_SEARCH_UNSUPPORTED",
            f"Search is not supported for {resource_type}. See CapabilityStatement.",
            400,
        )

    # Reject unknown search params silently? Spec says return appropriate errors.
    allowed = {"patient", "_id"} if resource_type == "Patient" else {"patient"}
    unknown = [k for k in request.query_params.keys() if k not in allowed and k != "_count"]
    if unknown:
        raise ApiError(
            "FHIR_SEARCH_PARAM_UNSUPPORTED",
            f"Unsupported search parameter(s): {', '.join(unknown)}",
            400,
        )

    patient_id = None
    if resource_type == "Patient" and _id:
        patient_id = _id
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
        resource = get_resource(
            session, tenant_id=tenant_id, resource_type="Patient", resource_id=patient_id
        )
        resources = [resource] if resource else []
    else:
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
        elif resource_type in PATIENT_SCOPED - {"Patient"} and membership.role in CLINICIAN_READ_ROLES:
            raise ApiError(
                "FHIR_PATIENT_REQUIRED",
                "patient search parameter is required.",
                422,
            )
        elif membership.role == "patient":
            patient_id = user.id
        if resource_type == "Patient" and membership.role == "patient":
            resource = get_resource(
                session, tenant_id=tenant_id, resource_type="Patient", resource_id=user.id
            )
            resources = [resource] if resource else []
        else:
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
        action=f"fhir.r4.{resource_type}.search",
        subject_type=resource_type,
        subject_id=patient_id or tenant_id,
        request_id=_request_id(request),
    )
    return bundle_search(resources)
