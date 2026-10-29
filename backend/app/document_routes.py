from __future__ import annotations

import hashlib
import re
import secrets
from typing import Annotated

from fastapi import APIRouter, Depends, File, Request, Response, UploadFile
from fastapi.responses import Response as RawResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit import append_audit_event
from app.auth import ApiError, get_current_user
from app.authorization import require_clinic_patient, require_role
from app.config import settings
from app.db import get_session
from app.models import ClinicPatient, MedicalDocument, TenantMembership, User
from app.schemas import DocumentRead
from app.malware_port import build_malware_scanner
from app.storage import (
    PrivateDocumentStorage,
    StorageUnavailable,
    build_private_storage,
)

router = APIRouter(prefix="/api/v1")

ALLOWED_CONTENT_TYPES = {
    "application/pdf",
    "image/jpeg",
    "image/png",
    "image/webp",
    "text/plain",
}
MAX_UPLOAD_BYTES = int(getattr(settings, "document_max_upload_bytes", 10 * 1024 * 1024) or 10 * 1024 * 1024)
SAFE_FILENAME = re.compile(r"[^A-Za-z0-9._\- ()\[\]]+")


def get_private_storage() -> PrivateDocumentStorage:
    return build_private_storage(settings.document_storage_path)


def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", "")


def _sniff_content_type(payload: bytes, declared: str) -> str:
    """Prefer file signatures over client-declared MIME types."""
    if payload.startswith(b"%PDF"):
        return "application/pdf"
    if payload.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if payload.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if len(payload) >= 12 and payload[0:4] == b"RIFF" and payload[8:12] == b"WEBP":
        return "image/webp"
    # UTF-8 / ASCII text lab fixtures
    try:
        sample = payload[:4096].decode("utf-8")
        if sample.isprintable() or "\n" in sample or "\t" in sample:
            if declared == "text/plain" or declared not in ALLOWED_CONTENT_TYPES:
                return "text/plain"
    except UnicodeDecodeError:
        pass
    return declared


def _to_read(row: MedicalDocument, *, processing_status: str | None = None, document_category: str | None = None) -> DocumentRead:
    return DocumentRead(
        document_id=row.id,
        original_filename=row.original_filename,
        content_type=row.content_type,
        size_bytes=row.size_bytes,
        lifecycle_state=row.lifecycle_state,
        created_at=row.created_at,
        clinic_patient_id=row.clinic_patient_id,
        processing_status=processing_status,
        document_category=document_category,
    )


def _sanitize_filename(name: str) -> str:
    cleaned = SAFE_FILENAME.sub("_", (name or "document").strip())[:255]
    return cleaned or "document"


