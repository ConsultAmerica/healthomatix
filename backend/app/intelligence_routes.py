"""Document intelligence: /documents listing helpers, /extractions, /verify."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit import append_audit_event
from app.auth import ApiError, get_current_user
from app.authorization import require_role
from app.config import settings
from app.consent_gate import require_patient_consent
from app.db import get_session
from app.fhir_models import Extraction
from app.fhir_store import create_resource, write_provenance
from app.intelligence.extraction_port import build_extraction_adapter
from app.intelligence.ocr_port import build_ocr_adapter
from app.intelligence.processing_service import (
    enqueue_and_run_processing,
    job_to_dict,
    latest_job_for_document,
)
from app.models import MedicalDocument, TenantMembership, User, utcnow
from app.roles import CLINICIAN_READ_ROLES
from app.schemas import (
    DocumentProcessingJobRead,
    ExtractionFieldRead,
    ExtractionRead,
    ExtractionVerifyWrite,
)
from app.storage import (
    PrivateDocumentStorage,
    StorageUnavailable,
    build_private_storage,
)

router = APIRouter(prefix="/api/v1", tags=["intelligence"])


def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", "")


def get_private_storage() -> PrivateDocumentStorage:
    return build_private_storage(settings.document_storage_path)


def _to_extraction_read(row: Extraction) -> ExtractionRead:
    fields = [
        ExtractionFieldRead.model_validate(f) if isinstance(f, dict) else f
        for f in (row.fields or [])
    ]
    return ExtractionRead(
        extraction_id=row.id,
        document_id=row.document_id,
        document_reference_id=row.document_reference_id,
        patient_id=row.patient_id,
        status=row.status,
        fields=fields,
        ocr_text=row.ocr_text,
        created_at=row.created_at,
        verified_at=row.verified_at,
        processing_job_id=getattr(row, "processing_job_id", None),
    )


def _load_stored_document(session: Session, *, tenant_id: str, document_id: str) -> MedicalDocument:
    document = session.execute(
        select(MedicalDocument).where(
            MedicalDocument.tenant_id == tenant_id,
            MedicalDocument.id == document_id,
            MedicalDocument.lifecycle_state == "stored",
        )
    ).scalar_one_or_none()
    if document is None:
        raise ApiError("DOCUMENT_NOT_FOUND", "Document not found.", 404)
    return document


def _authorize_document_access(
    *,
    session: Session,
    tenant_id: str,
    document: MedicalDocument,
    user: User,
    membership: TenantMembership,
    request: Request,
) -> None:
    patient_id = document.patient_user_id
    if membership.role == "patient" and user.id != patient_id:
        raise ApiError("DOCUMENT_NOT_FOUND", "Document not found.", 404)
    if membership.role in CLINICIAN_READ_ROLES:
        require_patient_consent(
            session,
            tenant_id=tenant_id,
            patient_id=patient_id,
            actor=user,
            membership=membership,
            request_id=_request_id(request),
            subject_type="DocumentReference",
            subject_id=document.id,
        )


@router.post(
    "/tenants/{tenant_id}/documents/{document_id}/process",
    response_model=DocumentProcessingJobRead,
    status_code=202,
)
def process_document(
    tenant_id: str,
    document_id: str,
    request: Request,
    response: Response,
    force: bool = False,
    user: User = Depends(get_current_user),
    membership: TenantMembership = Depends(require_role("tenant_admin", "staff", "provider", "patient")),
    session: Session = Depends(get_session),
    storage: PrivateDocumentStorage = Depends(get_private_storage),
) -> DocumentProcessingJobRead:
    """Enqueue durable processing (classify → OCR → extract). Runs in-process for V1.3 demos."""
    if membership.tenant_id != tenant_id:
        raise ApiError("TENANT_NOT_FOUND", "Tenant not found.", 404)
    document = _load_stored_document(session, tenant_id=tenant_id, document_id=document_id)
    _authorize_document_access(
        session=session,
        tenant_id=tenant_id,
        document=document,
        user=user,
        membership=membership,
        request=request,
    )
    job, extraction = enqueue_and_run_processing(
        session,
        tenant_id=tenant_id,
        document=document,
        actor=user,
        storage=storage,
        force=force,
    )
    append_audit_event(
        session,
        actor_user_id=user.id,
        tenant_id=tenant_id,
        action="document.processing_started",
        subject_type="DocumentProcessingJob",
        subject_id=job.id,
        request_id=_request_id(request),
    )
    if extraction is not None:
        append_audit_event(
            session,
            actor_user_id=user.id,
            tenant_id=tenant_id,
            action="extraction.created",
            subject_type="Extraction",
            subject_id=extraction.id,
            request_id=_request_id(request),
        )
    response.headers["Cache-Control"] = "no-store"
    return DocumentProcessingJobRead.model_validate(job_to_dict(job))


@router.get(
    "/tenants/{tenant_id}/documents/{document_id}/processing-status",
    response_model=DocumentProcessingJobRead | None,
)
def document_processing_status(
    tenant_id: str,
    document_id: str,
    request: Request,
    response: Response,
    user: User = Depends(get_current_user),
    membership: TenantMembership = Depends(require_role("tenant_admin", "staff", "provider", "patient")),
    session: Session = Depends(get_session),
) -> DocumentProcessingJobRead | None:
    if membership.tenant_id != tenant_id:
        raise ApiError("TENANT_NOT_FOUND", "Tenant not found.", 404)
    document = _load_stored_document(session, tenant_id=tenant_id, document_id=document_id)
    _authorize_document_access(
        session=session,
        tenant_id=tenant_id,
        document=document,
        user=user,
        membership=membership,
        request=request,
    )
    response.headers["Cache-Control"] = "no-store"
    job = latest_job_for_document(session, tenant_id=tenant_id, document_id=document_id)
    if job is None:
        return None
    return DocumentProcessingJobRead.model_validate(job_to_dict(job))


@router.post(
    "/tenants/{tenant_id}/documents/{document_id}/extractions",
    response_model=ExtractionRead,
    status_code=201,
)
def create_extraction(
    tenant_id: str,
    document_id: str,
    request: Request,
    response: Response,
    user: User = Depends(get_current_user),
    membership: TenantMembership = Depends(require_role("tenant_admin", "staff", "provider", "patient")),
    session: Session = Depends(get_session),
    storage: PrivateDocumentStorage = Depends(get_private_storage),
) -> ExtractionRead:
    """Backward-compatible extraction create; prefers the V1.3 processing pipeline."""
    if membership.tenant_id != tenant_id:
        raise ApiError("TENANT_NOT_FOUND", "Tenant not found.", 404)
    document = _load_stored_document(session, tenant_id=tenant_id, document_id=document_id)
    _authorize_document_access(
        session=session,
        tenant_id=tenant_id,
        document=document,
        user=user,
        membership=membership,
        request=request,
    )

    job, extraction = enqueue_and_run_processing(
        session,
        tenant_id=tenant_id,
        document=document,
        actor=user,
        storage=storage,
        force=True,
    )
    if extraction is None:
        # Non-lab classification: still produce a draft shell for review UX.
        try:
            content = storage.get(
                tenant_id=tenant_id, document_id=document.id, key=document.storage_key
            )
        except StorageUnavailable as error:
            raise ApiError(
                "STORAGE_UNAVAILABLE",
                "Secure document storage is not available.",
                503,
            ) from error
        ocr = build_ocr_adapter().extract_text(content=content, content_type=document.content_type)
        fields = build_extraction_adapter().extract_fields(ocr=ocr)
        extraction = Extraction(
            tenant_id=tenant_id,
            document_id=document.id,
            patient_id=document.patient_user_id,
            document_reference_id=document.id,
            status="draft",
            fields=[f.as_dict() for f in fields],
            ocr_text=ocr.full_text,
            processing_job_id=job.id,
            created_by_user_id=user.id,
        )
        session.add(extraction)
        session.flush()
        job.extraction_id = extraction.id
        job.status = "awaiting_review"
        job.completed_at = utcnow()
        session.flush()

    append_audit_event(
        session,
        actor_user_id=user.id,
        tenant_id=tenant_id,
        action="extraction.created",
        subject_type="Extraction",
        subject_id=extraction.id,
        request_id=_request_id(request),
    )
    response.headers["Cache-Control"] = "no-store"
    return _to_extraction_read(extraction)


@router.get("/tenants/{tenant_id}/extractions", response_model=list[ExtractionRead])
def list_extractions(
    tenant_id: str,
    request: Request,
    response: Response,
    patient_id: str,
    document_id: str | None = None,
    user: User = Depends(get_current_user),
    membership: TenantMembership = Depends(require_role("tenant_admin", "staff", "provider")),
    session: Session = Depends(get_session),
) -> list[ExtractionRead]:
    """List extractions for one patient. patient_id is required (consent-scoped)."""
    if membership.tenant_id != tenant_id:
        raise ApiError("TENANT_NOT_FOUND", "Tenant not found.", 404)
    response.headers["Cache-Control"] = "no-store"
    require_patient_consent(
        session,
        tenant_id=tenant_id,
        patient_id=patient_id,
        actor=user,
        membership=membership,
        request_id=_request_id(request),
    )
    stmt = select(Extraction).where(
        Extraction.tenant_id == tenant_id,
        Extraction.patient_id == patient_id,
    )
    if document_id:
        stmt = stmt.where(Extraction.document_id == document_id)
    rows = session.execute(stmt.order_by(Extraction.created_at.desc()).limit(100)).scalars()
    return [_to_extraction_read(row) for row in rows]


@router.get("/tenants/{tenant_id}/extractions/{extraction_id}", response_model=ExtractionRead)
def get_extraction(
    tenant_id: str,
    extraction_id: str,
    request: Request,
    response: Response,
    user: User = Depends(get_current_user),
    membership: TenantMembership = Depends(require_role("tenant_admin", "staff", "provider")),
    session: Session = Depends(get_session),
) -> ExtractionRead:
    if membership.tenant_id != tenant_id:
        raise ApiError("TENANT_NOT_FOUND", "Tenant not found.", 404)
    row = session.execute(
        select(Extraction).where(
            Extraction.tenant_id == tenant_id,
            Extraction.id == extraction_id,
        )
    ).scalar_one_or_none()
    if row is None:
        raise ApiError("EXTRACTION_NOT_FOUND", "Extraction not found.", 404)
    require_patient_consent(
        session,
        tenant_id=tenant_id,
        patient_id=row.patient_id,
        actor=user,
        membership=membership,
        request_id=_request_id(request),
        subject_type="Extraction",
        subject_id=row.id,
    )
    response.headers["Cache-Control"] = "no-store"
    return _to_extraction_read(row)


@router.post("/tenants/{tenant_id}/verify", response_model=dict[str, Any])
def verify_extraction(
    tenant_id: str,
    body: ExtractionVerifyWrite,
    request: Request,
    response: Response,
    user: User = Depends(get_current_user),
    membership: TenantMembership = Depends(require_role("tenant_admin", "staff", "provider")),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Human verification promotes extraction fields to FHIR Observations."""
    if membership.tenant_id != tenant_id:
        raise ApiError("TENANT_NOT_FOUND", "Tenant not found.", 404)
    row = session.execute(
        select(Extraction).where(
            Extraction.tenant_id == tenant_id,
            Extraction.id == body.extraction_id,
        )
    ).scalar_one_or_none()
    if row is None:
        raise ApiError("EXTRACTION_NOT_FOUND", "Extraction not found.", 404)
    if row.status == "verified":
        raise ApiError("EXTRACTION_ALREADY_VERIFIED", "Extraction already verified.", 409)

    require_patient_consent(
        session,
        tenant_id=tenant_id,
        patient_id=row.patient_id,
        actor=user,
        membership=membership,
        request_id=_request_id(request),
        subject_type="Extraction",
        subject_id=row.id,
    )

    # Preserve original AI values when reviewers correct fields.
    prior_by_name = {
        str(item.get("name")): item for item in (row.fields or []) if isinstance(item, dict)
    }
    merged_fields: list[dict[str, Any]] = []
    for field in body.fields:
        payload = field.model_dump()
        prior = prior_by_name.get(field.name, {})
        if prior and not payload.get("original_extracted"):
            payload["original_extracted"] = prior.get("original_extracted") or {
                "value_raw": prior.get("value_raw") or prior.get("value"),
                "unit_raw": prior.get("unit_raw") or prior.get("unit"),
                "reference_range_raw": prior.get("reference_range_raw")
                or prior.get("reference_range"),
                "abnormal_flag_raw": prior.get("abnormal_flag_raw"),
            }
        if payload.get("verification_status") in {None, "pending"}:
            payload["verification_status"] = "verified"
        merged_fields.append(payload)
    row.fields = merged_fields
    observations: list[dict[str, Any]] = []
    for field in body.fields:
        if field.verification_status == "rejected":
            continue
        if not field.value:
            continue
        obs_body: dict[str, Any] = {
            "resourceType": "Observation",
            "status": "final",
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
            "code": {"text": field.name},
            "subject": {"reference": f"Patient/{row.patient_id}"},
            "valueQuantity": {
                "value": float(field.value) if _is_number(field.value) else None,
                "unit": field.unit or None,
            }
            if _is_number(field.value)
            else None,
            "valueString": None if _is_number(field.value) else field.value,
            "referenceRange": [{"text": field.reference_range}]
            if field.reference_range
            else [],
            "effectiveDateTime": field.effective_date or None,
            "derivedFrom": [
                {
                    "reference": f"DocumentReference/{row.document_reference_id or row.document_id}"
                }
            ],
            "extension": [
                {
                    "url": "urn:healthomatix:source-region",
                    "valueString": str(field.source_region),
                },
                {
                    "url": "urn:healthomatix:extraction-id",
                    "valueString": row.id,
                },
                {
                    "url": "urn:healthomatix:confidence",
                    "valueDecimal": field.confidence,
                },
            ],
        }
        # Drop nulls for cleaner FHIR
        obs_body = {k: v for k, v in obs_body.items() if v is not None}
        obs = create_resource(
            session, tenant_id=tenant_id, resource_type="Observation", body=obs_body
        )
        write_provenance(
            session,
            tenant_id=tenant_id,
            target_type="Observation",
            target_id=obs["id"],
            patient_id=row.patient_id,
            agent_user_id=user.id,
            activity_code="CREATE",
            entity_refs=[
                ("Extraction", row.id),
                ("DocumentReference", row.document_reference_id or row.document_id),
            ],
        )
        observations.append(obs)

    row.status = "verified"
    row.verified_by_user_id = user.id
    row.verified_at = utcnow()
    session.flush()

    append_audit_event(
        session,
        actor_user_id=user.id,
        tenant_id=tenant_id,
        action="extraction.verified",
        subject_type="Extraction",
        subject_id=row.id,
        request_id=_request_id(request),
    )
    response.headers["Cache-Control"] = "no-store"
    return {
        "extraction": _to_extraction_read(row).model_dump(mode="json"),
        "observations": observations,
    }


def _is_number(value: str) -> bool:
    try:
        float(value)
        return True
    except ValueError:
        return False
