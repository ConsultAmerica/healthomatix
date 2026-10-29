"""FHIR-on-Postgres resource rows and document-intelligence Extraction entity."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.db import Base
from app.models import new_id, utcnow


class FhirResource(Base):
    """Stores one FHIR R4 resource as JSON with tenant and optional patient scope."""

    __tablename__ = "fhir_resources"
    __table_args__ = (
        Index("ix_fhir_type_tenant", "resource_type", "tenant_id"),
        Index("ix_fhir_type_tenant_patient", "resource_type", "tenant_id", "patient_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    resource_type: Mapped[str] = mapped_column(String(64), nullable=False)
    tenant_id: Mapped[str] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    # FHIR Patient.id when the resource is patient-scoped; null for Practitioner etc.
    patient_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    resource: Mapped[dict] = mapped_column(JSON, nullable=False)
    version_id: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    last_updated: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )


class DocumentProcessingJob(Base):
    """Durable document intelligence job (classify → OCR → extract → await review)."""

    __tablename__ = "document_processing_jobs"
    __table_args__ = (
        Index("ix_doc_job_tenant_document", "tenant_id", "document_id", "created_at"),
        Index("ix_doc_job_tenant_status", "tenant_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    document_id: Mapped[str] = mapped_column(
        ForeignKey("medical_documents.id", ondelete="CASCADE"), nullable=False
    )
    patient_id: Mapped[str] = mapped_column(String(36), nullable=False)
    job_type: Mapped[str] = mapped_column(String(32), default="lab_extract", nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="queued", nullable=False)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    processor_version: Mapped[str] = mapped_column(String(64), default="v1.3-lab", nullable=False)
    model_identifier: Mapped[str] = mapped_column(String(128), default="fake-extraction-v1", nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(64), default="lab_parser_v1", nullable=False)
    classification: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    extraction_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_summary: Mapped[str | None] = mapped_column(String(500), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )


class Extraction(Base):
    """Custom entity: AI-extracted fields pending human verification."""

    __tablename__ = "extractions"
    __table_args__ = (
        Index("ix_extraction_tenant_document", "tenant_id", "document_id"),
        Index("ix_extraction_tenant_status", "tenant_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    document_id: Mapped[str] = mapped_column(
        ForeignKey("medical_documents.id", ondelete="CASCADE"), nullable=False
    )
    # FHIR Patient.id (same as FhirResource Patient row id for that person)
    patient_id: Mapped[str] = mapped_column(String(36), nullable=False)
    document_reference_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="draft", nullable=False)
    fields: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    ocr_text: Mapped[str] = mapped_column(Text, default="", nullable=False)
    processing_job_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_by_user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    verified_by_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class VideoSession(Base):
    """Telehealth visit session bound to a booked appointment (Phase 4)."""

    __tablename__ = "video_sessions"
    __table_args__ = (
        Index("ix_video_session_tenant_appointment", "tenant_id", "appointment_id"),
        Index("ix_video_session_tenant_status", "tenant_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    appointment_id: Mapped[str] = mapped_column(
        ForeignKey("appointments.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    patient_user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    provider_user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    clinic_patient_id: Mapped[str] = mapped_column(String(36), nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="scheduled", nullable=False)
    # fake | daily | livekit | vonage | chime — Fake used in CI; live requires BAA
    video_provider: Mapped[str] = mapped_column(String(32), default="fake", nullable=False)
    room_id: Mapped[str] = mapped_column(String(128), nullable=False)
    encounter_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    follow_up_plan: Mapped[str] = mapped_column(Text, default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ClinicalDraft(Base):
    """AI clinical output held as draft until clinician approval (Phase 5)."""

    __tablename__ = "clinical_drafts"
    __table_args__ = (
        Index("ix_clinical_draft_tenant_patient", "tenant_id", "patient_id", "status"),
        Index("ix_clinical_draft_tenant_type", "tenant_id", "draft_type"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    patient_id: Mapped[str] = mapped_column(String(36), nullable=False)
    # summary | note | task
    draft_type: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="draft", nullable=False)
    title: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    content: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    source_links: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    session_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    encounter_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    # FHIR resource id written on approval (Composition / Task)
    approved_resource_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_by_user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    approved_by_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class WaitingRoomEntry(Base):
    """Patient check-in / admit state for a telehealth appointment (V1.4)."""

    __tablename__ = "waiting_room_entries"
    __table_args__ = (
        Index("ix_waiting_room_tenant_appt", "tenant_id", "appointment_id"),
        Index("ix_waiting_room_tenant_status", "tenant_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    appointment_id: Mapped[str] = mapped_column(
        ForeignKey("appointments.id", ondelete="CASCADE"), nullable=False
    )
    session_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    patient_user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    provider_user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    clinic_patient_id: Mapped[str] = mapped_column(String(36), nullable=False)
    # not_checked_in | checked_in | waiting | admitted | in_consultation | left | completed
    status: Mapped[str] = mapped_column(String(32), default="not_checked_in", nullable=False)
    checked_in_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    admitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    admitted_by_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    left_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )


class ClinicalNote(Base):
    """Clinician SOAP note with draft → signed lifecycle (V1.4)."""

    __tablename__ = "clinical_notes"
    __table_args__ = (
        Index("ix_clinical_note_tenant_patient", "tenant_id", "patient_id", "status"),
        Index("ix_clinical_note_tenant_session", "tenant_id", "session_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    patient_id: Mapped[str] = mapped_column(String(36), nullable=False)
    author_user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    session_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    encounter_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    appointment_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    note_type: Mapped[str] = mapped_column(String(32), default="soap", nullable=False)
    subjective: Mapped[str] = mapped_column(Text, default="", nullable=False)
    objective: Mapped[str] = mapped_column(Text, default="", nullable=False)
    assessment: Mapped[str] = mapped_column(Text, default="", nullable=False)
    plan: Mapped[str] = mapped_column(Text, default="", nullable=False)
    # draft | in_review | signed | discarded
    status: Mapped[str] = mapped_column(String(16), default="draft", nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    ai_assisted: Mapped[bool] = mapped_column(default=False, nullable=False)
    source_draft_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    signed_by_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    signed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )


class ClinicalNoteVersion(Base):
    """Immutable snapshots for clinical note edits and amendments."""

    __tablename__ = "clinical_note_versions"
    __table_args__ = (Index("ix_note_version_note", "tenant_id", "note_id", "version"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    note_id: Mapped[str] = mapped_column(
        ForeignKey("clinical_notes.id", ondelete="CASCADE"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    content_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    editor_user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    change_reason: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )


class FollowUpPlan(Base):
    """Clinician-approved follow-up instructions published to the patient."""

    __tablename__ = "follow_up_plans"
    __table_args__ = (
        Index("ix_follow_up_tenant_patient", "tenant_id", "patient_id", "status"),
        Index("ix_follow_up_tenant_session", "tenant_id", "session_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    patient_id: Mapped[str] = mapped_column(String(36), nullable=False)
    provider_user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    session_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    encounter_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    appointment_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    # draft | approved | published | cancelled
    status: Mapped[str] = mapped_column(String(16), default="draft", nullable=False)
    instructions: Mapped[str] = mapped_column(Text, default="", nullable=False)
    tasks: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    approved_by_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )


class AiGeneration(Base):
    """Governance metadata for every AI clinical artifact (V1.5)."""

    __tablename__ = "ai_generations"
    __table_args__ = (
        Index("ix_ai_gen_tenant_module", "tenant_id", "module", "created_at"),
        Index("ix_ai_gen_tenant_patient", "tenant_id", "patient_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    patient_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    encounter_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    session_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    # previsit | soap_draft | note_quality | message_draft | education | care_tasks | scribe
    module: Mapped[str] = mapped_column(String(32), nullable=False)
    model_identifier: Mapped[str] = mapped_column(String(64), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="generated", nullable=False)
    source_references: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    output_reference: Mapped[str | None] = mapped_column(String(64), nullable=True)
    usage_metadata: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_by_user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    reviewed_by_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )


class AiScribeSession(Base):
    """Consent-gated medical scribe session (manual or ambient)."""

    __tablename__ = "ai_scribe_sessions"
    __table_args__ = (Index("ix_scribe_tenant_status", "tenant_id", "status"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    patient_id: Mapped[str] = mapped_column(String(36), nullable=False)
    provider_user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    appointment_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    session_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    encounter_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    consent_grant_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    # manual | ambient
    mode: Mapped[str] = mapped_column(String(16), default="manual", nullable=False)
    speech_provider: Mapped[str] = mapped_column(String(32), default="fake", nullable=False)
    # created | active | paused | stopped | failed
    status: Mapped[str] = mapped_column(String(16), default="created", nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    stopped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )


class TranscriptSegment(Base):
    """Transcript segment for ambient scribe (synthetic/Fake STT in demos)."""

    __tablename__ = "transcript_segments"
    __table_args__ = (Index("ix_transcript_scribe", "tenant_id", "scribe_session_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    scribe_session_id: Mapped[str] = mapped_column(
        ForeignKey("ai_scribe_sessions.id", ondelete="CASCADE"), nullable=False
    )
    speaker_label: Mapped[str] = mapped_column(String(32), default="unknown", nullable=False)
    start_offset_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    end_offset_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    transcript_text: Mapped[str] = mapped_column(Text, default="", nullable=False)
    confidence_metadata: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )


class ClinicalNoteQualityFinding(Base):
    """Non-blocking AI/deterministic documentation quality finding."""

    __tablename__ = "clinical_note_quality_findings"
    __table_args__ = (Index("ix_note_quality_note", "tenant_id", "clinical_note_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    clinical_note_id: Mapped[str] = mapped_column(
        ForeignKey("clinical_notes.id", ondelete="CASCADE"), nullable=False
    )
    note_version: Mapped[int] = mapped_column(Integer, nullable=False)
    finding_type: Mapped[str] = mapped_column(String(64), nullable=False)
    # informational | review_recommended | high_priority | blocking
    severity: Mapped[str] = mapped_column(String(32), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    source_reference: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    suggested_action: Mapped[str] = mapped_column(Text, default="", nullable=False)
    # open | accepted | dismissed
    review_status: Mapped[str] = mapped_column(String(16), default="open", nullable=False)
    reviewed_by_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    dismiss_reason: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )


class AiMessageDraft(Base):
    """Staff-reviewed AI draft reply for patient messaging."""

    __tablename__ = "ai_message_drafts"
    __table_args__ = (Index("ix_ai_msg_draft_thread", "tenant_id", "thread_id", "status"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    thread_id: Mapped[str] = mapped_column(
        ForeignKey("message_threads.id", ondelete="CASCADE"), nullable=False
    )
    source_message_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    category: Mapped[str] = mapped_column(String(64), default="other", nullable=False)
    generated_content: Mapped[str] = mapped_column(Text, nullable=False)
    edited_content: Mapped[str] = mapped_column(Text, default="", nullable=False)
    # generated | pending_review | approved | rejected | sent
    status: Mapped[str] = mapped_column(String(16), default="generated", nullable=False)
    ai_generation_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    reviewer_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sent_message_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )


class PatientEducationSession(Base):
    """Source-grounded patient education Q&A (non-diagnostic)."""

    __tablename__ = "patient_education_sessions"
    __table_args__ = (Index("ix_edu_tenant_patient", "tenant_id", "patient_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    patient_id: Mapped[str] = mapped_column(String(36), nullable=False)
    topic: Mapped[str] = mapped_column(String(200), nullable=False)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    answer: Mapped[str] = mapped_column(Text, nullable=False)
    source_references: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    status: Mapped[str] = mapped_column(String(16), default="answered", nullable=False)
    escalated: Mapped[bool] = mapped_column(default=False, nullable=False)
    ai_generation_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )


class CareCoordinationTask(Base):
    """Staff/patient task derived from an approved follow-up plan (V1.5)."""

    __tablename__ = "care_coordination_tasks"
    __table_args__ = (
        Index("ix_care_task_plan", "tenant_id", "follow_up_plan_id", "status"),
        Index("ix_care_task_patient", "tenant_id", "patient_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    patient_id: Mapped[str] = mapped_column(String(36), nullable=False)
    follow_up_plan_id: Mapped[str] = mapped_column(
        ForeignKey("follow_up_plans.id", ondelete="CASCADE"), nullable=False
    )
    encounter_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    task_category: Mapped[str] = mapped_column(String(64), default="follow_up", nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    assigned_role: Mapped[str] = mapped_column(String(32), default="patient", nullable=False)
    assigned_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # draft | pending_approval | open | in_progress | completed | cancelled | overdue
    status: Mapped[str] = mapped_column(String(24), default="open", nullable=False)
    approval_reference: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class WorkflowAutomationExecution(Base):
    """Audit row for approved administrative automation attempts."""

    __tablename__ = "workflow_automation_executions"
    __table_args__ = (Index("ix_auto_exec_tenant", "tenant_id", "automation_type", "executed_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    automation_type: Mapped[str] = mapped_column(String(64), nullable=False)
    trigger_event_id: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    target_entity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    target_entity_id: Mapped[str] = mapped_column(String(36), nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="completed", nullable=False)
    attempt_count: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    error_code: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    executed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