@router.post(
    "/tenants/{tenant_id}/documents",
    response_model=DocumentRead,
    status_code=201,
)
async def upload_document(
    tenant_id: str,
    request: Request,
    response: Response,
    file: Annotated[UploadFile, File()],
    user: User = Depends(get_current_user),
    membership: TenantMembership = Depends(require_role("patient")),
    session: Session = Depends(get_session),
    storage: PrivateDocumentStorage = Depends(get_private_storage),
) -> DocumentRead:
    if membership.tenant_id != tenant_id:
        raise ApiError("TENANT_NOT_FOUND", "Tenant not found.", 404)
    clinic_patient = require_clinic_patient(session, tenant_id=tenant_id, user_id=user.id)

    declared = (file.content_type or "").split(";")[0].strip().lower()

    payload = await file.read()
    if not payload:
        raise ApiError("DOCUMENT_EMPTY", "The uploaded file was empty.", 422)
    if len(payload) > MAX_UPLOAD_BYTES:
        raise ApiError("DOCUMENT_TOO_LARGE", "Files must be 10 MB or smaller.", 422)

    content_type = _sniff_content_type(payload, declared)
    if content_type not in ALLOWED_CONTENT_TYPES:
        raise ApiError(
            "DOCUMENT_TYPE_UNSUPPORTED",
            "Upload a PDF, PNG, JPEG, WebP, or plain text file.",
            422,
        )

    scan = build_malware_scanner().scan(content=payload, content_type=content_type)
    if scan.status == "infected":
        raise ApiError("DOCUMENT_REJECTED", "The upload failed security screening.", 422)
    if scan.status == "unavailable" and settings.document_require_malware_clear:
        raise ApiError(
            "DOCUMENT_SCAN_UNAVAILABLE",
            "Secure malware scanning is required and is not configured.",
            503,
        )

    digest = hashlib.sha256(payload).hexdigest()
    duplicate = session.execute(
        select(MedicalDocument).where(
            MedicalDocument.tenant_id == tenant_id,
            MedicalDocument.patient_user_id == user.id,
            MedicalDocument.sha256 == digest,
            MedicalDocument.lifecycle_state == "stored",
        )
    ).scalar_one_or_none()
    if duplicate is not None:
        raise ApiError(
            "DOCUMENT_DUPLICATE",
            "An identical document was already uploaded for this clinic record.",
            409,
        )

    document = MedicalDocument(
        tenant_id=tenant_id,
        patient_user_id=user.id,
        clinic_patient_id=clinic_patient.id,
        uploaded_by_user_id=user.id,
        storage_key=f"pending:{secrets.token_hex(16)}",
        original_filename=_sanitize_filename(file.filename or "document"),
        content_type=content_type,
        size_bytes=len(payload),
        sha256=digest,
        lifecycle_state="reserved",
    )
    session.add(document)
    session.flush()

    try:
        stored = storage.put(tenant_id=tenant_id, document_id=document.id, content=payload)
    except StorageUnavailable as error:
        document.lifecycle_state = "deleted"
        session.flush()
        raise ApiError(
            "STORAGE_UNAVAILABLE",
            "Secure document storage is not available.",
            503,
        ) from error

    document.storage_key = stored.key
    document.sha256 = stored.sha256
    document.size_bytes = stored.size_bytes
    document.lifecycle_state = "stored"

    from app.fhir_store import create_resource, ensure_patient_for_user

    ensure_patient_for_user(session, tenant_id=tenant_id, user_id=user.id)
    doc_ref = create_resource(
        session,
        tenant_id=tenant_id,
        resource_type="DocumentReference",
        resource_id=document.id,
        body={
            "resourceType": "DocumentReference",
            "status": "current",
            "subject": {"reference": f"Patient/{user.id}"},
            "date": document.created_at.isoformat(),
            "content": [
                {
                    "attachment": {
                        "contentType": document.content_type,
                        "title": document.original_filename,
                        "size": document.size_bytes,
                        "hash": document.sha256,
                        "url": f"urn:healthomatix:storage:{document.storage_key}",
                    }
                }
            ],
            "extension": [
                {
                    "url": "urn:healthomatix:medical-document-id",
                    "valueString": document.id,
                }
            ],
        },
    )

    append_audit_event(
        session,
        actor_user_id=user.id,
        tenant_id=tenant_id,
        action="document.uploaded",
        subject_type="medical_document",
        subject_id=document.id,
        request_id=_request_id(request),
    )
    response.headers["Cache-Control"] = "no-store"
    read = _to_read(document)
    read.document_reference_id = doc_ref["id"]
    return read


@router.get("/tenants/{tenant_id}/documents/{document_id}/content")
def download_document(
    tenant_id: str,
    document_id: str,
    request: Request,
    user: User = Depends(get_current_user),
    membership: TenantMembership = Depends(
        require_role("patient", "tenant_admin", "staff", "provider")
    ),
    session: Session = Depends(get_session),
    storage: PrivateDocumentStorage = Depends(get_private_storage),
) -> RawResponse:
    if membership.tenant_id != tenant_id:
        raise ApiError("TENANT_NOT_FOUND", "Tenant not found.", 404)

    document = session.execute(
        select(MedicalDocument).where(
            MedicalDocument.tenant_id == tenant_id,
            MedicalDocument.id == document_id,
            MedicalDocument.lifecycle_state == "stored",
        )
    ).scalar_one_or_none()
    if document is None:
        raise ApiError("DOCUMENT_NOT_FOUND", "Document not found.", 404)

    if membership.role == "patient":
        if document.patient_user_id != user.id:
            raise ApiError("DOCUMENT_NOT_FOUND", "Document not found.", 404)
        require_clinic_patient(session, tenant_id=tenant_id, user_id=user.id)
    else:
        from app.consent_gate import require_patient_consent

        require_patient_consent(
            session,
            tenant_id=tenant_id,
            patient_id=document.patient_user_id,
            actor=user,
            membership=membership,
            request_id=_request_id(request),
            subject_type="DocumentReference",
            subject_id=document.id,
        )

    try:
        content = storage.get(
            tenant_id=tenant_id,
            document_id=document.id,
            key=document.storage_key,
        )
    except StorageUnavailable as error:
        raise ApiError(
            "STORAGE_UNAVAILABLE",
            "Secure document storage is not available.",
            503,
        ) from error

    append_audit_event(
        session,
        actor_user_id=user.id,
        tenant_id=tenant_id,
        action="document.downloaded",
        subject_type="medical_document",
        subject_id=document.id,
        request_id=_request_id(request),
    )
    headers = {
        "Cache-Control": "no-store",
        "Content-Disposition": f'attachment; filename="{document.original_filename}"',
    }
    return RawResponse(content=content, media_type=document.content_type, headers=headers)


