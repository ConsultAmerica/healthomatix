"""V1.7 integration hub, HL7 lab ingest, identity, terminology, export/import."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from fastapi import APIRouter, Depends, Request, Response
from pydantic import Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.audit import append_audit_event
from app.auth import ApiError, get_current_user
from app.authorization import require_role
from app.consent_gate import require_patient_consent
from app.db import get_session
from app.fhir_store import create_resource, get_resource, search_resources, update_resource, write_provenance
from app.integrations.ehr_port import build_ehr_client
from app.integrations.hl7_port import build_hl7_lab_adapter
from app.interop_models import (
    ClinicalImportBatch,
    ClinicalImportItem,
    DataExchangeAuditEvent,
    IntegrationConnection,
    IntegrationJob,
    IntegrationTransaction,
    PatientDataExport,
    PatientIdentityLink,
    TerminologyMapping,
)
from app.models import TenantMembership, User, utcnow
from app.schemas import StrictModel

router = APIRouter(prefix="/api/v1", tags=["interop"])


class ConnectionWrite(StrictModel):
    connection_name: str = Field(min_length=2, max_length=120)
    integration_type: str = Field(pattern="^(fhir_ehr|hl7_lab|file_import)$")
    external_system: str = Field(min_length=2, max_length=120)
    base_url: str = Field(default="", max_length=512)
    authentication_type: str = Field(default="sandbox", max_length=32)
    authorized_scopes: list[str] = Field(default_factory=list)


class ConnectionRead(StrictModel):
    connection_id: str
    connection_name: str
    integration_type: str
    external_system: str
    base_url: str
    fhir_version: str
    authentication_type: str
    status: str
    authorized_scopes: list[str]
    last_success_at: str | None = None
    last_error: str


class Hl7IngestWrite(StrictModel):
    connection_id: str = Field(min_length=36, max_length=36)
    message: str = Field(min_length=10, max_length=20000)
    local_patient_id: str | None = Field(default=None, min_length=36, max_length=36)


class IdentityResolveWrite(StrictModel):
    patient_id: str = Field(min_length=36, max_length=36)
    verification_status: str = Field(pattern="^(confirmed|rejected)$")


class TerminologyWrite(StrictModel):
    source_system: str = Field(min_length=2, max_length=120)
    source_code: str = Field(min_length=1, max_length=64)
    source_display: str = Field(default="", max_length=200)
    target_system: str = Field(min_length=2, max_length=120)
    target_code: str = Field(min_length=1, max_length=64)
    mapping_version: str = Field(default="1", max_length=32)


class ImportCreateWrite(StrictModel):
    connection_id: str = Field(min_length=36, max_length=36)
    patient_family: str = Field(default="Demo", max_length=80)
    local_patient_id: str = Field(min_length=36, max_length=36)


def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", "")


def _exchange_audit(
    session: Session,
    *,
    tenant_id: str,
    actor_id: str | None,
    action: str,
    patient_id: str | None = None,
    connection_id: str | None = None,
    resource_type: str = "",
    resource_reference: str = "",
    outcome: str = "success",
    purpose_reference: str = "",
) -> None:
    session.add(
        DataExchangeAuditEvent(
            tenant_id=tenant_id,
            actor_user_id=actor_id,
            patient_id=patient_id,
            connection_id=connection_id,
            action=action,
            resource_type=resource_type,
            resource_reference=resource_reference,
            outcome=outcome,
            purpose_reference=purpose_reference,
        )
    )


def _conn_read(row: IntegrationConnection) -> ConnectionRead:
    return ConnectionRead(
        connection_id=row.id,
        connection_name=row.connection_name,
        integration_type=row.integration_type,
        external_system=row.external_system,
        base_url=row.base_url,
        fhir_version=row.fhir_version,
        authentication_type=row.authentication_type,
        status=row.status,
        authorized_scopes=list(row.authorized_scopes or []),
        last_success_at=row.last_success_at.isoformat() if row.last_success_at else None,
        last_error=row.last_error,
    )


@router.get("/tenants/{tenant_id}/integrations/connections", response_model=list[ConnectionRead])
def list_connections(
    tenant_id: str,
    response: Response,
    user: User = Depends(get_current_user),
    membership: TenantMembership = Depends(require_role("tenant_admin", "staff")),
    session: Session = Depends(get_session),
) -> list[ConnectionRead]:
    if membership.tenant_id != tenant_id:
        raise ApiError("TENANT_NOT_FOUND", "Tenant not found.", 404)
    rows = session.execute(
        select(IntegrationConnection)
        .where(IntegrationConnection.tenant_id == tenant_id)
        .order_by(IntegrationConnection.created_at.desc())
    ).scalars()
    response.headers["Cache-Control"] = "no-store"
    return [_conn_read(row) for row in rows]


@router.post(
    "/tenants/{tenant_id}/integrations/connections",
    response_model=ConnectionRead,
    status_code=201,
)
def create_connection(
    tenant_id: str,
    body: ConnectionWrite,
    request: Request,
    response: Response,
    user: User = Depends(get_current_user),
    membership: TenantMembership = Depends(require_role("tenant_admin")),
    session: Session = Depends(get_session),
) -> ConnectionRead:
    if membership.tenant_id != tenant_id:
        raise ApiError("TENANT_NOT_FOUND", "Tenant not found.", 404)
    row = IntegrationConnection(
        tenant_id=tenant_id,
        connection_name=body.connection_name,
        integration_type=body.integration_type,
        external_system=body.external_system,
        base_url=body.base_url,
        authentication_type=body.authentication_type,
        authorized_scopes=body.authorized_scopes,
        secret_reference="",  # never expose secrets via API
        status="configured",
    )
    session.add(row)
    session.flush()
    append_audit_event(
        session,
        actor_user_id=user.id,
        tenant_id=tenant_id,
        action="integration.connection_created",
        subject_type="IntegrationConnection",
        subject_id=row.id,
        request_id=_request_id(request),
    )
    response.headers["Cache-Control"] = "no-store"
    return _conn_read(row)


@router.post(
    "/tenants/{tenant_id}/integrations/connections/{connection_id}/test",
    response_model=dict[str, Any],
)
def test_connection(
    tenant_id: str,
    connection_id: str,
    response: Response,
    user: User = Depends(get_current_user),
    membership: TenantMembership = Depends(require_role("tenant_admin", "staff")),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    if membership.tenant_id != tenant_id:
        raise ApiError("TENANT_NOT_FOUND", "Tenant not found.", 404)
    row = session.execute(
        select(IntegrationConnection).where(
            IntegrationConnection.tenant_id == tenant_id,
            IntegrationConnection.id == connection_id,
        )
    ).scalar_one_or_none()
    if row is None:
        raise ApiError("CONNECTION_NOT_FOUND", "Connection not found.", 404)
    client = build_ehr_client()
    caps = client.discover_capabilities(base_url=row.base_url or "https://sandbox.example/fhir")
    auth = client.authorize_sandbox(scopes=list(row.authorized_scopes or []))
    row.status = "active"
    row.last_success_at = utcnow()
    row.last_error = ""
    row.secret_reference = auth.token_reference  # opaque reference only
    row.fhir_version = caps.fhir_version
    session.flush()
    response.headers["Cache-Control"] = "no-store"
    return {
        "status": "ok",
        "fhir_version": caps.fhir_version,
        "resources": caps.resources,
        "smart_modes": caps.smart_modes,
        "authorized_scopes": auth.scopes,
        "token_reference_present": bool(auth.token_reference),
        "note": "Sandbox capability discovery — no real SMART tokens returned to clients.",
    }


@router.post("/tenants/{tenant_id}/integrations/hl7/oru", response_model=dict[str, Any], status_code=201)
def ingest_oru(
    tenant_id: str,
    body: Hl7IngestWrite,
    request: Request,
    response: Response,
    user: User = Depends(get_current_user),
    membership: TenantMembership = Depends(require_role("tenant_admin", "staff", "provider")),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    if membership.tenant_id != tenant_id:
        raise ApiError("TENANT_NOT_FOUND", "Tenant not found.", 404)
    conn = session.execute(
        select(IntegrationConnection).where(
            IntegrationConnection.tenant_id == tenant_id,
            IntegrationConnection.id == body.connection_id,
        )
    ).scalar_one_or_none()
    if conn is None or conn.integration_type != "hl7_lab":
        raise ApiError("CONNECTION_NOT_FOUND", "HL7 lab connection not found.", 404)

    try:
        parsed = build_hl7_lab_adapter().parse_oru_r01(body.message)
    except ValueError as exc:
        raise ApiError("HL7_INVALID", str(exc), 422) from exc

    dup = session.execute(
        select(IntegrationTransaction).where(
            IntegrationTransaction.tenant_id == tenant_id,
            IntegrationTransaction.connection_id == conn.id,
            IntegrationTransaction.external_message_id == parsed.external_message_id,
        )
    ).scalar_one_or_none()
    if dup is not None:
        response.headers["Cache-Control"] = "no-store"
        return {
            "transaction_id": dup.id,
            "status": dup.status,
            "duplicate": True,
            "note": "Idempotent replay — existing transaction returned; observation not recreated.",
        }

    txn = IntegrationTransaction(
        tenant_id=tenant_id,
        connection_id=conn.id,
        direction="inbound",
        message_type="ORU^R01",
        external_message_id=parsed.external_message_id,
        correlation_id=parsed.order_id or parsed.external_message_id,
        status="validating",
        payload_reference=f"sandbox://hl7/{parsed.external_message_id}",
        payload_summary={
            "patient_external_id": parsed.patient_external_id,
            "test_code": parsed.test_code,
            "result_status": parsed.result_status,
            "segments": parsed.raw_summary.get("segments"),
        },
    )
    session.add(txn)
    session.flush()

    # Identity resolution — never auto-merge on name alone
    link = session.execute(
        select(PatientIdentityLink).where(
            PatientIdentityLink.tenant_id == tenant_id,
            PatientIdentityLink.external_system == conn.external_system,
            PatientIdentityLink.external_identifier == parsed.patient_external_id,
        )
    ).scalar_one_or_none()
    patient_id = body.local_patient_id
    if link and link.verification_status == "confirmed" and link.patient_id:
        patient_id = link.patient_id
    elif patient_id:
        if link is None:
            link = PatientIdentityLink(
                tenant_id=tenant_id,
                patient_id=None,
                external_system=conn.external_system,
                external_identifier=parsed.patient_external_id,
                assigning_authority=conn.external_system,
                verification_status="manual_review",
                match_evidence={
                    "external_name": parsed.patient_name,
                    "proposed_patient_id": patient_id,
                    "note": "Requires authorized confirmation before merge.",
                },
            )
            session.add(link)
            session.flush()
        txn.status = "awaiting_review"
        session.add(
            IntegrationJob(
                tenant_id=tenant_id,
                transaction_id=txn.id,
                job_type="identity_review",
                status="queued",
            )
        )
        session.flush()
        response.headers["Cache-Control"] = "no-store"
        return {
            "transaction_id": txn.id,
            "status": txn.status,
            "identity_link_id": link.id,
            "verification_status": link.verification_status,
            "parsed": {
                "test_code": parsed.test_code,
                "value": parsed.value,
                "result_status": parsed.result_status,
            },
            "note": "Patient identity requires manual confirmation before clinical import.",
        }
    else:
        txn.status = "awaiting_review"
        if link is None:
            link = PatientIdentityLink(
                tenant_id=tenant_id,
                external_system=conn.external_system,
                external_identifier=parsed.patient_external_id,
                assigning_authority=conn.external_system,
                verification_status="manual_review",
                match_evidence={"external_name": parsed.patient_name},
            )
            session.add(link)
            session.flush()
        response.headers["Cache-Control"] = "no-store"
        return {
            "transaction_id": txn.id,
            "status": txn.status,
            "identity_link_id": link.id,
            "note": "No local patient supplied; manual identity resolution required.",
        }

    # Confirmed path — create draft observation pending clinical verification policy
    require_patient_consent(
        session,
        tenant_id=tenant_id,
        patient_id=patient_id,
        actor=user,
        membership=membership,
        request_id=_request_id(request),
    )
    # Map terminology if approved mapping exists; otherwise keep source code
    mapping = session.execute(
        select(TerminologyMapping).where(
            TerminologyMapping.source_system == conn.external_system,
            TerminologyMapping.source_code == parsed.test_code,
            TerminologyMapping.status == "approved",
        )
    ).scalar_one_or_none()
    code_system = mapping.target_system if mapping else "urn:sandbox:lab"
    code_value = mapping.target_code if mapping else parsed.test_code

    obs_status = {
        "preliminary": "preliminary",
        "final": "final",
        "corrected": "corrected",
        "cancelled": "cancelled",
    }.get(parsed.result_status, "final")

    # Do NOT mark as clinically verified merely because HL7 parsed
    observation = create_resource(
        session,
        tenant_id=tenant_id,
        resource_type="Observation",
        body={
            "resourceType": "Observation",
            "status": obs_status,
            "category": [
                {
                    "coding": [
                        {
                            "system": "http://terminology.hl7.org/CodeSystem/observation-category",
                            "code": "laboratory",
                        }
                    ]
                }
            ],
            "code": {
                "coding": [{"system": code_system, "code": code_value, "display": parsed.test_name}],
                "text": parsed.test_name,
            },
            "subject": {"reference": f"Patient/{patient_id}"},
            "effectiveDateTime": parsed.observation_datetime or None,
            "valueQuantity": {
                "value": float(parsed.value) if parsed.value.replace(".", "", 1).isdigit() else None,
                "unit": parsed.unit,
            }
            if parsed.value
            else {"valueString": parsed.value},
            "interpretation": (
                [{"text": parsed.abnormal_flag}] if parsed.abnormal_flag else []
            ),
            "referenceRange": (
                [{"text": parsed.reference_range}] if parsed.reference_range else []
            ),
            "extension": [
                {
                    "url": "urn:healthomatix:verification",
                    "valueString": "imported_unverified",
                },
                {
                    "url": "urn:healthomatix:source-message",
                    "valueString": parsed.external_message_id,
                },
            ],
        },
    )
    if isinstance(observation.get("valueQuantity"), dict) and observation["valueQuantity"].get("value") is None:
        observation["valueString"] = parsed.value
        observation.pop("valueQuantity", None)
        update_resource(
            session,
            tenant_id=tenant_id,
            resource_type="Observation",
            resource_id=observation["id"],
            body=observation,
        )

    write_provenance(
        session,
        tenant_id=tenant_id,
        target_type="Observation",
        target_id=observation["id"],
        patient_id=patient_id,
        agent_user_id=user.id,
        activity_code="CREATE",
        entity_refs=[("IntegrationTransaction", txn.id)],
    )
    txn.status = "processed"
    txn.processed_at = utcnow()
    conn.last_success_at = utcnow()
    session.add(
        IntegrationJob(
            tenant_id=tenant_id,
            transaction_id=txn.id,
            job_type="hl7_oru_import",
            status="completed",
            attempt_count=1,
            completed_at=utcnow(),
        )
    )
    _exchange_audit(
        session,
        tenant_id=tenant_id,
        actor_id=user.id,
        action="hl7.oru.imported",
        patient_id=patient_id,
        connection_id=conn.id,
        resource_type="Observation",
        resource_reference=f"Observation/{observation['id']}",
        purpose_reference="laboratory_result_exchange",
    )
    session.flush()
    response.headers["Cache-Control"] = "no-store"
    return {
        "transaction_id": txn.id,
        "status": txn.status,
        "observation_id": observation["id"],
        "verification": "imported_unverified",
        "note": "Imported laboratory Observation is not auto-verified clinical truth.",
        "duplicate": False,
    }


@router.get("/tenants/{tenant_id}/integrations/patient-matches", response_model=list[dict[str, Any]])
def list_patient_matches(
    tenant_id: str,
    response: Response,
    user: User = Depends(get_current_user),
    membership: TenantMembership = Depends(require_role("tenant_admin", "staff", "provider")),
    session: Session = Depends(get_session),
) -> list[dict[str, Any]]:
    if membership.tenant_id != tenant_id:
        raise ApiError("TENANT_NOT_FOUND", "Tenant not found.", 404)
    rows = session.execute(
        select(PatientIdentityLink)
        .where(
            PatientIdentityLink.tenant_id == tenant_id,
            PatientIdentityLink.verification_status.in_(("manual_review", "possible", "conflict")),
        )
        .order_by(PatientIdentityLink.created_at.desc())
        .limit(50)
    ).scalars()
    response.headers["Cache-Control"] = "no-store"
    return [
        {
            "link_id": row.id,
            "patient_id": row.patient_id,
            "external_system": row.external_system,
            "external_identifier": row.external_identifier,
            "verification_status": row.verification_status,
            "match_evidence": row.match_evidence or {},
        }
        for row in rows
    ]


@router.post(
    "/tenants/{tenant_id}/integrations/patient-matches/{link_id}/resolve",
    response_model=dict[str, Any],
)
def resolve_patient_match(
    tenant_id: str,
    link_id: str,
    body: IdentityResolveWrite,
    request: Request,
    response: Response,
    user: User = Depends(get_current_user),
    membership: TenantMembership = Depends(require_role("tenant_admin", "staff")),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    if membership.tenant_id != tenant_id:
        raise ApiError("TENANT_NOT_FOUND", "Tenant not found.", 404)
    link = session.execute(
        select(PatientIdentityLink).where(
            PatientIdentityLink.tenant_id == tenant_id, PatientIdentityLink.id == link_id
        )
    ).scalar_one_or_none()
    if link is None:
        raise ApiError("LINK_NOT_FOUND", "Identity link not found.", 404)
    if body.verification_status == "confirmed":
        link.patient_id = body.patient_id
        link.verification_status = "confirmed"
    else:
        link.verification_status = "no_match"
    link.verified_by_user_id = user.id
    link.verified_at = utcnow()
    session.flush()
    append_audit_event(
        session,
        actor_user_id=user.id,
        tenant_id=tenant_id,
        action="integration.identity_resolved",
        subject_type="PatientIdentityLink",
        subject_id=link.id,
        request_id=_request_id(request),
    )
    response.headers["Cache-Control"] = "no-store"
    return {
        "link_id": link.id,
        "verification_status": link.verification_status,
        "patient_id": link.patient_id,
    }


@router.get("/tenants/{tenant_id}/integrations/terminology/mappings", response_model=list[dict[str, Any]])
def list_terminology_mappings(
    tenant_id: str,
    response: Response,
    user: User = Depends(get_current_user),
    membership: TenantMembership = Depends(require_role("tenant_admin", "staff", "provider")),
    session: Session = Depends(get_session),
) -> list[dict[str, Any]]:
    if membership.tenant_id != tenant_id:
        raise ApiError("TENANT_NOT_FOUND", "Tenant not found.", 404)
    rows = session.execute(
        select(TerminologyMapping).order_by(TerminologyMapping.created_at.desc()).limit(100)
    ).scalars()
    response.headers["Cache-Control"] = "no-store"
    return [
        {
            "mapping_id": row.id,
            "source_system": row.source_system,
            "source_code": row.source_code,
            "source_display": row.source_display,
            "target_system": row.target_system,
            "target_code": row.target_code,
            "mapping_version": row.mapping_version,
            "status": row.status,
        }
        for row in rows
    ]


@router.post(
    "/tenants/{tenant_id}/integrations/terminology/mappings",
    response_model=dict[str, Any],
    status_code=201,
)
def create_terminology_mapping(
    tenant_id: str,
    body: TerminologyWrite,
    response: Response,
    user: User = Depends(get_current_user),
    membership: TenantMembership = Depends(require_role("tenant_admin", "staff")),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    if membership.tenant_id != tenant_id:
        raise ApiError("TENANT_NOT_FOUND", "Tenant not found.", 404)
    row = TerminologyMapping(
        source_system=body.source_system,
        source_code=body.source_code,
        source_display=body.source_display,
        target_system=body.target_system,
        target_code=body.target_code,
        mapping_version=body.mapping_version,
        status="pending_review",
    )
    session.add(row)
    session.flush()
    response.headers["Cache-Control"] = "no-store"
    return {
        "mapping_id": row.id,
        "status": row.status,
        "source_code": row.source_code,
        "target_code": row.target_code,
    }


@router.post(
    "/tenants/{tenant_id}/integrations/terminology/mappings/{mapping_id}/approve",
    response_model=dict[str, Any],
)
def approve_terminology_mapping(
    tenant_id: str,
    mapping_id: str,
    response: Response,
    user: User = Depends(get_current_user),
    membership: TenantMembership = Depends(require_role("tenant_admin")),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    if membership.tenant_id != tenant_id:
        raise ApiError("TENANT_NOT_FOUND", "Tenant not found.", 404)
    row = session.get(TerminologyMapping, mapping_id)
    if row is None:
        raise ApiError("MAPPING_NOT_FOUND", "Terminology mapping not found.", 404)
    row.status = "approved"
    row.reviewed_by_user_id = user.id
    row.reviewed_at = utcnow()
    session.flush()
    response.headers["Cache-Control"] = "no-store"
    return {"mapping_id": row.id, "status": row.status}


@router.post(
    "/tenants/{tenant_id}/patients/{patient_id}/export",
    response_model=dict[str, Any],
    status_code=201,
)
def export_patient_data(
    tenant_id: str,
    patient_id: str,
    request: Request,
    response: Response,
    user: User = Depends(get_current_user),
    membership: TenantMembership = Depends(require_role("patient", "tenant_admin", "staff", "provider")),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    if membership.tenant_id != tenant_id:
        raise ApiError("TENANT_NOT_FOUND", "Tenant not found.", 404)
    if membership.role == "patient" and user.id != patient_id:
        raise ApiError("PATIENT_NOT_FOUND", "Patient not found.", 404)
    require_patient_consent(
        session,
        tenant_id=tenant_id,
        patient_id=patient_id,
        actor=user,
        membership=membership,
        request_id=_request_id(request),
    )
    entries: list[dict[str, Any]] = []
    patient = get_resource(
        session, tenant_id=tenant_id, resource_type="Patient", resource_id=patient_id
    )
    if patient:
        entries.append({"resource": patient})
    for rtype in ("Observation", "Encounter", "Appointment", "DocumentReference", "Provenance"):
        for resource in search_resources(
            session, tenant_id=tenant_id, resource_type=rtype, patient_id=patient_id, limit=100
        ):
            # Skip unverified imported labs from being labeled as verified in export metadata
            entries.append({"resource": resource})
    bundle = {
        "resourceType": "Bundle",
        "type": "collection",
        "timestamp": utcnow().isoformat().replace("+00:00", "Z"),
        "entry": entries,
        "meta": {
            "tag": [
                {
                    "system": "urn:healthomatix:export",
                    "code": "patient-authorized",
                    "display": "Authorized patient data export (supported resources only)",
                }
            ]
        },
    }
    export = PatientDataExport(
        tenant_id=tenant_id,
        patient_id=patient_id,
        requested_by_user_id=user.id,
        status="ready",
        format="fhir_r4_bundle",
        bundle_json=bundle,
        expires_at=utcnow() + timedelta(hours=24),
    )
    session.add(export)
    session.flush()
    _exchange_audit(
        session,
        tenant_id=tenant_id,
        actor_id=user.id,
        action="patient.export.created",
        patient_id=patient_id,
        resource_type="Bundle",
        resource_reference=f"PatientDataExport/{export.id}",
        purpose_reference="patient_portability",
    )
    response.headers["Cache-Control"] = "no-store"
    return {
        "export_id": export.id,
        "status": export.status,
        "format": export.format,
        "entry_count": len(entries),
        "expires_at": export.expires_at.isoformat() if export.expires_at else None,
        "note": "Not FHIR Bulk Data ($export) — authorized Bundle collection download.",
    }


@router.get("/tenants/{tenant_id}/patients/{patient_id}/exports/{export_id}")
def download_export(
    tenant_id: str,
    patient_id: str,
    export_id: str,
    request: Request,
    response: Response,
    user: User = Depends(get_current_user),
    membership: TenantMembership = Depends(require_role("patient", "tenant_admin", "staff", "provider")),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    if membership.tenant_id != tenant_id:
        raise ApiError("TENANT_NOT_FOUND", "Tenant not found.", 404)
    if membership.role == "patient" and user.id != patient_id:
        raise ApiError("PATIENT_NOT_FOUND", "Patient not found.", 404)
    export = session.execute(
        select(PatientDataExport).where(
            PatientDataExport.tenant_id == tenant_id,
            PatientDataExport.patient_id == patient_id,
            PatientDataExport.id == export_id,
        )
    ).scalar_one_or_none()
    if export is None:
        raise ApiError("EXPORT_NOT_FOUND", "Export not found.", 404)
    if export.expires_at is not None:
        expires = export.expires_at
        now = utcnow()
        # SQLite may return naive datetimes; normalize before compare.
        if expires.tzinfo is None and now.tzinfo is not None:
            expires = expires.replace(tzinfo=now.tzinfo)
        elif expires.tzinfo is not None and now.tzinfo is None:
            now = now.replace(tzinfo=expires.tzinfo)
        if expires < now:
            raise ApiError("EXPORT_EXPIRED", "Export has expired.", 410)
    require_patient_consent(
        session,
        tenant_id=tenant_id,
        patient_id=patient_id,
        actor=user,
        membership=membership,
        request_id=_request_id(request),
    )
    response.headers["Cache-Control"] = "no-store"
    return export.bundle_json


@router.post(
    "/tenants/{tenant_id}/integrations/imports",
    response_model=dict[str, Any],
    status_code=201,
)
def create_import_preview(
    tenant_id: str,
    body: ImportCreateWrite,
    request: Request,
    response: Response,
    user: User = Depends(get_current_user),
    membership: TenantMembership = Depends(require_role("tenant_admin", "staff")),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    if membership.tenant_id != tenant_id:
        raise ApiError("TENANT_NOT_FOUND", "Tenant not found.", 404)
    conn = session.execute(
        select(IntegrationConnection).where(
            IntegrationConnection.tenant_id == tenant_id,
            IntegrationConnection.id == body.connection_id,
        )
    ).scalar_one_or_none()
    if conn is None:
        raise ApiError("CONNECTION_NOT_FOUND", "Connection not found.", 404)
    require_patient_consent(
        session,
        tenant_id=tenant_id,
        patient_id=body.local_patient_id,
        actor=user,
        membership=membership,
        request_id=_request_id(request),
    )
    client = build_ehr_client()
    patients = client.search_patients(family=body.patient_family)
    ext_patient = patients[0]
    observations = client.read_observations(patient_id=ext_patient["id"])
    batch = ClinicalImportBatch(
        tenant_id=tenant_id,
        source_connection_id=conn.id,
        import_type="fhir_ehr",
        status="preview",
        requested_by_user_id=user.id,
        summary={"external_patient_id": ext_patient["id"], "observation_count": len(observations)},
    )
    session.add(batch)
    session.flush()
    for obs in observations:
        # Remap subject to local patient for preview — do not write yet
        preview = {**obs, "subject": {"reference": f"Patient/{body.local_patient_id}"}}
        session.add(
            ClinicalImportItem(
                tenant_id=tenant_id,
                batch_id=batch.id,
                resource_type="Observation",
                external_identifier=obs["id"],
                mapping_status="mapped",
                validation_status="valid",
                import_status="pending",
                resource_preview=preview,
            )
        )
    session.flush()
    response.headers["Cache-Control"] = "no-store"
    return {
        "batch_id": batch.id,
        "status": batch.status,
        "summary": batch.summary,
        "note": "Preview only — approve to import. Will not silently overwrite verified records.",
    }


@router.get("/tenants/{tenant_id}/integrations/imports/{batch_id}", response_model=dict[str, Any])
def get_import_batch(
    tenant_id: str,
    batch_id: str,
    response: Response,
    user: User = Depends(get_current_user),
    membership: TenantMembership = Depends(require_role("tenant_admin", "staff")),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    if membership.tenant_id != tenant_id:
        raise ApiError("TENANT_NOT_FOUND", "Tenant not found.", 404)
    batch = session.execute(
        select(ClinicalImportBatch).where(
            ClinicalImportBatch.tenant_id == tenant_id, ClinicalImportBatch.id == batch_id
        )
    ).scalar_one_or_none()
    if batch is None:
        raise ApiError("IMPORT_NOT_FOUND", "Import batch not found.", 404)
    items = session.execute(
        select(ClinicalImportItem).where(
            ClinicalImportItem.tenant_id == tenant_id, ClinicalImportItem.batch_id == batch_id
        )
    ).scalars().all()
    response.headers["Cache-Control"] = "no-store"
    return {
        "batch_id": batch.id,
        "status": batch.status,
        "summary": batch.summary or {},
        "items": [
            {
                "item_id": item.id,
                "resource_type": item.resource_type,
                "external_identifier": item.external_identifier,
                "validation_status": item.validation_status,
                "import_status": item.import_status,
                "local_entity_reference": item.local_entity_reference,
                "error_summary": item.error_summary,
            }
            for item in items
        ],
    }


@router.post(
    "/tenants/{tenant_id}/integrations/imports/{batch_id}/approve",
    response_model=dict[str, Any],
)
def approve_import(
    tenant_id: str,
    batch_id: str,
    request: Request,
    response: Response,
    user: User = Depends(get_current_user),
    membership: TenantMembership = Depends(require_role("tenant_admin", "staff")),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    if membership.tenant_id != tenant_id:
        raise ApiError("TENANT_NOT_FOUND", "Tenant not found.", 404)
    batch = session.execute(
        select(ClinicalImportBatch).where(
            ClinicalImportBatch.tenant_id == tenant_id, ClinicalImportBatch.id == batch_id
        )
    ).scalar_one_or_none()
    if batch is None:
        raise ApiError("IMPORT_NOT_FOUND", "Import batch not found.", 404)
    if batch.status == "completed":
        response.headers["Cache-Control"] = "no-store"
        return {"batch_id": batch.id, "status": batch.status, "duplicate": True}
    items = session.execute(
        select(ClinicalImportItem).where(
            ClinicalImportItem.tenant_id == tenant_id, ClinicalImportItem.batch_id == batch_id
        )
    ).scalars().all()
    imported = 0
    for item in items:
        if item.import_status == "imported":
            continue
        body = dict(item.resource_preview or {})
        body["extension"] = list(body.get("extension") or []) + [
            {"url": "urn:healthomatix:verification", "valueString": "imported_unverified"}
        ]
        created = create_resource(
            session,
            tenant_id=tenant_id,
            resource_type=item.resource_type,
            body=body,
        )
        item.import_status = "imported"
        item.local_entity_reference = f"{item.resource_type}/{created['id']}"
        imported += 1
    batch.status = "completed"
    batch.approved_by_user_id = user.id
    batch.completed_at = utcnow()
    session.flush()
    _exchange_audit(
        session,
        tenant_id=tenant_id,
        actor_id=user.id,
        action="integration.import.approved",
        connection_id=batch.source_connection_id,
        resource_type="ClinicalImportBatch",
        resource_reference=batch.id,
        purpose_reference="ehr_data_import",
    )
    response.headers["Cache-Control"] = "no-store"
    return {"batch_id": batch.id, "status": batch.status, "imported_count": imported}


@router.get("/tenants/{tenant_id}/integrations/transactions", response_model=list[dict[str, Any]])
def list_transactions(
    tenant_id: str,
    response: Response,
    user: User = Depends(get_current_user),
    membership: TenantMembership = Depends(require_role("tenant_admin", "staff")),
    session: Session = Depends(get_session),
) -> list[dict[str, Any]]:
    if membership.tenant_id != tenant_id:
        raise ApiError("TENANT_NOT_FOUND", "Tenant not found.", 404)
    rows = session.execute(
        select(IntegrationTransaction)
        .where(IntegrationTransaction.tenant_id == tenant_id)
        .order_by(IntegrationTransaction.received_at.desc())
        .limit(100)
    ).scalars()
    response.headers["Cache-Control"] = "no-store"
    return [
        {
            "transaction_id": row.id,
            "connection_id": row.connection_id,
            "direction": row.direction,
            "message_type": row.message_type,
            "external_message_id": row.external_message_id,
            "status": row.status,
            "error_code": row.error_code,
            "error_summary": row.error_summary,
            "payload_summary": row.payload_summary or {},
            "received_at": row.received_at.isoformat(),
        }
        for row in rows
    ]


@router.post(
    "/tenants/{tenant_id}/integrations/transactions/{transaction_id}/retry",
    response_model=dict[str, Any],
)
def retry_transaction(
    tenant_id: str,
    transaction_id: str,
    response: Response,
    user: User = Depends(get_current_user),
    membership: TenantMembership = Depends(require_role("tenant_admin", "staff")),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    if membership.tenant_id != tenant_id:
        raise ApiError("TENANT_NOT_FOUND", "Tenant not found.", 404)
    txn = session.execute(
        select(IntegrationTransaction).where(
            IntegrationTransaction.tenant_id == tenant_id,
            IntegrationTransaction.id == transaction_id,
        )
    ).scalar_one_or_none()
    if txn is None:
        raise ApiError("TRANSACTION_NOT_FOUND", "Transaction not found.", 404)
    if txn.status == "processed":
        response.headers["Cache-Control"] = "no-store"
        return {
            "transaction_id": txn.id,
            "status": txn.status,
            "note": "Already processed — retry skipped to prevent duplicates.",
        }
    txn.status = "retrying"
    job = IntegrationJob(
        tenant_id=tenant_id,
        transaction_id=txn.id,
        job_type="manual_retry",
        status="queued",
        attempt_count=1,
        next_retry_at=utcnow(),
    )
    session.add(job)
    session.flush()
    response.headers["Cache-Control"] = "no-store"
    return {"transaction_id": txn.id, "status": txn.status, "job_id": job.id}


@router.get("/tenants/{tenant_id}/integrations/monitoring", response_model=dict[str, Any])
def integration_monitoring(
    tenant_id: str,
    response: Response,
    user: User = Depends(get_current_user),
    membership: TenantMembership = Depends(require_role("tenant_admin", "staff")),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    if membership.tenant_id != tenant_id:
        raise ApiError("TENANT_NOT_FOUND", "Tenant not found.", 404)

    def _count(model, *filters) -> int:
        return int(session.execute(select(func.count()).select_from(model).where(*filters)).scalar_one())

    response.headers["Cache-Control"] = "no-store"
    return {
        "connections": _count(IntegrationConnection, IntegrationConnection.tenant_id == tenant_id),
        "transactions": _count(IntegrationTransaction, IntegrationTransaction.tenant_id == tenant_id),
        "processed": _count(
            IntegrationTransaction,
            IntegrationTransaction.tenant_id == tenant_id,
            IntegrationTransaction.status == "processed",
        ),
        "awaiting_review": _count(
            IntegrationTransaction,
            IntegrationTransaction.tenant_id == tenant_id,
            IntegrationTransaction.status == "awaiting_review",
        ),
        "failed": _count(
            IntegrationTransaction,
            IntegrationTransaction.tenant_id == tenant_id,
            IntegrationTransaction.status == "failed",
        ),
        "jobs_queued": _count(
            IntegrationJob,
            IntegrationJob.tenant_id == tenant_id,
            IntegrationJob.status == "queued",
        ),
        "identity_reviews": _count(
            PatientIdentityLink,
            PatientIdentityLink.tenant_id == tenant_id,
            PatientIdentityLink.verification_status == "manual_review",
        ),
        "note": "Operational counts from durable integration tables — not fabricated.",
    }
