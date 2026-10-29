"""Telehealth sessions: /sessions (Phase 4). Messaging remains under /threads."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit import append_audit_event
from app.auth import ApiError, get_current_user
from app.authorization import require_role
from app.consent_gate import require_patient_consent
from app.consultation.fhir_sync import create_visit_encounter
from app.consultation.video_port import VideoRoom, build_video_adapter
from app.db import get_session
from app.fhir_models import VideoSession
from app.models import (
    Appointment,
    ProviderAvailability,
    TenantMembership,
    User,
    utcnow,
)
from app.schemas import (
    SessionCompleteWrite,
    SessionCreate,
    SessionJoinRead,
    SessionRead,
)

router = APIRouter(prefix="/api/v1", tags=["consultation"])


def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", "")


def _to_read(row: VideoSession) -> SessionRead:
    return SessionRead(
        session_id=row.id,
        appointment_id=row.appointment_id,
        status=row.status,
        video_provider=row.video_provider,
        room_id=row.room_id,
        patient_user_id=row.patient_user_id,
        provider_user_id=row.provider_user_id,
        clinic_patient_id=row.clinic_patient_id,
        encounter_id=row.encounter_id,
        follow_up_plan=row.follow_up_plan,
        created_at=row.created_at,
        started_at=row.started_at,
        ended_at=row.ended_at,
    )


def _appointment_context(
    session: Session, *, tenant_id: str, appointment_id: str
) -> tuple[Appointment, ProviderAvailability]:
    appointment = session.execute(
        select(Appointment).where(
            Appointment.tenant_id == tenant_id,
            Appointment.id == appointment_id,
            Appointment.status == "booked",
        )
    ).scalar_one_or_none()
    if appointment is None:
        raise ApiError("APPOINTMENT_NOT_FOUND", "Appointment not found.", 404)
    slot = session.execute(
        select(ProviderAvailability).where(
            ProviderAvailability.tenant_id == tenant_id,
            ProviderAvailability.id == appointment.availability_id,
        )
    ).scalar_one_or_none()
    if slot is None:
        raise ApiError("SLOT_UNAVAILABLE", "Appointment slot is missing.", 404)
    return appointment, slot


def _authorize_session_access(
    *,
    user: User,
    membership: TenantMembership,
    row: VideoSession,
) -> str:
    if membership.role == "patient":
        if user.id != row.patient_user_id:
            raise ApiError("SESSION_NOT_FOUND", "Session not found.", 404)
        return "patient"
    if membership.role == "provider":
        if user.id != row.provider_user_id:
            raise ApiError("SESSION_NOT_FOUND", "Session not found.", 404)
        return "clinician"
    if membership.role in {"staff", "tenant_admin"}:
        return "clinician"
    raise ApiError("ROLE_REQUIRED", "You are not authorized for this action.", 403)


@router.post(
    "/tenants/{tenant_id}/sessions",
    response_model=SessionRead,
    status_code=201,
)
def create_session(
    tenant_id: str,
    body: SessionCreate,
    request: Request,
    response: Response,
    user: User = Depends(get_current_user),
    membership: TenantMembership = Depends(
        require_role("tenant_admin", "staff", "provider", "patient")
    ),
    session: Session = Depends(get_session),
) -> SessionRead:
    if membership.tenant_id != tenant_id:
        raise ApiError("TENANT_NOT_FOUND", "Tenant not found.", 404)
    appointment, slot = _appointment_context(
        session, tenant_id=tenant_id, appointment_id=body.appointment_id
    )
    if membership.role == "patient" and user.id != appointment.patient_user_id:
        raise ApiError("APPOINTMENT_NOT_FOUND", "Appointment not found.", 404)
    if membership.role == "provider" and user.id != slot.provider_user_id:
        raise ApiError("APPOINTMENT_NOT_FOUND", "Appointment not found.", 404)

    require_patient_consent(
        session,
        tenant_id=tenant_id,
        patient_id=appointment.patient_user_id,
        actor=user,
        membership=membership,
        request_id=_request_id(request),
        subject_type="Appointment",
        subject_id=appointment.id,
    )

    existing = session.execute(
        select(VideoSession).where(
            VideoSession.tenant_id == tenant_id,
            VideoSession.appointment_id == appointment.id,
        )
    ).scalar_one_or_none()
    if existing is not None:
        response.headers["Cache-Control"] = "no-store"
        response.status_code = 200
        return _to_read(existing)

    video = build_video_adapter()
    # provisional id for room naming
    from app.models import new_id

    session_id = new_id()
    room = video.create_room(session_id=session_id, appointment_id=appointment.id)
    row = VideoSession(
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
    session.add(row)
    session.flush()
    append_audit_event(
        session,
        actor_user_id=user.id,
        tenant_id=tenant_id,
        action="session.created",
        subject_type="VideoSession",
        subject_id=row.id,
        request_id=_request_id(request),
    )
    response.headers["Cache-Control"] = "no-store"
    return _to_read(row)


@router.get("/tenants/{tenant_id}/sessions/{session_id}", response_model=SessionRead)
def read_session(
    tenant_id: str,
    session_id: str,
    request: Request,
    response: Response,
    user: User = Depends(get_current_user),
    membership: TenantMembership = Depends(
        require_role("tenant_admin", "staff", "provider", "patient")
    ),
    session: Session = Depends(get_session),
) -> SessionRead:
    if membership.tenant_id != tenant_id:
        raise ApiError("TENANT_NOT_FOUND", "Tenant not found.", 404)
    row = session.execute(
        select(VideoSession).where(
            VideoSession.tenant_id == tenant_id,
            VideoSession.id == session_id,
        )
    ).scalar_one_or_none()
    if row is None:
        raise ApiError("SESSION_NOT_FOUND", "Session not found.", 404)
    _authorize_session_access(user=user, membership=membership, row=row)
    require_patient_consent(
        session,
        tenant_id=tenant_id,
        patient_id=row.patient_user_id,
        actor=user,
        membership=membership,
        request_id=_request_id(request),
        subject_type="VideoSession",
        subject_id=row.id,
    )
    response.headers["Cache-Control"] = "no-store"
    return _to_read(row)


@router.post(
    "/tenants/{tenant_id}/sessions/{session_id}/join",
    response_model=SessionJoinRead,
)
def join_session(
    tenant_id: str,
    session_id: str,
    request: Request,
    response: Response,
    user: User = Depends(get_current_user),
    membership: TenantMembership = Depends(
        require_role("tenant_admin", "staff", "provider", "patient")
    ),
    session: Session = Depends(get_session),
) -> SessionJoinRead:
    if membership.tenant_id != tenant_id:
        raise ApiError("TENANT_NOT_FOUND", "Tenant not found.", 404)
    row = session.execute(
        select(VideoSession).where(
            VideoSession.tenant_id == tenant_id,
            VideoSession.id == session_id,
        )
    ).scalar_one_or_none()
    if row is None:
        raise ApiError("SESSION_NOT_FOUND", "Session not found.", 404)
    if row.status == "completed":
        raise ApiError("SESSION_COMPLETED", "This visit has already been completed.", 409)
    if row.status == "cancelled":
        raise ApiError("SESSION_CANCELLED", "This visit was cancelled.", 409)

    role = _authorize_session_access(user=user, membership=membership, row=row)
    require_patient_consent(
        session,
        tenant_id=tenant_id,
        patient_id=row.patient_user_id,
        actor=user,
        membership=membership,
        request_id=_request_id(request),
        subject_type="VideoSession",
        subject_id=row.id,
    )

    if row.status == "scheduled":
        row.status = "live"
        row.started_at = utcnow()
        session.flush()

    video = build_video_adapter()
    room = VideoRoom(
        provider=row.video_provider,
        room_id=row.room_id,
        join_url=f"https://video.healthomatix.local/rooms/{row.room_id}",
    )
    token = video.participant_token(
        room=room,
        user_id=user.id,
        role=role,
        display_name=role,
    )
    append_audit_event(
        session,
        actor_user_id=user.id,
        tenant_id=tenant_id,
        action="session.joined",
        subject_type="VideoSession",
        subject_id=row.id,
        request_id=_request_id(request),
    )
    response.headers["Cache-Control"] = "no-store"
    return SessionJoinRead(
        session_id=row.id,
        appointment_id=row.appointment_id,
        status=row.status,
        video_provider=row.video_provider,
        room_id=row.room_id,
        role=token.role,
        token=token.token,
        join_url=token.join_url,
        expires_in_seconds=token.expires_in_seconds,
        patient_user_id=row.patient_user_id,
        provider_user_id=row.provider_user_id,
        clinic_patient_id=row.clinic_patient_id,
        encounter_id=row.encounter_id,
        follow_up_plan=row.follow_up_plan,
    )


@router.post(
    "/tenants/{tenant_id}/sessions/{session_id}/complete",
    response_model=SessionRead,
)
def complete_session(
    tenant_id: str,
    session_id: str,
    body: SessionCompleteWrite,
    request: Request,
    response: Response,
    user: User = Depends(get_current_user),
    membership: TenantMembership = Depends(require_role("tenant_admin", "staff", "provider")),
    session: Session = Depends(get_session),
) -> SessionRead:
    """Clinician ends the visit, records follow-up, and writes a FHIR Encounter."""
    if membership.tenant_id != tenant_id:
        raise ApiError("TENANT_NOT_FOUND", "Tenant not found.", 404)
    row = session.execute(
        select(VideoSession).where(
            VideoSession.tenant_id == tenant_id,
            VideoSession.id == session_id,
        )
    ).scalar_one_or_none()
    if row is None:
        raise ApiError("SESSION_NOT_FOUND", "Session not found.", 404)
    if membership.role == "provider" and user.id != row.provider_user_id:
        raise ApiError("SESSION_NOT_FOUND", "Session not found.", 404)
    if row.status == "completed":
        raise ApiError("SESSION_COMPLETED", "Visit already completed.", 409)

    require_patient_consent(
        session,
        tenant_id=tenant_id,
        patient_id=row.patient_user_id,
        actor=user,
        membership=membership,
        request_id=_request_id(request),
        subject_type="VideoSession",
        subject_id=row.id,
    )

    started = row.started_at or utcnow()
    ended = utcnow()
    encounter = create_visit_encounter(
        session,
        tenant_id=tenant_id,
        patient_id=row.patient_user_id,
        provider_user_id=row.provider_user_id,
        appointment_id=row.appointment_id,
        session_id=row.id,
        started_at=started,
        ended_at=ended,
        follow_up_plan=body.follow_up_plan,
        actor_user_id=user.id,
    )
    row.status = "completed"
    row.ended_at = ended
    row.started_at = started
    row.follow_up_plan = body.follow_up_plan.strip()
    row.encounter_id = encounter["id"]
    session.flush()

    append_audit_event(
        session,
        actor_user_id=user.id,
        tenant_id=tenant_id,
        action="session.completed",
        subject_type="Encounter",
        subject_id=encounter["id"],
        request_id=_request_id(request),
    )
    response.headers["Cache-Control"] = "no-store"
    return _to_read(row)
