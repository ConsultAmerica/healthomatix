"""V1.4 waiting room, clinical notes, and follow-up publish workflows."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit import append_audit_event
from app.auth import ApiError, get_current_user
from app.authorization import require_role
from app.consent_gate import require_patient_consent
from app.consultation.video_port import build_video_adapter
from app.consultation_routes import _appointment_context
from app.db import get_session
from app.fhir_models import (
    ClinicalNote,
    ClinicalNoteVersion,
    FollowUpPlan,
    VideoSession,
    WaitingRoomEntry,
)
from app.models import TenantMembership, User, new_id, utcnow
from app.schemas import (
    ClinicalNoteAmendWrite,
    ClinicalNoteRead,
    ClinicalNoteWrite,
    FollowUpPlanRead,
    FollowUpPlanWrite,
    WaitingRoomEntryRead,
)

router = APIRouter(prefix="/api/v1", tags=["telehealth-workflow"])


def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", "")


def _waiting_read(row: WaitingRoomEntry) -> WaitingRoomEntryRead:
    return WaitingRoomEntryRead(
        entry_id=row.id,
        appointment_id=row.appointment_id,
        session_id=row.session_id,
        patient_user_id=row.patient_user_id,
        provider_user_id=row.provider_user_id,
        clinic_patient_id=row.clinic_patient_id,
        status=row.status,
        checked_in_at=row.checked_in_at,
        admitted_at=row.admitted_at,
        left_at=row.left_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _note_read(row: ClinicalNote) -> ClinicalNoteRead:
    return ClinicalNoteRead(
        note_id=row.id,
        patient_id=row.patient_id,
        author_user_id=row.author_user_id,
        session_id=row.session_id,
        encounter_id=row.encounter_id,
        appointment_id=row.appointment_id,
        note_type=row.note_type,
        subjective=row.subjective,
        objective=row.objective,
        assessment=row.assessment,
        plan=row.plan,
        status=row.status,
        version=row.version,
        ai_assisted=row.ai_assisted,
        source_draft_id=row.source_draft_id,
        signed_by_user_id=row.signed_by_user_id,
        signed_at=row.signed_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _follow_up_read(row: FollowUpPlan) -> FollowUpPlanRead:
    return FollowUpPlanRead(
        plan_id=row.id,
        patient_id=row.patient_id,
        provider_user_id=row.provider_user_id,
        session_id=row.session_id,
        encounter_id=row.encounter_id,
        appointment_id=row.appointment_id,
        status=row.status,
        instructions=row.instructions,
        tasks=list(row.tasks or []),
        approved_by_user_id=row.approved_by_user_id,
        approved_at=row.approved_at,
        published_at=row.published_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _snapshot(note: ClinicalNote) -> dict:
    return {
        "subjective": note.subjective,
        "objective": note.objective,
        "assessment": note.assessment,
        "plan": note.plan,
        "status": note.status,
        "version": note.version,
    }


@router.post(
    "/tenants/{tenant_id}/appointments/{appointment_id}/check-in",
    response_model=WaitingRoomEntryRead,
)
def check_in(
    tenant_id: str,
    appointment_id: str,
    request: Request,
    response: Response,
    user: User = Depends(get_current_user),
    membership: TenantMembership = Depends(require_role("patient")),
    session: Session = Depends(get_session),
) -> WaitingRoomEntryRead:
    if membership.tenant_id != tenant_id:
        raise ApiError("TENANT_NOT_FOUND", "Tenant not found.", 404)
    appointment, slot = _appointment_context(session, tenant_id=tenant_id, appointment_id=appointment_id)
    if user.id != appointment.patient_user_id:
        raise ApiError("APPOINTMENT_NOT_FOUND", "Appointment not found.", 404)

    video_row = session.execute(
        select(VideoSession).where(
            VideoSession.tenant_id == tenant_id,
            VideoSession.appointment_id == appointment.id,
        )
    ).scalar_one_or_none()
    if video_row is None:
        session_id = new_id()
        room = build_video_adapter().create_room(
            session_id=session_id, appointment_id=appointment.id
        )
        video_row = VideoSession(
            id=session_id,
            tenant_id=tenant_id,
            appointment_id=appointment.id,
            patient_user_id=appointment.patient_user_id,
            provider_user_id=slot.provider_user_id,
            clinic_patient_id=appointment.clinic_patient_id,
            status="scheduled",
            video_provider=room.provider,
            room_id=room.room_id,
        )
        session.add(video_row)
        session.flush()

    existing = session.execute(
        select(WaitingRoomEntry).where(
            WaitingRoomEntry.tenant_id == tenant_id,
            WaitingRoomEntry.appointment_id == appointment_id,
        )
    ).scalar_one_or_none()
    now = utcnow()
    if existing is None:
        existing = WaitingRoomEntry(
            tenant_id=tenant_id,
            appointment_id=appointment_id,
            session_id=video_row.id,
            patient_user_id=appointment.patient_user_id,
            provider_user_id=slot.provider_user_id,
            clinic_patient_id=appointment.clinic_patient_id,
            status="waiting",
            checked_in_at=now,
        )
        session.add(existing)
    else:
        if existing.status in {"left", "completed"}:
            existing.status = "waiting"
            existing.left_at = None
        elif existing.status == "not_checked_in":
            existing.status = "waiting"
        existing.checked_in_at = existing.checked_in_at or now
        existing.session_id = existing.session_id or video_row.id
        existing.updated_at = now
    session.flush()
    append_audit_event(
        session,
        actor_user_id=user.id,
        tenant_id=tenant_id,
        action="waiting_room.checked_in",
        subject_type="WaitingRoomEntry",
        subject_id=existing.id,
        request_id=_request_id(request),
    )
    response.headers["Cache-Control"] = "no-store"
    return _waiting_read(existing)


@router.get(
    "/tenants/{tenant_id}/appointments/{appointment_id}/waiting-room",
    response_model=WaitingRoomEntryRead | None,
)
def get_waiting_room(
    tenant_id: str,
    appointment_id: str,
    request: Request,
    response: Response,
    user: User = Depends(get_current_user),
    membership: TenantMembership = Depends(
        require_role("tenant_admin", "staff", "provider", "patient")
    ),
    session: Session = Depends(get_session),
) -> WaitingRoomEntryRead | None:
    if membership.tenant_id != tenant_id:
        raise ApiError("TENANT_NOT_FOUND", "Tenant not found.", 404)
    appointment, slot = _appointment_context(session, tenant_id=tenant_id, appointment_id=appointment_id)
    if membership.role == "patient" and user.id != appointment.patient_user_id:
        raise ApiError("APPOINTMENT_NOT_FOUND", "Appointment not found.", 404)
    if membership.role == "provider" and user.id != slot.provider_user_id:
        raise ApiError("APPOINTMENT_NOT_FOUND", "Appointment not found.", 404)
    response.headers["Cache-Control"] = "no-store"
    row = session.execute(
        select(WaitingRoomEntry).where(
            WaitingRoomEntry.tenant_id == tenant_id,
            WaitingRoomEntry.appointment_id == appointment_id,
        )
    ).scalar_one_or_none()
    return _waiting_read(row) if row else None


@router.get("/tenants/{tenant_id}/waiting-room", response_model=list[WaitingRoomEntryRead])
def list_waiting_room(
    tenant_id: str,
    request: Request,
    response: Response,
    user: User = Depends(get_current_user),
    membership: TenantMembership = Depends(require_role("tenant_admin", "staff", "provider")),
    session: Session = Depends(get_session),
) -> list[WaitingRoomEntryRead]:
    if membership.tenant_id != tenant_id:
        raise ApiError("TENANT_NOT_FOUND", "Tenant not found.", 404)
    stmt = select(WaitingRoomEntry).where(
        WaitingRoomEntry.tenant_id == tenant_id,
        WaitingRoomEntry.status.in_(("waiting", "admitted", "checked_in")),
    )
    if membership.role == "provider":
        stmt = stmt.where(WaitingRoomEntry.provider_user_id == user.id)
    rows = session.execute(
        stmt.order_by(WaitingRoomEntry.created_at.asc()).limit(50)
    ).scalars()
    response.headers["Cache-Control"] = "no-store"
    return [_waiting_read(row) for row in rows]


@router.post(
    "/tenants/{tenant_id}/appointments/{appointment_id}/admit",
    response_model=WaitingRoomEntryRead,
)
def admit_patient(
    tenant_id: str,
    appointment_id: str,
    request: Request,
    response: Response,
    user: User = Depends(get_current_user),
    membership: TenantMembership = Depends(require_role("tenant_admin", "staff", "provider")),
    session: Session = Depends(get_session),
) -> WaitingRoomEntryRead:
    if membership.tenant_id != tenant_id:
        raise ApiError("TENANT_NOT_FOUND", "Tenant not found.", 404)
    appointment, slot = _appointment_context(session, tenant_id=tenant_id, appointment_id=appointment_id)
    if membership.role == "provider" and user.id != slot.provider_user_id:
        raise ApiError("APPOINTMENT_NOT_FOUND", "Appointment not found.", 404)
    row = session.execute(
        select(WaitingRoomEntry).where(
            WaitingRoomEntry.tenant_id == tenant_id,
            WaitingRoomEntry.appointment_id == appointment_id,
        )
    ).scalar_one_or_none()
    if row is None or row.status not in {"waiting", "checked_in"}:
        raise ApiError("WAITING_ROOM_EMPTY", "Patient is not waiting to be admitted.", 409)
    row.status = "admitted"
    row.admitted_at = utcnow()
    row.admitted_by_user_id = user.id
    row.updated_at = utcnow()
    if row.session_id:
        video = session.get(VideoSession, row.session_id)
        if video and video.status == "scheduled":
            # Keep scheduled until join; admission unlocks join for UX.
            pass
    session.flush()
    append_audit_event(
        session,
        actor_user_id=user.id,
        tenant_id=tenant_id,
        action="waiting_room.admitted",
        subject_type="WaitingRoomEntry",
        subject_id=row.id,
        request_id=_request_id(request),
    )
    response.headers["Cache-Control"] = "no-store"
    return _waiting_read(row)


@router.post(
    "/tenants/{tenant_id}/appointments/{appointment_id}/leave-waiting-room",
    response_model=WaitingRoomEntryRead,
)
def leave_waiting_room(
    tenant_id: str,
    appointment_id: str,
    request: Request,
    response: Response,
    user: User = Depends(get_current_user),
    membership: TenantMembership = Depends(require_role("patient")),
    session: Session = Depends(get_session),
) -> WaitingRoomEntryRead:
    if membership.tenant_id != tenant_id:
        raise ApiError("TENANT_NOT_FOUND", "Tenant not found.", 404)
    appointment, _slot = _appointment_context(session, tenant_id=tenant_id, appointment_id=appointment_id)
    if user.id != appointment.patient_user_id:
        raise ApiError("APPOINTMENT_NOT_FOUND", "Appointment not found.", 404)
    row = session.execute(
        select(WaitingRoomEntry).where(
            WaitingRoomEntry.tenant_id == tenant_id,
            WaitingRoomEntry.appointment_id == appointment_id,
        )
    ).scalar_one_or_none()
    if row is None:
        raise ApiError("WAITING_ROOM_EMPTY", "No waiting room entry.", 404)
    row.status = "left"
    row.left_at = utcnow()
    row.updated_at = utcnow()
    session.flush()
    append_audit_event(
        session,
        actor_user_id=user.id,
        tenant_id=tenant_id,
        action="waiting_room.left",
        subject_type="WaitingRoomEntry",
        subject_id=row.id,
        request_id=_request_id(request),
    )
    response.headers["Cache-Control"] = "no-store"
    return _waiting_read(row)


@router.post(
    "/tenants/{tenant_id}/clinical-notes",
    response_model=ClinicalNoteRead,
    status_code=201,
)
def create_or_update_clinical_note(
    tenant_id: str,
    body: ClinicalNoteWrite,
    request: Request,
    response: Response,
    user: User = Depends(get_current_user),
    membership: TenantMembership = Depends(require_role("tenant_admin", "staff", "provider")),
    session: Session = Depends(get_session),
) -> ClinicalNoteRead:
    if membership.tenant_id != tenant_id:
        raise ApiError("TENANT_NOT_FOUND", "Tenant not found.", 404)
    require_patient_consent(
        session,
        tenant_id=tenant_id,
        patient_id=body.patient_id,
        actor=user,
        membership=membership,
        request_id=_request_id(request),
        subject_type="Patient",
        subject_id=body.patient_id,
    )
    note = ClinicalNote(
        tenant_id=tenant_id,
        patient_id=body.patient_id,
        author_user_id=user.id,
        session_id=body.session_id,
        appointment_id=body.appointment_id,
        subjective=body.subjective,
        objective=body.objective,
        assessment=body.assessment,
        plan=body.plan,
        status="draft",
        version=1,
        ai_assisted=body.ai_assisted,
        source_draft_id=body.source_draft_id,
    )
    session.add(note)
    session.flush()
    session.add(
        ClinicalNoteVersion(
            tenant_id=tenant_id,
            note_id=note.id,
            version=1,
            content_snapshot=_snapshot(note),
            editor_user_id=user.id,
            change_reason="created",
        )
    )
    session.flush()
    append_audit_event(
        session,
        actor_user_id=user.id,
        tenant_id=tenant_id,
        action="clinical_note.created",
        subject_type="ClinicalNote",
        subject_id=note.id,
        request_id=_request_id(request),
    )
    response.headers["Cache-Control"] = "no-store"
    return _note_read(note)


@router.patch(
    "/tenants/{tenant_id}/clinical-notes/{note_id}",
    response_model=ClinicalNoteRead,
)
def patch_clinical_note(
    tenant_id: str,
    note_id: str,
    body: ClinicalNoteWrite,
    request: Request,
    response: Response,
    user: User = Depends(get_current_user),
    membership: TenantMembership = Depends(require_role("tenant_admin", "staff", "provider")),
    session: Session = Depends(get_session),
) -> ClinicalNoteRead:
    if membership.tenant_id != tenant_id:
        raise ApiError("TENANT_NOT_FOUND", "Tenant not found.", 404)
    note = session.execute(
        select(ClinicalNote).where(ClinicalNote.tenant_id == tenant_id, ClinicalNote.id == note_id)
    ).scalar_one_or_none()
    if note is None:
        raise ApiError("NOTE_NOT_FOUND", "Clinical note not found.", 404)
    if note.status == "signed":
        raise ApiError("NOTE_SIGNED", "Signed notes cannot be edited. Use amend.", 409)
    if body.expected_version is not None and body.expected_version != note.version:
        raise ApiError("NOTE_VERSION_CONFLICT", "Note was updated elsewhere. Reload and retry.", 409)
    require_patient_consent(
        session,
        tenant_id=tenant_id,
        patient_id=note.patient_id,
        actor=user,
        membership=membership,
        request_id=_request_id(request),
        subject_type="ClinicalNote",
        subject_id=note.id,
    )
    note.subjective = body.subjective
    note.objective = body.objective
    note.assessment = body.assessment
    note.plan = body.plan
    note.ai_assisted = body.ai_assisted or note.ai_assisted
    note.version += 1
    note.updated_at = utcnow()
    session.add(
        ClinicalNoteVersion(
            tenant_id=tenant_id,
            note_id=note.id,
            version=note.version,
            content_snapshot=_snapshot(note),
            editor_user_id=user.id,
            change_reason="autosave",
        )
    )
    session.flush()
    response.headers["Cache-Control"] = "no-store"
    return _note_read(note)


@router.post(
    "/tenants/{tenant_id}/clinical-notes/{note_id}/sign",
    response_model=ClinicalNoteRead,
)
def sign_clinical_note(
    tenant_id: str,
    note_id: str,
    request: Request,
    response: Response,
    user: User = Depends(get_current_user),
    membership: TenantMembership = Depends(require_role("provider", "tenant_admin")),
    session: Session = Depends(get_session),
) -> ClinicalNoteRead:
    if membership.tenant_id != tenant_id:
        raise ApiError("TENANT_NOT_FOUND", "Tenant not found.", 404)
    note = session.execute(
        select(ClinicalNote).where(ClinicalNote.tenant_id == tenant_id, ClinicalNote.id == note_id)
    ).scalar_one_or_none()
    if note is None:
        raise ApiError("NOTE_NOT_FOUND", "Clinical note not found.", 404)
    if note.status == "signed":
        raise ApiError("NOTE_SIGNED", "Note already signed.", 409)
    if not (note.subjective or note.objective or note.assessment or note.plan):
        raise ApiError("NOTE_INCOMPLETE", "Add clinical content before signing.", 422)
    require_patient_consent(
        session,
        tenant_id=tenant_id,
        patient_id=note.patient_id,
        actor=user,
        membership=membership,
        request_id=_request_id(request),
        subject_type="ClinicalNote",
        subject_id=note.id,
    )
    note.status = "signed"
    note.signed_by_user_id = user.id
    note.signed_at = utcnow()
    note.version += 1
    note.updated_at = utcnow()
    session.add(
        ClinicalNoteVersion(
            tenant_id=tenant_id,
            note_id=note.id,
            version=note.version,
            content_snapshot=_snapshot(note),
            editor_user_id=user.id,
            change_reason="signed",
        )
    )
    session.flush()
    append_audit_event(
        session,
        actor_user_id=user.id,
        tenant_id=tenant_id,
        action="clinical_note.signed",
        subject_type="ClinicalNote",
        subject_id=note.id,
        request_id=_request_id(request),
    )
    response.headers["Cache-Control"] = "no-store"
    return _note_read(note)


@router.post(
    "/tenants/{tenant_id}/clinical-notes/{note_id}/amend",
    response_model=ClinicalNoteRead,
)
def amend_clinical_note(
    tenant_id: str,
    note_id: str,
    body: ClinicalNoteAmendWrite,
    request: Request,
    response: Response,
    user: User = Depends(get_current_user),
    membership: TenantMembership = Depends(require_role("provider", "tenant_admin")),
    session: Session = Depends(get_session),
) -> ClinicalNoteRead:
    if membership.tenant_id != tenant_id:
        raise ApiError("TENANT_NOT_FOUND", "Tenant not found.", 404)
    note = session.execute(
        select(ClinicalNote).where(ClinicalNote.tenant_id == tenant_id, ClinicalNote.id == note_id)
    ).scalar_one_or_none()
    if note is None:
        raise ApiError("NOTE_NOT_FOUND", "Clinical note not found.", 404)
    if note.status != "signed":
        raise ApiError("NOTE_NOT_SIGNED", "Only signed notes can be amended.", 409)
    if body.expected_version != note.version:
        raise ApiError("NOTE_VERSION_CONFLICT", "Note was updated elsewhere. Reload and retry.", 409)
    require_patient_consent(
        session,
        tenant_id=tenant_id,
        patient_id=note.patient_id,
        actor=user,
        membership=membership,
        request_id=_request_id(request),
        subject_type="ClinicalNote",
        subject_id=note.id,
    )
    if body.subjective is not None:
        note.subjective = body.subjective
    if body.objective is not None:
        note.objective = body.objective
    if body.assessment is not None:
        note.assessment = body.assessment
    if body.plan is not None:
        note.plan = body.plan
    note.version += 1
    note.updated_at = utcnow()
    session.add(
        ClinicalNoteVersion(
            tenant_id=tenant_id,
            note_id=note.id,
            version=note.version,
            content_snapshot=_snapshot(note),
            editor_user_id=user.id,
            change_reason=body.change_reason,
        )
    )
    session.flush()
    append_audit_event(
        session,
        actor_user_id=user.id,
        tenant_id=tenant_id,
        action="clinical_note.amended",
        subject_type="ClinicalNote",
        subject_id=note.id,
        request_id=_request_id(request),
    )
    response.headers["Cache-Control"] = "no-store"
    return _note_read(note)


@router.post(
    "/tenants/{tenant_id}/follow-up-plans",
    response_model=FollowUpPlanRead,
    status_code=201,
)
def create_follow_up_plan(
    tenant_id: str,
    body: FollowUpPlanWrite,
    request: Request,
    response: Response,
    user: User = Depends(get_current_user),
    membership: TenantMembership = Depends(require_role("tenant_admin", "staff", "provider")),
    session: Session = Depends(get_session),
) -> FollowUpPlanRead:
    if membership.tenant_id != tenant_id:
        raise ApiError("TENANT_NOT_FOUND", "Tenant not found.", 404)
    require_patient_consent(
        session,
        tenant_id=tenant_id,
        patient_id=body.patient_id,
        actor=user,
        membership=membership,
        request_id=_request_id(request),
        subject_type="Patient",
        subject_id=body.patient_id,
    )
    plan = FollowUpPlan(
        tenant_id=tenant_id,
        patient_id=body.patient_id,
        provider_user_id=user.id,
        session_id=body.session_id,
        appointment_id=body.appointment_id,
        status="draft",
        instructions=body.instructions.strip(),
        tasks=body.tasks,
    )
    session.add(plan)
    session.flush()
    append_audit_event(
        session,
        actor_user_id=user.id,
        tenant_id=tenant_id,
        action="follow_up.created",
        subject_type="FollowUpPlan",
        subject_id=plan.id,
        request_id=_request_id(request),
    )
    response.headers["Cache-Control"] = "no-store"
    return _follow_up_read(plan)


@router.post(
    "/tenants/{tenant_id}/follow-up-plans/{plan_id}/approve",
    response_model=FollowUpPlanRead,
)
def approve_follow_up_plan(
    tenant_id: str,
    plan_id: str,
    request: Request,
    response: Response,
    user: User = Depends(get_current_user),
    membership: TenantMembership = Depends(require_role("provider", "tenant_admin")),
    session: Session = Depends(get_session),
) -> FollowUpPlanRead:
    if membership.tenant_id != tenant_id:
        raise ApiError("TENANT_NOT_FOUND", "Tenant not found.", 404)
    plan = session.execute(
        select(FollowUpPlan).where(FollowUpPlan.tenant_id == tenant_id, FollowUpPlan.id == plan_id)
    ).scalar_one_or_none()
    if plan is None:
        raise ApiError("FOLLOW_UP_NOT_FOUND", "Follow-up plan not found.", 404)
    if plan.status not in {"draft", "approved"}:
        raise ApiError("FOLLOW_UP_STATE", "Plan cannot be approved from its current state.", 409)
    require_patient_consent(
        session,
        tenant_id=tenant_id,
        patient_id=plan.patient_id,
        actor=user,
        membership=membership,
        request_id=_request_id(request),
        subject_type="FollowUpPlan",
        subject_id=plan.id,
    )
    plan.status = "approved"
    plan.approved_by_user_id = user.id
    plan.approved_at = utcnow()
    plan.updated_at = utcnow()
    session.flush()
    append_audit_event(
        session,
        actor_user_id=user.id,
        tenant_id=tenant_id,
        action="follow_up.approved",
        subject_type="FollowUpPlan",
        subject_id=plan.id,
        request_id=_request_id(request),
    )
    response.headers["Cache-Control"] = "no-store"
    return _follow_up_read(plan)


@router.post(
    "/tenants/{tenant_id}/follow-up-plans/{plan_id}/publish",
    response_model=FollowUpPlanRead,
)
def publish_follow_up_plan(
    tenant_id: str,
    plan_id: str,
    request: Request,
    response: Response,
    user: User = Depends(get_current_user),
    membership: TenantMembership = Depends(require_role("provider", "tenant_admin")),
    session: Session = Depends(get_session),
) -> FollowUpPlanRead:
    if membership.tenant_id != tenant_id:
        raise ApiError("TENANT_NOT_FOUND", "Tenant not found.", 404)
    plan = session.execute(
        select(FollowUpPlan).where(FollowUpPlan.tenant_id == tenant_id, FollowUpPlan.id == plan_id)
    ).scalar_one_or_none()
    if plan is None:
        raise ApiError("FOLLOW_UP_NOT_FOUND", "Follow-up plan not found.", 404)
    if plan.status != "approved":
        raise ApiError("FOLLOW_UP_NOT_APPROVED", "Approve the plan before publishing to the patient.", 409)
    require_patient_consent(
        session,
        tenant_id=tenant_id,
        patient_id=plan.patient_id,
        actor=user,
        membership=membership,
        request_id=_request_id(request),
        subject_type="FollowUpPlan",
        subject_id=plan.id,
    )
    plan.status = "published"
    plan.published_at = utcnow()
    plan.updated_at = utcnow()
    session.flush()
    append_audit_event(
        session,
        actor_user_id=user.id,
        tenant_id=tenant_id,
        action="follow_up.published",
        subject_type="FollowUpPlan",
        subject_id=plan.id,
        request_id=_request_id(request),
    )
    response.headers["Cache-Control"] = "no-store"
    return _follow_up_read(plan)


@router.get(
    "/tenants/{tenant_id}/patients/me/follow-up-plans",
    response_model=list[FollowUpPlanRead],
)
def list_my_published_follow_ups(
    tenant_id: str,
    response: Response,
    user: User = Depends(get_current_user),
    membership: TenantMembership = Depends(require_role("patient")),
    session: Session = Depends(get_session),
) -> list[FollowUpPlanRead]:
    if membership.tenant_id != tenant_id:
        raise ApiError("TENANT_NOT_FOUND", "Tenant not found.", 404)
    rows = session.execute(
        select(FollowUpPlan)
        .where(
            FollowUpPlan.tenant_id == tenant_id,
            FollowUpPlan.patient_id == user.id,
            FollowUpPlan.status == "published",
        )
        .order_by(FollowUpPlan.published_at.desc())
        .limit(50)
    ).scalars()
    response.headers["Cache-Control"] = "no-store"
    return [_follow_up_read(row) for row in rows]
