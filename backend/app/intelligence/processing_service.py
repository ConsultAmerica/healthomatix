"""Document processing pipeline: validate → classify → OCR → extract → await review."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import ApiError
from app.fhir_models import DocumentProcessingJob, Extraction
from app.intelligence.extraction_port import build_extraction_adapter
from app.intelligence.lab_parser import classify_document_text
from app.intelligence.ocr_port import build_ocr_adapter
from app.models import MedicalDocument, User, utcnow
from app.storage import PrivateDocumentStorage, StorageUnavailable


TERMINAL_OK = {"awaiting_review", "verified", "partially_verified", "rejected"}
ACTIVE = {"queued", "processing"}


def latest_job_for_document(
    session: Session, *, tenant_id: str, document_id: str
) -> DocumentProcessingJob | None:
    return session.execute(
        select(DocumentProcessingJob)
        .where(
            DocumentProcessingJob.tenant_id == tenant_id,
            DocumentProcessingJob.document_id == document_id,
        )
        .order_by(DocumentProcessingJob.created_at.desc())
        .limit(1)
    ).scalar_one_or_none()


def enqueue_and_run_processing(
    session: Session,
    *,
    tenant_id: str,
    document: MedicalDocument,
    actor: User,
    storage: PrivateDocumentStorage,
    force: bool = False,
) -> tuple[DocumentProcessingJob, Extraction | None]:
    """Create a durable job and run the pipeline in-process (worker-ready boundary).

    External queue workers can later claim `queued` jobs; V1.3 runs immediately after enqueue
    so demos and tests stay deterministic without Redis/Celery.
    """
    existing = latest_job_for_document(
        session, tenant_id=tenant_id, document_id=document.id
    )
    if existing and existing.status in ACTIVE and not force:
        return existing, None
    if (
        existing
        and existing.status in TERMINAL_OK
        and existing.extraction_id
        and not force
    ):
        extraction = session.get(Extraction, existing.extraction_id)
        return existing, extraction

    job = DocumentProcessingJob(
        tenant_id=tenant_id,
        document_id=document.id,
        patient_id=document.patient_user_id,
        job_type="lab_extract",
        status="queued",
        classification={},
    )
    session.add(job)
    session.flush()

    job.status = "processing"
    job.attempt_count += 1
    job.started_at = utcnow()
    session.flush()

    try:
        content = storage.get(
            tenant_id=tenant_id, document_id=document.id, key=document.storage_key
        )
    except StorageUnavailable as error:
        job.status = "failed"
        job.error_code = "STORAGE_UNAVAILABLE"
        job.error_summary = "Secure document storage is not available."
        job.completed_at = utcnow()
        session.flush()
        raise ApiError("STORAGE_UNAVAILABLE", job.error_summary, 503) from error

    ocr = build_ocr_adapter().extract_text(content=content, content_type=document.content_type)
    classification = classify_document_text(ocr.full_text)
    job.classification = classification

    if not classification.get("auto_extract_lab"):
        job.status = "awaiting_review"
        job.error_code = None
        job.error_summary = "Document classified as non-lab or low confidence; lab extraction not auto-run."
        job.completed_at = utcnow()
        session.flush()
        return job, None

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
        created_by_user_id=actor.id,
    )
    session.add(extraction)
    session.flush()

    job.extraction_id = extraction.id
    job.status = "awaiting_review"
    job.completed_at = utcnow()
    session.flush()
    return job, extraction


def job_to_dict(job: DocumentProcessingJob) -> dict[str, Any]:
    return {
        "job_id": job.id,
        "document_id": job.document_id,
        "patient_id": job.patient_id,
        "job_type": job.job_type,
        "status": job.status,
        "attempt_count": job.attempt_count,
        "processor_version": job.processor_version,
        "model_identifier": job.model_identifier,
        "prompt_version": job.prompt_version,
        "classification": job.classification or {},
        "extraction_id": job.extraction_id,
        "error_code": job.error_code,
        "error_summary": job.error_summary,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
        "created_at": job.created_at.isoformat(),
    }
