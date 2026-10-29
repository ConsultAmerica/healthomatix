"""V1.5 AI Clinical Copilot: scribe, quality, messaging drafts, education, care tasks, analytics."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.audit import append_audit_event
from app.auth import ApiError, get_current_user
from app.authorization import require_role
from app.consent_gate import require_patient_consent, require_scribe_ambient_consent
from app.db import get_session
from app.fhir_models import (
    AiGeneration,
    AiMessageDraft,
    AiScribeSession,
    CareCoordinationTask,
    ClinicalDraft,
    ClinicalNote,
    ClinicalNoteQualityFinding,
    FollowUpPlan,
    PatientEducationSession,
    TranscriptSegment,
    WorkflowAutomationExecution,
)
from app.fhir_store import search_resources
from app.intelligence.clinical_ai_port import (
    MODEL_ID,
    PROMPT_VERSION,
    build_clinical_ai_adapter,
)
from app.intelligence.speech_port import build_speech_adapter
from app.models import ClinicPatient, Message, MessageThread, TenantMembership, User, utcnow
from app.schemas import (
    AiGenerationRead,
    AiMessageDraftCreate,
    AiMessageDraftEditWrite,
    AiMessageDraftRead,
    AiMessageDraftSendWrite,
    CareTaskCreateWrite,
    CareTaskPatchWrite,
    CareTaskRead,
    CareTaskSuggestRead,
    PatientEducationAskWrite,
    PatientEducationRead,
    QualityFindingRead,
    QualityFindingReviewWrite,
    ScribeGenerateNoteWrite,
    ScribeSessionRead,
    ScribeStartWrite,
    SoapDraftRead,
    TranscriptSegmentRead,
    WorkflowAnalyticsRead,
)

router = APIRouter(prefix="/api/v1", tags=["ai-copilot"])


def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", "")


def _record_generation(
    session: Session,
    *,
    tenant_id: str,
    user: User,
    module: str,
    patient_id: str | None = None,
    source_references: list | None = None,
    output_reference: str | None = None,
    usage_metadata: dict | None = None,
) -> AiGeneration:
    row = AiGeneration(
        tenant_id=tenant_id,
        patient_id=patient_id,
        module=module,
        model_identifier=MODEL_ID,
        prompt_version=PROMPT_VERSION,
        status="generated",
        source_references=source_references or [],
        output_reference=output_reference,
        usage_metadata=usage_metadata or {"provider": "fake", "tokens_estimated": 0},
        created_by_user_id=user.id,
    )
    session.add(row)
    session.flush()
    return row


def _scribe_read(row: AiScribeSession) -> ScribeSessionRead:
    return ScribeSessionRead(
        scribe_session_id=row.id,
        patient_id=row.patient_id,
        mode=row.mode,
        status=row.status,
        speech_provider=row.speech_provider,
        consent_grant_id=row.consent_grant_id,
        started_at=row.started_at,
        stopped_at=row.stopped_at,
        created_at=row.created_at,
    )


def _msg_draft_read(row: AiMessageDraft) -> AiMessageDraftRead:
    return AiMessageDraftRead(
        draft_id=row.id,
        thread_id=row.thread_id,
        category=row.category,
        generated_content=row.generated_content,
        edited_content=row.edited_content,
        status=row.status,
        sent_message_id=row.sent_message_id,
        created_at=row.created_at,
    )


def _care_task_read(row: CareCoordinationTask) -> CareTaskRead:
    return CareTaskRead(
        task_id=row.id,
        follow_up_plan_id=row.follow_up_plan_id,
        patient_id=row.patient_id,
        task_category=row.task_category,
        description=row.description,
        assigned_role=row.assigned_role,
        status=row.status,
        due_at=row.due_at,
        created_at=row.created_at,
        completed_at=row.completed_at,
    )


@router.post(
    "/tenants/{tenant_id}/scribe/sessions",
    response_model=ScribeSessionRead,
    status_code=201,
)
def start_scribe_session(
    tenant_id: str,
    body: ScribeStartWrite,
    request: Request,
    response: Response,
    user: User = Depends(get_current_user),
    membership: TenantMembership = Depends(require_role("tenant_admin", "staff", "provider")),
    session: Session = Depends(get_session),
) -> ScribeSessionRead:
    if membership.tenant_id != tenant_id:
        raise ApiError("TENANT_NOT_FOUND", "Tenant not found.", 404)
    require_patient_consent(
        session,
        tenant_id=tenant_id,
        patient_id=body.patient_id,
        actor=user,
        membership=membership,
        request_id=_request_id(request),
    )
    consent_id = None
    if body.mode == "ambient":
        grant = require_scribe_ambient_consent(
            session,
            tenant_id=tenant_id,
            patient_id=body.patient_id,
            actor=user,
            request_id=_request_id(request),
        )
        consent_id = grant.id

    speech = build_speech_adapter()
    row = AiScribeSession(
        tenant_id=tenant_id,
        patient_id=body.patient_id,
        provider_user_id=user.id,
        appointment_id=body.appointment_id,
        session_id=body.session_id,
        consent_grant_id=consent_id,
        mode=body.mode,
        speech_provider=getattr(speech, "provider", "fake"),
        status="active",
        started_at=utcnow(),
    )
    session.add(row)
    session.flush()

    if body.mode == "ambient":
        chunks = speech.transcribe_synthetic(
            session_id=row.id, clinician_notes=body.clinician_notes
        )
        for chunk in chunks:
            session.add(
                TranscriptSegment(
                    tenant_id=tenant_id,
                    scribe_session_id=row.id,
                    speaker_label=chunk.speaker_label,
                    start_offset_ms=chunk.start_offset_ms,
                    end_offset_ms=chunk.end_offset_ms,
                    transcript_text=chunk.text,
                    confidence_metadata={"confidence": chunk.confidence, "provider": "fake"},
                )
            )

    _record_generation(
        session,
        tenant_id=tenant_id,
        user=user,
        module="scribe",
        patient_id=body.patient_id,
        output_reference=f"AiScribeSession/{row.id}",
        usage_metadata={"mode": body.mode, "provider": row.speech_provider},
    )
    append_audit_event(
        session,
        actor_user_id=user.id,
        tenant_id=tenant_id,
        action="scribe.started",
        subject_type="AiScribeSession",
        subject_id=row.id,
        request_id=_request_id(request),
    )
    response.headers["Cache-Control"] = "no-store"
    return _scribe_read(row)


@router.post(
    "/tenants/{tenant_id}/scribe/sessions/{scribe_session_id}/pause",
    response_model=ScribeSessionRead,
)
def pause_scribe(
    tenant_id: str,
    scribe_session_id: str,
    request: Request,
    response: Response,
    user: User = Depends(get_current_user),
    membership: TenantMembership = Depends(require_role("tenant_admin", "staff", "provider")),
    session: Session = Depends(get_session),
) -> ScribeSessionRead:
    if membership.tenant_id != tenant_id:
        raise ApiError("TENANT_NOT_FOUND", "Tenant not found.", 404)
    row = session.execute(
        select(AiScribeSession).where(
            AiScribeSession.tenant_id == tenant_id, AiScribeSession.id == scribe_session_id
        )
    ).scalar_one_or_none()
    if row is None:
        raise ApiError("SCRIBE_NOT_FOUND", "Scribe session not found.", 404)
    if row.status != "active":
        raise ApiError("SCRIBE_STATE", "Only active sessions can be paused.", 409)
    row.status = "paused"
    session.flush()
    response.headers["Cache-Control"] = "no-store"
    return _scribe_read(row)


@router.post(
    "/tenants/{tenant_id}/scribe/sessions/{scribe_session_id}/resume",
    response_model=ScribeSessionRead,
)
def resume_scribe(
    tenant_id: str,
    scribe_session_id: str,
    response: Response,
    user: User = Depends(get_current_user),
    membership: TenantMembership = Depends(require_role("tenant_admin", "staff", "provider")),
    session: Session = Depends(get_session),
) -> ScribeSessionRead:
    if membership.tenant_id != tenant_id:
        raise ApiError("TENANT_NOT_FOUND", "Tenant not found.", 404)
    row = session.execute(
        select(AiScribeSession).where(
            AiScribeSession.tenant_id == tenant_id, AiScribeSession.id == scribe_session_id
        )
    ).scalar_one_or_none()
    if row is None:
        raise ApiError("SCRIBE_NOT_FOUND", "Scribe session not found.", 404)
    if row.status != "paused":
        raise ApiError("SCRIBE_STATE", "Only paused sessions can be resumed.", 409)
    if row.mode == "ambient":
        require_scribe_ambient_consent(
            session, tenant_id=tenant_id, patient_id=row.patient_id, actor=user
        )
    row.status = "active"
    session.flush()
    response.headers["Cache-Control"] = "no-store"
    return _scribe_read(row)


@router.post(
    "/tenants/{tenant_id}/scribe/sessions/{scribe_session_id}/stop",
    response_model=ScribeSessionRead,
)
def stop_scribe(
    tenant_id: str,
    scribe_session_id: str,
    request: Request,
    response: Response,
    user: User = Depends(get_current_user),
    membership: TenantMembership = Depends(require_role("tenant_admin", "staff", "provider")),
    session: Session = Depends(get_session),
) -> ScribeSessionRead:
    if membership.tenant_id != tenant_id:
        raise ApiError("TENANT_NOT_FOUND", "Tenant not found.", 404)
    row = session.execute(
        select(AiScribeSession).where(
            AiScribeSession.tenant_id == tenant_id, AiScribeSession.id == scribe_session_id
        )
    ).scalar_one_or_none()
    if row is None:
        raise ApiError("SCRIBE_NOT_FOUND", "Scribe session not found.", 404)
    if row.status == "stopped":
        response.headers["Cache-Control"] = "no-store"
        return _scribe_read(row)
    row.status = "stopped"
    row.stopped_at = utcnow()
    session.flush()
    append_audit_event(
        session,
        actor_user_id=user.id,
        tenant_id=tenant_id,
        action="scribe.stopped",
        subject_type="AiScribeSession",
        subject_id=row.id,
        request_id=_request_id(request),
    )
    response.headers["Cache-Control"] = "no-store"
    return _scribe_read(row)


@router.get(
    "/tenants/{tenant_id}/scribe/sessions/{scribe_session_id}/transcript",
    response_model=list[TranscriptSegmentRead],
)
def get_transcript(
    tenant_id: str,
    scribe_session_id: str,
    response: Response,
    user: User = Depends(get_current_user),
    membership: TenantMembership = Depends(require_role("tenant_admin", "staff", "provider")),
    session: Session = Depends(get_session),
) -> list[TranscriptSegmentRead]:
    if membership.tenant_id != tenant_id:
        raise ApiError("TENANT_NOT_FOUND", "Tenant not found.", 404)
    row = session.execute(
        select(AiScribeSession).where(
            AiScribeSession.tenant_id == tenant_id, AiScribeSession.id == scribe_session_id
        )
    ).scalar_one_or_none()
    if row is None:
        raise ApiError("SCRIBE_NOT_FOUND", "Scribe session not found.", 404)
    require_patient_consent(
        session,
        tenant_id=tenant_id,
        patient_id=row.patient_id,
        actor=user,
        membership=membership,
    )
    segments = session.execute(
        select(TranscriptSegment)
        .where(
            TranscriptSegment.tenant_id == tenant_id,
            TranscriptSegment.scribe_session_id == scribe_session_id,
        )
        .order_by(TranscriptSegment.start_offset_ms.asc())
    ).scalars()
    response.headers["Cache-Control"] = "no-store"
    return [
        TranscriptSegmentRead(
            segment_id=seg.id,
            speaker_label=seg.speaker_label,
            start_offset_ms=seg.start_offset_ms,
            end_offset_ms=seg.end_offset_ms,
            transcript_text=seg.transcript_text,
            confidence_metadata=seg.confidence_metadata or {},
        )
        for seg in segments
    ]


@router.post(
    "/tenants/{tenant_id}/scribe/sessions/{scribe_session_id}/generate-note",
    response_model=SoapDraftRead,
)
def generate_scribe_note(
    tenant_id: str,
    scribe_session_id: str,
    body: ScribeGenerateNoteWrite,
    request: Request,
    response: Response,
    user: User = Depends(get_current_user),
    membership: TenantMembership = Depends(require_role("tenant_admin", "staff", "provider")),
    session: Session = Depends(get_session),
) -> SoapDraftRead:
    if membership.tenant_id != tenant_id:
        raise ApiError("TENANT_NOT_FOUND", "Tenant not found.", 404)
    row = session.execute(
        select(AiScribeSession).where(
            AiScribeSession.tenant_id == tenant_id, AiScribeSession.id == scribe_session_id
        )
    ).scalar_one_or_none()
    if row is None:
        raise ApiError("SCRIBE_NOT_FOUND", "Scribe session not found.", 404)
    require_patient_consent(
        session,
        tenant_id=tenant_id,
        patient_id=row.patient_id,
        actor=user,
        membership=membership,
        request_id=_request_id(request),
    )
    segments = session.execute(
        select(TranscriptSegment).where(
            TranscriptSegment.tenant_id == tenant_id,
            TranscriptSegment.scribe_session_id == scribe_session_id,
        )
    ).scalars().all()
    transcript = " ".join(seg.transcript_text for seg in segments)
    observations = search_resources(
        session,
        tenant_id=tenant_id,
        resource_type="Observation",
        patient_id=row.patient_id,
        limit=50,
    )
    bundle = build_clinical_ai_adapter().generate_soap_draft(
        patient_id=row.patient_id,
        visit_reason=body.visit_reason,
        clinician_notes=body.clinician_notes,
        transcript=transcript,
        observations=observations,
    )
    content = bundle.content
    draft = ClinicalDraft(
        tenant_id=tenant_id,
        patient_id=row.patient_id,
        draft_type="note",
        status="draft",
        title=bundle.title,
        content=content,
        source_links=bundle.source_links,
        session_id=row.session_id,
        created_by_user_id=user.id,
    )
    session.add(draft)
    session.flush()
    gen = _record_generation(
        session,
        tenant_id=tenant_id,
        user=user,
        module="soap_draft",
        patient_id=row.patient_id,
        source_references=bundle.source_links,
        output_reference=f"ClinicalDraft/{draft.id}",
    )
    response.headers["Cache-Control"] = "no-store"
    return SoapDraftRead(
        generation_id=gen.id,
        draft_id=draft.id,
        subjective=str(content.get("subjective", "")),
        objective=str(content.get("objective", "")),
        assessment=str(content.get("assessment", "")),
        plan=str(content.get("plan", "")),
        source_links=bundle.source_links,
        disclaimer=str(content.get("disclaimer", "")),
    )


@router.post(
    "/tenants/{tenant_id}/clinical-notes/{note_id}/quality-check",
    response_model=list[QualityFindingRead],
)
def run_quality_check(
    tenant_id: str,
    note_id: str,
    request: Request,
    response: Response,
    user: User = Depends(get_current_user),
    membership: TenantMembership = Depends(require_role("tenant_admin", "staff", "provider")),
    session: Session = Depends(get_session),
) -> list[QualityFindingRead]:
    if membership.tenant_id != tenant_id:
        raise ApiError("TENANT_NOT_FOUND", "Tenant not found.", 404)
    note = session.execute(
        select(ClinicalNote).where(ClinicalNote.tenant_id == tenant_id, ClinicalNote.id == note_id)
    ).scalar_one_or_none()
    if note is None:
        raise ApiError("NOTE_NOT_FOUND", "Clinical note not found.", 404)
    require_patient_consent(
        session,
        tenant_id=tenant_id,
        patient_id=note.patient_id,
        actor=user,
        membership=membership,
        request_id=_request_id(request),
    )
    drafts = build_clinical_ai_adapter().analyze_note_quality(
        subjective=note.subjective,
        objective=note.objective,
        assessment=note.assessment,
        plan=note.plan,
    )
    findings: list[ClinicalNoteQualityFinding] = []
    for item in drafts:
        finding = ClinicalNoteQualityFinding(
            tenant_id=tenant_id,
            clinical_note_id=note.id,
            note_version=note.version,
            finding_type=item.finding_type,
            severity=item.severity,
            description=item.description,
            source_reference=item.source_reference,
            suggested_action=item.suggested_action,
            review_status="open",
        )
        session.add(finding)
        findings.append(finding)
    session.flush()
    _record_generation(
        session,
        tenant_id=tenant_id,
        user=user,
        module="note_quality",
        patient_id=note.patient_id,
        output_reference=f"ClinicalNote/{note.id}",
        usage_metadata={"finding_count": len(findings)},
    )
    response.headers["Cache-Control"] = "no-store"
    return [
        QualityFindingRead(
            finding_id=f.id,
            clinical_note_id=f.clinical_note_id,
            note_version=f.note_version,
            finding_type=f.finding_type,
            severity=f.severity,
            description=f.description,
            source_reference=f.source_reference,
            suggested_action=f.suggested_action,
            review_status=f.review_status,
            created_at=f.created_at,
        )
        for f in findings
    ]


@router.get(
    "/tenants/{tenant_id}/clinical-notes/{note_id}/quality-findings",
    response_model=list[QualityFindingRead],
)
def list_quality_findings(
    tenant_id: str,
    note_id: str,
    response: Response,
    user: User = Depends(get_current_user),
    membership: TenantMembership = Depends(require_role("tenant_admin", "staff", "provider")),
    session: Session = Depends(get_session),
) -> list[QualityFindingRead]:
    if membership.tenant_id != tenant_id:
        raise ApiError("TENANT_NOT_FOUND", "Tenant not found.", 404)
    note = session.execute(
        select(ClinicalNote).where(ClinicalNote.tenant_id == tenant_id, ClinicalNote.id == note_id)
    ).scalar_one_or_none()
    if note is None:
        raise ApiError("NOTE_NOT_FOUND", "Clinical note not found.", 404)
    require_patient_consent(
        session,
        tenant_id=tenant_id,
        patient_id=note.patient_id,
        actor=user,
        membership=membership,
    )
    rows = session.execute(
        select(ClinicalNoteQualityFinding)
        .where(
            ClinicalNoteQualityFinding.tenant_id == tenant_id,
            ClinicalNoteQualityFinding.clinical_note_id == note_id,
        )
        .order_by(ClinicalNoteQualityFinding.created_at.desc())
        .limit(100)
    ).scalars()
    response.headers["Cache-Control"] = "no-store"
    return [
        QualityFindingRead(
            finding_id=f.id,
            clinical_note_id=f.clinical_note_id,
            note_version=f.note_version,
            finding_type=f.finding_type,
            severity=f.severity,
            description=f.description,
            source_reference=f.source_reference,
            suggested_action=f.suggested_action,
            review_status=f.review_status,
            created_at=f.created_at,
        )
        for f in rows
    ]


@router.post(
    "/tenants/{tenant_id}/clinical-notes/{note_id}/quality-findings/{finding_id}/review",
    response_model=QualityFindingRead,
)
def review_quality_finding(
    tenant_id: str,
    note_id: str,
    finding_id: str,
    body: QualityFindingReviewWrite,
    response: Response,
    user: User = Depends(get_current_user),
    membership: TenantMembership = Depends(require_role("tenant_admin", "staff", "provider")),
    session: Session = Depends(get_session),
) -> QualityFindingRead:
    if membership.tenant_id != tenant_id:
        raise ApiError("TENANT_NOT_FOUND", "Tenant not found.", 404)
    finding = session.execute(
        select(ClinicalNoteQualityFinding).where(
            ClinicalNoteQualityFinding.tenant_id == tenant_id,
            ClinicalNoteQualityFinding.clinical_note_id == note_id,
            ClinicalNoteQualityFinding.id == finding_id,
        )
    ).scalar_one_or_none()
    if finding is None:
        raise ApiError("FINDING_NOT_FOUND", "Quality finding not found.", 404)
    if body.action == "dismiss" and not body.dismiss_reason.strip():
        raise ApiError("DISMISS_REASON_REQUIRED", "Provide a dismiss reason.", 422)
    finding.review_status = "accepted" if body.action == "accept" else "dismissed"
    finding.reviewed_by_user_id = user.id
    finding.reviewed_at = utcnow()
    finding.dismiss_reason = body.dismiss_reason.strip()
    session.flush()
    response.headers["Cache-Control"] = "no-store"
    return QualityFindingRead(
        finding_id=finding.id,
        clinical_note_id=finding.clinical_note_id,
        note_version=finding.note_version,
        finding_type=finding.finding_type,
        severity=finding.severity,
        description=finding.description,
        source_reference=finding.source_reference,
        suggested_action=finding.suggested_action,
        review_status=finding.review_status,
        created_at=finding.created_at,
    )


@router.post(
    "/tenants/{tenant_id}/threads/{thread_id}/ai/draft-response",
    response_model=AiMessageDraftRead,
    status_code=201,
)
def draft_message_response(
    tenant_id: str,
    thread_id: str,
    body: AiMessageDraftCreate,
    request: Request,
    response: Response,
    user: User = Depends(get_current_user),
    membership: TenantMembership = Depends(require_role("tenant_admin", "staff", "provider")),
    session: Session = Depends(get_session),
) -> AiMessageDraftRead:
    if membership.tenant_id != tenant_id:
        raise ApiError("TENANT_NOT_FOUND", "Tenant not found.", 404)
    thread = session.execute(
        select(MessageThread).where(
            MessageThread.tenant_id == tenant_id, MessageThread.id == thread_id
        )
    ).scalar_one_or_none()
    if thread is None:
        raise ApiError("THREAD_NOT_FOUND", "Thread not found.", 404)
    messages = session.execute(
        select(Message)
        .where(Message.thread_id == thread.id, Message.tenant_id == tenant_id)
        .order_by(Message.created_at.desc())
        .limit(20)
    ).scalars().all()
    clinic_patient = session.get(ClinicPatient, thread.clinic_patient_id)
    patient_user_id = clinic_patient.patient_user_id if clinic_patient else None
    source = None
    if body.source_message_id:
        source = next((m for m in messages if m.id == body.source_message_id), None)
        if source is None:
            raise ApiError("MESSAGE_NOT_FOUND", "Source message not found.", 404)
    else:
        source = None
        if patient_user_id:
            source = next((m for m in messages if m.sender_user_id == patient_user_id), None)
        if source is None and messages:
            source = messages[0]
    latest = source.body if source else ""
    bundle = build_clinical_ai_adapter().draft_patient_message(
        subject=thread.subject or "",
        latest_patient_message=latest,
    )
    gen = _record_generation(
        session,
        tenant_id=tenant_id,
        user=user,
        module="message_draft",
        patient_id=patient_user_id,
        output_reference=f"MessageThread/{thread.id}",
        usage_metadata={"category": bundle.category, "urgency_hint": bundle.urgency_hint},
    )
    draft = AiMessageDraft(
        tenant_id=tenant_id,
        thread_id=thread.id,
        source_message_id=source.id if source else None,
        category=bundle.category,
        generated_content=bundle.content,
        edited_content=bundle.content,
        status="pending_review",
        ai_generation_id=gen.id,
    )
    session.add(draft)
    session.flush()
    append_audit_event(
        session,
        actor_user_id=user.id,
        tenant_id=tenant_id,
        action="ai_message.drafted",
        subject_type="AiMessageDraft",
        subject_id=draft.id,
        request_id=_request_id(request),
    )
    response.headers["Cache-Control"] = "no-store"
    return _msg_draft_read(draft)


@router.get(
    "/tenants/{tenant_id}/threads/{thread_id}/ai/drafts",
    response_model=list[AiMessageDraftRead],
)
def list_message_drafts(
    tenant_id: str,
    thread_id: str,
    response: Response,
    user: User = Depends(get_current_user),
    membership: TenantMembership = Depends(require_role("tenant_admin", "staff", "provider")),
    session: Session = Depends(get_session),
) -> list[AiMessageDraftRead]:
    if membership.tenant_id != tenant_id:
        raise ApiError("TENANT_NOT_FOUND", "Tenant not found.", 404)
    rows = session.execute(
        select(AiMessageDraft)
        .where(AiMessageDraft.tenant_id == tenant_id, AiMessageDraft.thread_id == thread_id)
        .order_by(AiMessageDraft.created_at.desc())
        .limit(20)
    ).scalars()
    response.headers["Cache-Control"] = "no-store"
    return [_msg_draft_read(row) for row in rows]


@router.post(
    "/tenants/{tenant_id}/ai/message-drafts/{draft_id}/approve",
    response_model=AiMessageDraftRead,
)
def approve_message_draft(
    tenant_id: str,
    draft_id: str,
    response: Response,
    body: AiMessageDraftEditWrite | None = None,
    user: User = Depends(get_current_user),
    membership: TenantMembership = Depends(require_role("tenant_admin", "staff", "provider")),
    session: Session = Depends(get_session),
) -> AiMessageDraftRead:
    if membership.tenant_id != tenant_id:
        raise ApiError("TENANT_NOT_FOUND", "Tenant not found.", 404)
    draft = session.execute(
        select(AiMessageDraft).where(
            AiMessageDraft.tenant_id == tenant_id, AiMessageDraft.id == draft_id
        )
    ).scalar_one_or_none()
    if draft is None:
        raise ApiError("DRAFT_NOT_FOUND", "AI message draft not found.", 404)
    if draft.status not in {"generated", "pending_review", "approved"}:
        raise ApiError("DRAFT_STATE", "Draft cannot be approved from its current state.", 409)
    if body and body.edited_content.strip():
        draft.edited_content = body.edited_content.strip()
    draft.status = "approved"
    draft.reviewer_user_id = user.id
    draft.approved_at = utcnow()
    session.flush()
    response.headers["Cache-Control"] = "no-store"
    return _msg_draft_read(draft)


@router.post(
    "/tenants/{tenant_id}/ai/message-drafts/{draft_id}/reject",
    response_model=AiMessageDraftRead,
)
def reject_message_draft(
    tenant_id: str,
    draft_id: str,
    response: Response,
    user: User = Depends(get_current_user),
    membership: TenantMembership = Depends(require_role("tenant_admin", "staff", "provider")),
    session: Session = Depends(get_session),
) -> AiMessageDraftRead:
    if membership.tenant_id != tenant_id:
        raise ApiError("TENANT_NOT_FOUND", "Tenant not found.", 404)
    draft = session.execute(
        select(AiMessageDraft).where(
            AiMessageDraft.tenant_id == tenant_id, AiMessageDraft.id == draft_id
        )
    ).scalar_one_or_none()
    if draft is None:
        raise ApiError("DRAFT_NOT_FOUND", "AI message draft not found.", 404)
    draft.status = "rejected"
    draft.reviewer_user_id = user.id
    session.flush()
    response.headers["Cache-Control"] = "no-store"
    return _msg_draft_read(draft)


@router.post(
    "/tenants/{tenant_id}/ai/message-drafts/{draft_id}/send",
    response_model=AiMessageDraftRead,
)
def send_message_draft(
    tenant_id: str,
    draft_id: str,
    body: AiMessageDraftSendWrite,
    request: Request,
    response: Response,
    user: User = Depends(get_current_user),
    membership: TenantMembership = Depends(require_role("tenant_admin", "staff", "provider")),
    session: Session = Depends(get_session),
) -> AiMessageDraftRead:
    if membership.tenant_id != tenant_id:
        raise ApiError("TENANT_NOT_FOUND", "Tenant not found.", 404)
    draft = session.execute(
        select(AiMessageDraft).where(
            AiMessageDraft.tenant_id == tenant_id, AiMessageDraft.id == draft_id
        )
    ).scalar_one_or_none()
    if draft is None:
        raise ApiError("DRAFT_NOT_FOUND", "AI message draft not found.", 404)
    if draft.status == "sent" and draft.idempotency_key == body.idempotency_key:
        response.headers["Cache-Control"] = "no-store"
        return _msg_draft_read(draft)
    if draft.status != "approved":
        raise ApiError("DRAFT_NOT_APPROVED", "Approve the draft before sending.", 409)
    if draft.idempotency_key and draft.idempotency_key != body.idempotency_key and draft.sent_message_id:
        raise ApiError("DUPLICATE_SEND", "Draft already sent with a different idempotency key.", 409)

    text = (body.body or draft.edited_content or draft.generated_content).strip()
    if not text:
        raise ApiError("EMPTY_MESSAGE", "Message body is empty.", 422)
    message = Message(
        tenant_id=tenant_id,
        thread_id=draft.thread_id,
        sender_user_id=user.id,
        body=text,
    )
    session.add(message)
    thread = session.get(MessageThread, draft.thread_id)
    if thread:
        thread.updated_at = utcnow()
    draft.status = "sent"
    draft.sent_message_id = message.id
    draft.idempotency_key = body.idempotency_key
    draft.reviewer_user_id = user.id
    session.flush()
    # Fix message id after flush
    draft.sent_message_id = message.id
    append_audit_event(
        session,
        actor_user_id=user.id,
        tenant_id=tenant_id,
        action="ai_message.sent",
        subject_type="AiMessageDraft",
        subject_id=draft.id,
        request_id=_request_id(request),
    )
    response.headers["Cache-Control"] = "no-store"
    return _msg_draft_read(draft)


@router.post(
    "/tenants/{tenant_id}/patient-education/questions",
    response_model=PatientEducationRead,
    status_code=201,
)
def ask_patient_education(
    tenant_id: str,
    body: PatientEducationAskWrite,
    request: Request,
    response: Response,
    user: User = Depends(get_current_user),
    membership: TenantMembership = Depends(require_role("patient")),
    session: Session = Depends(get_session),
) -> PatientEducationRead:
    if membership.tenant_id != tenant_id:
        raise ApiError("TENANT_NOT_FOUND", "Tenant not found.", 404)
    bundle = build_clinical_ai_adapter().generate_patient_education(question=body.question)
    gen = _record_generation(
        session,
        tenant_id=tenant_id,
        user=user,
        module="education",
        patient_id=user.id,
        source_references=bundle.source_references,
        usage_metadata={"escalated": bundle.escalate},
    )
    row = PatientEducationSession(
        tenant_id=tenant_id,
        patient_id=user.id,
        topic=bundle.topic,
        question=body.question.strip(),
        answer=bundle.answer,
        source_references=bundle.source_references,
        status="escalated" if bundle.escalate else "answered",
        escalated=bundle.escalate,
        ai_generation_id=gen.id,
    )
    session.add(row)
    session.flush()
    append_audit_event(
        session,
        actor_user_id=user.id,
        tenant_id=tenant_id,
        action="education.answered",
        subject_type="PatientEducationSession",
        subject_id=row.id,
        request_id=_request_id(request),
    )
    response.headers["Cache-Control"] = "no-store"
    return PatientEducationRead(
        education_id=row.id,
        topic=row.topic,
        question=row.question,
        answer=row.answer,
        source_references=row.source_references or [],
        escalated=row.escalated,
        status=row.status,
        created_at=row.created_at,
    )


@router.get(
    "/tenants/{tenant_id}/patient-education/sources",
    response_model=list[dict[str, object]],
)
def list_education_sources(
    tenant_id: str,
    response: Response,
    user: User = Depends(get_current_user),
    membership: TenantMembership = Depends(require_role("patient", "tenant_admin", "staff", "provider")),
) -> list[dict[str, object]]:
    if membership.tenant_id != tenant_id:
        raise ApiError("TENANT_NOT_FOUND", "Tenant not found.", 404)
    response.headers["Cache-Control"] = "no-store"
    return [
        {
            "source_id": "hmx-edu-lab-a1c-v1",
            "title": "Approved lab education — HbA1c overview",
            "version": "1.0",
            "reviewed": "2026-01-15",
        },
        {
            "source_id": "hmx-edu-portal-v1",
            "title": "Healthomatix patient guide",
            "version": "1.0",
        },
        {
            "source_id": "hmx-edu-safety-v1",
            "title": "Healthomatix safety policy",
            "version": "1.0",
        },
    ]


@router.post(
    "/tenants/{tenant_id}/follow-up-plans/{plan_id}/ai/suggest-tasks",
    response_model=CareTaskSuggestRead,
)
def suggest_care_tasks(
    tenant_id: str,
    plan_id: str,
    request: Request,
    response: Response,
    user: User = Depends(get_current_user),
    membership: TenantMembership = Depends(require_role("tenant_admin", "staff", "provider")),
    session: Session = Depends(get_session),
) -> CareTaskSuggestRead:
    if membership.tenant_id != tenant_id:
        raise ApiError("TENANT_NOT_FOUND", "Tenant not found.", 404)
    plan = session.execute(
        select(FollowUpPlan).where(FollowUpPlan.tenant_id == tenant_id, FollowUpPlan.id == plan_id)
    ).scalar_one_or_none()
    if plan is None:
        raise ApiError("FOLLOW_UP_NOT_FOUND", "Follow-up plan not found.", 404)
    if plan.status not in {"approved", "published"}:
        raise ApiError(
            "FOLLOW_UP_NOT_APPROVED",
            "Suggest tasks only from clinician-approved follow-up plans.",
            409,
        )
    require_patient_consent(
        session,
        tenant_id=tenant_id,
        patient_id=plan.patient_id,
        actor=user,
        membership=membership,
        request_id=_request_id(request),
    )
    suggestions = build_clinical_ai_adapter().suggest_care_tasks(
        instructions=plan.instructions,
        existing_tasks=list(plan.tasks or []),
    )
    gen = _record_generation(
        session,
        tenant_id=tenant_id,
        user=user,
        module="care_tasks",
        patient_id=plan.patient_id,
        output_reference=f"FollowUpPlan/{plan.id}",
        usage_metadata={"suggestion_count": len(suggestions)},
    )
    response.headers["Cache-Control"] = "no-store"
    return CareTaskSuggestRead(suggestions=suggestions, generation_id=gen.id)


@router.post(
    "/tenants/{tenant_id}/follow-up-plans/{plan_id}/tasks",
    response_model=CareTaskRead,
    status_code=201,
)
def create_care_task(
    tenant_id: str,
    plan_id: str,
    body: CareTaskCreateWrite,
    request: Request,
    response: Response,
    user: User = Depends(get_current_user),
    membership: TenantMembership = Depends(require_role("tenant_admin", "staff", "provider")),
    session: Session = Depends(get_session),
) -> CareTaskRead:
    if membership.tenant_id != tenant_id:
        raise ApiError("TENANT_NOT_FOUND", "Tenant not found.", 404)
    plan = session.execute(
        select(FollowUpPlan).where(FollowUpPlan.tenant_id == tenant_id, FollowUpPlan.id == plan_id)
    ).scalar_one_or_none()
    if plan is None:
        raise ApiError("FOLLOW_UP_NOT_FOUND", "Follow-up plan not found.", 404)
    if plan.status not in {"approved", "published"}:
        raise ApiError("FOLLOW_UP_NOT_APPROVED", "Tasks require an approved follow-up plan.", 409)
    if body.idempotency_key:
        existing = session.execute(
            select(CareCoordinationTask).where(
                CareCoordinationTask.tenant_id == tenant_id,
                CareCoordinationTask.follow_up_plan_id == plan_id,
                CareCoordinationTask.idempotency_key == body.idempotency_key,
            )
        ).scalar_one_or_none()
        if existing:
            response.headers["Cache-Control"] = "no-store"
            return _care_task_read(existing)
    require_patient_consent(
        session,
        tenant_id=tenant_id,
        patient_id=plan.patient_id,
        actor=user,
        membership=membership,
        request_id=_request_id(request),
    )
    task = CareCoordinationTask(
        tenant_id=tenant_id,
        patient_id=plan.patient_id,
        follow_up_plan_id=plan.id,
        encounter_id=plan.encounter_id,
        task_category=body.task_category,
        description=body.description.strip(),
        assigned_role=body.assigned_role,
        status="open",
        approval_reference=f"FollowUpPlan/{plan.id}",
        idempotency_key=body.idempotency_key,
    )
    session.add(task)
    session.flush()
    session.add(
        WorkflowAutomationExecution(
            tenant_id=tenant_id,
            automation_type="care_task.created",
            trigger_event_id=f"follow_up.{plan.id}",
            target_entity_type="CareCoordinationTask",
            target_entity_id=task.id,
            status="completed",
        )
    )
    append_audit_event(
        session,
        actor_user_id=user.id,
        tenant_id=tenant_id,
        action="care_task.created",
        subject_type="CareCoordinationTask",
        subject_id=task.id,
        request_id=_request_id(request),
    )
    response.headers["Cache-Control"] = "no-store"
    return _care_task_read(task)


@router.get(
    "/tenants/{tenant_id}/patients/me/care-tasks",
    response_model=list[CareTaskRead],
)
def list_my_care_tasks(
    tenant_id: str,
    response: Response,
    user: User = Depends(get_current_user),
    membership: TenantMembership = Depends(require_role("patient")),
    session: Session = Depends(get_session),
) -> list[CareTaskRead]:
    if membership.tenant_id != tenant_id:
        raise ApiError("TENANT_NOT_FOUND", "Tenant not found.", 404)
    rows = session.execute(
        select(CareCoordinationTask)
        .where(
            CareCoordinationTask.tenant_id == tenant_id,
            CareCoordinationTask.patient_id == user.id,
            CareCoordinationTask.status.in_(("open", "in_progress", "completed")),
        )
        .order_by(CareCoordinationTask.created_at.desc())
        .limit(50)
    ).scalars()
    response.headers["Cache-Control"] = "no-store"
    return [_care_task_read(row) for row in rows]


@router.patch(
    "/tenants/{tenant_id}/care-tasks/{task_id}",
    response_model=CareTaskRead,
)
def patch_care_task(
    tenant_id: str,
    task_id: str,
    body: CareTaskPatchWrite,
    response: Response,
    user: User = Depends(get_current_user),
    membership: TenantMembership = Depends(
        require_role("tenant_admin", "staff", "provider", "patient")
    ),
    session: Session = Depends(get_session),
) -> CareTaskRead:
    if membership.tenant_id != tenant_id:
        raise ApiError("TENANT_NOT_FOUND", "Tenant not found.", 404)
    task = session.execute(
        select(CareCoordinationTask).where(
            CareCoordinationTask.tenant_id == tenant_id, CareCoordinationTask.id == task_id
        )
    ).scalar_one_or_none()
    if task is None:
        raise ApiError("TASK_NOT_FOUND", "Care task not found.", 404)
    if membership.role == "patient" and task.patient_id != user.id:
        raise ApiError("TASK_NOT_FOUND", "Care task not found.", 404)
    task.status = body.status
    if body.status == "completed":
        task.completed_at = utcnow()
    session.flush()
    response.headers["Cache-Control"] = "no-store"
    return _care_task_read(task)


@router.get(
    "/tenants/{tenant_id}/analytics/workflow",
    response_model=WorkflowAnalyticsRead,
)
def workflow_analytics(
    tenant_id: str,
    response: Response,
    user: User = Depends(get_current_user),
    membership: TenantMembership = Depends(require_role("tenant_admin", "staff", "provider")),
    session: Session = Depends(get_session),
) -> WorkflowAnalyticsRead:
    if membership.tenant_id != tenant_id:
        raise ApiError("TENANT_NOT_FOUND", "Tenant not found.", 404)

    def _count(model, *filters) -> int:
        return int(
            session.execute(
                select(func.count()).select_from(model).where(*filters)
            ).scalar_one()
        )

    notes_total = _count(ClinicalNote, ClinicalNote.tenant_id == tenant_id)
    notes_draft = _count(
        ClinicalNote, ClinicalNote.tenant_id == tenant_id, ClinicalNote.status == "draft"
    )
    notes_signed = _count(
        ClinicalNote, ClinicalNote.tenant_id == tenant_id, ClinicalNote.status == "signed"
    )
    scribe_total = _count(AiScribeSession, AiScribeSession.tenant_id == tenant_id)
    gen_total = _count(AiGeneration, AiGeneration.tenant_id == tenant_id)
    msg_drafts = _count(AiMessageDraft, AiMessageDraft.tenant_id == tenant_id)
    msg_sent = _count(
        AiMessageDraft, AiMessageDraft.tenant_id == tenant_id, AiMessageDraft.status == "sent"
    )
    plans = _count(FollowUpPlan, FollowUpPlan.tenant_id == tenant_id)
    tasks_open = _count(
        CareCoordinationTask,
        CareCoordinationTask.tenant_id == tenant_id,
        CareCoordinationTask.status.in_(("open", "in_progress")),
    )
    tasks_done = _count(
        CareCoordinationTask,
        CareCoordinationTask.tenant_id == tenant_id,
        CareCoordinationTask.status == "completed",
    )
    automations = _count(
        WorkflowAutomationExecution, WorkflowAutomationExecution.tenant_id == tenant_id
    )
    threads = _count(MessageThread, MessageThread.tenant_id == tenant_id)

    response.headers["Cache-Control"] = "no-store"
    return WorkflowAnalyticsRead(
        documentation={
            "clinical_notes": notes_total,
            "draft_notes": notes_draft,
            "signed_notes": notes_signed,
        },
        ai_scribe={
            "scribe_sessions": scribe_total,
            "ai_generations": gen_total,
            "provider": "fake",
        },
        messaging={
            "threads": threads,
            "ai_message_drafts": msg_drafts,
            "ai_drafts_sent": msg_sent,
        },
        care_coordination={
            "follow_up_plans": plans,
            "open_tasks": tasks_open,
            "completed_tasks": tasks_done,
            "automations": automations,
        },
        ai_operations={
            "model_identifier": MODEL_ID,
            "prompt_version": PROMPT_VERSION,
            "estimated_cost": 0,
            "note": "Operational metadata only; no PHI in analytics payloads.",
        },
    )


@router.get(
    "/tenants/{tenant_id}/ai/generations",
    response_model=list[AiGenerationRead],
)
def list_ai_generations(
    tenant_id: str,
    response: Response,
    user: User = Depends(get_current_user),
    membership: TenantMembership = Depends(require_role("tenant_admin", "staff", "provider")),
    session: Session = Depends(get_session),
) -> list[AiGenerationRead]:
    if membership.tenant_id != tenant_id:
        raise ApiError("TENANT_NOT_FOUND", "Tenant not found.", 404)
    rows = session.execute(
        select(AiGeneration)
        .where(AiGeneration.tenant_id == tenant_id)
        .order_by(AiGeneration.created_at.desc())
        .limit(50)
    ).scalars()
    response.headers["Cache-Control"] = "no-store"
    return [
        AiGenerationRead(
            generation_id=row.id,
            module=row.module,
            model_identifier=row.model_identifier,
            prompt_version=row.prompt_version,
            status=row.status,
            source_references=row.source_references or [],
            output_reference=row.output_reference,
            usage_metadata=row.usage_metadata or {},
            created_at=row.created_at,
        )
        for row in rows
    ]