@router.delete("/tenants/{tenant_id}/documents/{document_id}", status_code=204)
def delete_document(
    tenant_id: str,
    document_id: str,
    request: Request,
    user: User = Depends(get_current_user),
    membership: TenantMembership = Depends(require_role("patient")),
    session: Session = Depends(get_session),
    storage: PrivateDocumentStorage = Depends(get_private_storage),
) -> Response:
    if membership.tenant_id != tenant_id:
        raise ApiError("TENANT_NOT_FOUND", "Tenant not found.", 404)
    require_clinic_patient(session, tenant_id=tenant_id, user_id=user.id)
    document = session.execute(
        select(MedicalDocument).where(
            MedicalDocument.tenant_id == tenant_id,
            MedicalDocument.id == document_id,
            MedicalDocument.patient_user_id == user.id,
            MedicalDocument.lifecycle_state != "deleted",
        )
    ).scalar_one_or_none()
    if document is None:
        raise ApiError("DOCUMENT_NOT_FOUND", "Document not found.", 404)

    if document.lifecycle_state == "stored":
        try:
            storage.delete(
                tenant_id=tenant_id,
                document_id=document.id,
                key=document.storage_key,
            )
        except StorageUnavailable:
            # Soft-delete metadata even if the object store is unavailable.
            pass
    document.lifecycle_state = "deleted"
    append_audit_event(
        session,
        actor_user_id=user.id,
        tenant_id=tenant_id,
        action="document.deleted",
        subject_type="medical_document",
        subject_id=document.id,
        request_id=_request_id(request),
    )
    return Response(status_code=204, headers={"Cache-Control": "no-store"})


@router.get(
    "/tenants/{tenant_id}/patients/{clinic_patient_id}/documents",
    response_model=list[DocumentRead],
)
def list_patient_documents_for_clinic(
    tenant_id: str,
    clinic_patient_id: str,
    request: Request,
    response: Response,
    user: User = Depends(get_current_user),
    membership: TenantMembership = Depends(require_role("tenant_admin", "staff", "provider")),
    session: Session = Depends(get_session),
) -> list[DocumentRead]:
    if membership.tenant_id != tenant_id:
        raise ApiError("TENANT_NOT_FOUND", "Tenant not found.", 404)
    clinic_patient = session.execute(
        select(ClinicPatient).where(
            ClinicPatient.tenant_id == tenant_id,
            ClinicPatient.id == clinic_patient_id,
            ClinicPatient.status == "active",
        )
    ).scalar_one_or_none()
    if clinic_patient is None:
        raise ApiError("PATIENT_NOT_FOUND", "Patient not found.", 404)

    from app.consent_gate import require_patient_consent

    require_patient_consent(
        session,
        tenant_id=tenant_id,
        patient_id=clinic_patient.patient_user_id,
        actor=user,
        membership=membership,
        request_id=_request_id(request),
        subject_type="ClinicPatient",
        subject_id=clinic_patient_id,
    )

    response.headers["Cache-Control"] = "no-store"
    rows = session.execute(
        select(MedicalDocument)
        .where(
            MedicalDocument.tenant_id == tenant_id,
            MedicalDocument.clinic_patient_id == clinic_patient_id,
            MedicalDocument.lifecycle_state != "deleted",
        )
        .order_by(MedicalDocument.created_at.desc())
        .limit(100)
    ).scalars()
    return [_to_read(row) for row in rows]
