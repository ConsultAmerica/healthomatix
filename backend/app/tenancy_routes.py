from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.audit import append_audit_event
from app.auth import ApiError, get_current_user
from app.authorization import require_role
from app.db import get_session
from app.models import (
    Appointment,
    ClinicInvitation,
    ClinicLocation,
    ClinicPatient,
    MedicalDocument,
    MessageThread,
    PatientProfile,
    ProviderProfile,
    Tenant,
    TenantMembership,
    User,
)
from app.schemas import (
    ClinicOnboardingWrite,
    ClinicPatientDetailRead,
    ClinicPatientRead,
    ClinicRead,
    InvitationAcceptWrite,
    InvitationCreated,
    InvitationRead,
    InvitationWrite,
    LocationRead,
    LocationWrite,
    MemberRead,
)

router = APIRouter(prefix="/api/v1")


def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", "")


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


@router.post("/tenants", response_model=ClinicRead, status_code=201)
def onboard_clinic(
    body: ClinicOnboardingWrite,
    request: Request,
    response: Response,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> ClinicRead:
    try:
        ZoneInfo(body.timezone)
    except (ValueError, ZoneInfoNotFoundError) as error:
        raise ApiError("TIMEZONE_INVALID", "Use a valid IANA timezone.", 422) from error

    tenant = Tenant(slug=body.slug, display_name=body.display_name)
    membership = TenantMembership(user_id=user.id, role="tenant_admin")
    location = ClinicLocation(
        name=body.location_name,
        timezone=body.timezone,
        status="active",
    )
    try:
        with session.begin_nested():
            session.add(tenant)
            session.flush()
            membership.tenant_id = tenant.id
            location.tenant_id = tenant.id
            session.add_all((membership, location))
            session.flush()
            append_audit_event(
                session,
                actor_user_id=user.id,
                tenant_id=tenant.id,
                action="clinic.created",
                subject_type="tenant",
                subject_id=tenant.id,
                request_id=_request_id(request),
            )
    except IntegrityError as error:
        raise ApiError("CLINIC_SLUG_UNAVAILABLE", "Clinic slug is already in use.", 409) from error
    response.headers["Cache-Control"] = "no-store"
    return ClinicRead(
        tenant_id=tenant.id,
        slug=tenant.slug,
        display_name=tenant.display_name,
        role=membership.role,
        location_id=location.id,
        location_name=location.name,
        timezone=location.timezone,
    )


@router.get("/tenants/{tenant_id}/members", response_model=list[MemberRead])
def list_members(
    tenant_id: str,
    response: Response,
    membership: TenantMembership = Depends(require_role("tenant_admin")),
    session: Session = Depends(get_session),
) -> list[MemberRead]:
    if membership.tenant_id != tenant_id:
        raise ApiError("TENANT_NOT_FOUND", "Tenant not found.", 404)
    response.headers["Cache-Control"] = "no-store"
    rows = session.execute(
        select(TenantMembership)
        .where(TenantMembership.tenant_id == tenant_id)
        .order_by(TenantMembership.created_at.desc())
    ).scalars()
    return [
        MemberRead(
            user_id=row.user_id,
            role=row.role,
            status=row.status,
            created_at=row.created_at,
        )
        for row in rows
    ]


@router.get(
    "/tenants/{tenant_id}/patients",
    response_model=list[ClinicPatientRead],
)
def list_clinic_patients(
    tenant_id: str,
    response: Response,
    membership: TenantMembership = Depends(require_role("tenant_admin", "staff")),
    session: Session = Depends(get_session),
) -> list[ClinicPatientRead]:
    if membership.tenant_id != tenant_id:
        raise ApiError("TENANT_NOT_FOUND", "Tenant not found.", 404)
    response.headers["Cache-Control"] = "no-store"
    rows = session.execute(
        select(ClinicPatient)
        .where(
            ClinicPatient.tenant_id == tenant_id,
            ClinicPatient.status == "active",
        )
        .order_by(ClinicPatient.created_at.desc())
        .limit(100)
    ).scalars()
    return [
        ClinicPatientRead(
            clinic_patient_id=row.id,
            chart_number=row.chart_number,
            status=row.status,
            created_at=row.created_at,
        )
        for row in rows
    ]


@router.get(
    "/tenants/{tenant_id}/patients/{clinic_patient_id}",
    response_model=ClinicPatientDetailRead,
)
def get_clinic_patient(
    tenant_id: str,
    clinic_patient_id: str,
    response: Response,
    membership: TenantMembership = Depends(require_role("tenant_admin", "staff")),
    session: Session = Depends(get_session),
) -> ClinicPatientDetailRead:
    if membership.tenant_id != tenant_id:
        raise ApiError("TENANT_NOT_FOUND", "Tenant not found.", 404)
    row = session.execute(
        select(ClinicPatient).where(
            ClinicPatient.tenant_id == tenant_id,
            ClinicPatient.id == clinic_patient_id,
            ClinicPatient.status == "active",
        )
    ).scalar_one_or_none()
    if row is None:
        raise ApiError("PATIENT_NOT_FOUND", "Patient not found.", 404)

    document_count = session.execute(
        select(func.count())
        .select_from(MedicalDocument)
        .where(
            MedicalDocument.tenant_id == tenant_id,
            MedicalDocument.clinic_patient_id == row.id,
            MedicalDocument.lifecycle_state != "deleted",
        )
    ).scalar_one()
    open_thread_count = session.execute(
        select(func.count())
        .select_from(MessageThread)
        .where(
            MessageThread.tenant_id == tenant_id,
            MessageThread.clinic_patient_id == row.id,
            MessageThread.status == "open",
        )
    ).scalar_one()
    upcoming_appointment_count = session.execute(
        select(func.count())
        .select_from(Appointment)
        .where(
            Appointment.tenant_id == tenant_id,
            Appointment.clinic_patient_id == row.id,
            Appointment.status == "booked",
        )
    ).scalar_one()

    response.headers["Cache-Control"] = "no-store"
    return ClinicPatientDetailRead(
        clinic_patient_id=row.id,
        chart_number=row.chart_number,
        status=row.status,
        created_at=row.created_at,
        document_count=int(document_count or 0),
        open_thread_count=int(open_thread_count or 0),
        upcoming_appointment_count=int(upcoming_appointment_count or 0),
    )


@router.post(
    "/tenants/{tenant_id}/invitations",
    response_model=InvitationCreated,
    status_code=201,
)
def create_invitation(
    tenant_id: str,
    body: InvitationWrite,
    request: Request,
    response: Response,
    user: User = Depends(get_current_user),
    membership: TenantMembership = Depends(require_role("tenant_admin", "staff")),
    session: Session = Depends(get_session),
) -> InvitationCreated:
    if membership.tenant_id != tenant_id:
        raise ApiError("TENANT_NOT_FOUND", "Tenant not found.", 404)
    if membership.role == "staff" and body.role != "patient":
        raise ApiError("ROLE_REQUIRED", "Clinic staff may only invite patients.", 403)
    code = secrets.token_urlsafe(32)
    now = datetime.now(UTC)
    invitation = ClinicInvitation(
        tenant_id=tenant_id,
        token_hash=hashlib.sha256(code.encode("utf-8")).hexdigest(),
        role=body.role,
        created_by_user_id=user.id,
        expires_at=now + timedelta(days=7),
    )
    with session.begin_nested():
        session.add(invitation)
        session.flush()
        append_audit_event(
            session,
            actor_user_id=user.id,
            tenant_id=tenant_id,
            action="clinic.invitation_created",
            subject_type="clinic_invitation",
            subject_id=invitation.id,
            request_id=_request_id(request),
        )
    response.headers["Cache-Control"] = "no-store"
    return InvitationCreated(
        invitation_id=invitation.id,
        role=invitation.role,
        invitation_code=code,
        expires_at=invitation.expires_at,
    )


@router.get(
    "/tenants/{tenant_id}/invitations",
    response_model=list[InvitationRead],
)
def list_invitations(
    tenant_id: str,
    response: Response,
    membership: TenantMembership = Depends(require_role("tenant_admin")),
    session: Session = Depends(get_session),
) -> list[InvitationRead]:
    if membership.tenant_id != tenant_id:
        raise ApiError("TENANT_NOT_FOUND", "Tenant not found.", 404)
    response.headers["Cache-Control"] = "no-store"
    rows = session.execute(
        select(ClinicInvitation)
        .where(ClinicInvitation.tenant_id == tenant_id)
        .order_by(ClinicInvitation.created_at.desc())
    ).scalars()
    now = datetime.now(UTC)
    return [
        InvitationRead(
            invitation_id=row.id,
            role=row.role,
            status=(
                "expired" if row.status == "pending" and _utc(row.expires_at) <= now else row.status
            ),
            expires_at=row.expires_at,
            created_at=row.created_at,
        )
        for row in rows
    ]


@router.delete("/tenants/{tenant_id}/invitations/{invitation_id}", status_code=204)
def revoke_invitation(
    tenant_id: str,
    invitation_id: str,
    request: Request,
    response: Response,
    user: User = Depends(get_current_user),
    membership: TenantMembership = Depends(require_role("tenant_admin")),
    session: Session = Depends(get_session),
) -> Response:
    if membership.tenant_id != tenant_id:
        raise ApiError("TENANT_NOT_FOUND", "Tenant not found.", 404)
    invitation = session.execute(
        select(ClinicInvitation)
        .where(
            ClinicInvitation.id == invitation_id,
            ClinicInvitation.tenant_id == tenant_id,
        )
        .with_for_update()
    ).scalar_one_or_none()
    if invitation is None or invitation.status != "pending":
        raise ApiError("INVITATION_NOT_FOUND", "Invitation not found.", 404)
    invitation.status = "revoked"
    append_audit_event(
        session,
        actor_user_id=user.id,
        tenant_id=tenant_id,
        action="clinic.invitation_revoked",
        subject_type="clinic_invitation",
        subject_id=invitation.id,
        request_id=_request_id(request),
    )
    response.headers["Cache-Control"] = "no-store"
    response.status_code = 204
    return response


@router.post("/invitations/accept", response_model=MemberRead)
def accept_invitation(
    body: InvitationAcceptWrite,
    request: Request,
    response: Response,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> MemberRead:
    token_hash = hashlib.sha256(body.invitation_code.encode("utf-8")).hexdigest()
    invitation = session.execute(
        select(ClinicInvitation)
        .join(Tenant, Tenant.id == ClinicInvitation.tenant_id)
        .where(
            ClinicInvitation.token_hash == token_hash,
            ClinicInvitation.status == "pending",
            Tenant.status == "active",
        )
        .with_for_update()
    ).scalar_one_or_none()
    if invitation is None:
        raise ApiError("INVITATION_NOT_FOUND", "Invitation is invalid or unavailable.", 404)
    if _utc(invitation.expires_at) <= datetime.now(UTC):
        raise ApiError("INVITATION_EXPIRED", "Invitation has expired.", 410)
    existing = session.execute(
        select(TenantMembership).where(
            TenantMembership.tenant_id == invitation.tenant_id,
            TenantMembership.user_id == user.id,
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise ApiError("MEMBERSHIP_EXISTS", "You already have a clinic membership.", 409)

    now = datetime.now(UTC)
    member = TenantMembership(
        tenant_id=invitation.tenant_id,
        user_id=user.id,
        role=invitation.role,
        status="active",
    )
    try:
        with session.begin_nested():
            session.add(member)
            if invitation.role == "patient":
                session.add(
                    ClinicPatient(
                        tenant_id=invitation.tenant_id,
                        patient_user_id=user.id,
                    )
                )
                if session.get(PatientProfile, user.id) is None:
                    session.add(PatientProfile(user_id=user.id))
            elif invitation.role == "provider":
                # Profiles are per user, so a provider joining a second clinic keeps theirs.
                if session.get(ProviderProfile, user.id) is None:
                    session.add(ProviderProfile(user_id=user.id, profile_status="pending"))
            invitation.status = "accepted"
            invitation.accepted_by_user_id = user.id
            invitation.accepted_at = now
            session.flush()
            append_audit_event(
                session,
                actor_user_id=user.id,
                tenant_id=invitation.tenant_id,
                action="clinic.invitation_accepted",
                subject_type="clinic_invitation",
                subject_id=invitation.id,
                request_id=_request_id(request),
            )
    except IntegrityError as error:
        raise ApiError(
            "INVITATION_ACCEPTANCE_CONFLICT",
            "Invitation could not be accepted; contact the clinic administrator.",
            409,
        ) from error
    response.headers["Cache-Control"] = "no-store"
    return MemberRead(
        user_id=member.user_id,
        role=member.role,
        status=member.status,
        created_at=member.created_at,
    )


@router.get("/tenants/{tenant_id}/locations", response_model=list[LocationRead])
def list_locations(
    tenant_id: str,
    response: Response,
    membership: TenantMembership = Depends(
        require_role("tenant_admin", "staff", "provider", "patient")
    ),
    session: Session = Depends(get_session),
) -> list[LocationRead]:
    if membership.tenant_id != tenant_id:
        raise ApiError("TENANT_NOT_FOUND", "Tenant not found.", 404)
    response.headers["Cache-Control"] = "no-store"
    rows = session.execute(
        select(ClinicLocation)
        .where(ClinicLocation.tenant_id == tenant_id, ClinicLocation.status == "active")
        .order_by(ClinicLocation.name)
    ).scalars()
    return [LocationRead(location_id=row.id, name=row.name, timezone=row.timezone) for row in rows]


@router.post(
    "/tenants/{tenant_id}/locations",
    response_model=LocationRead,
    status_code=201,
)
def create_location(
    tenant_id: str,
    body: LocationWrite,
    request: Request,
    response: Response,
    user: User = Depends(get_current_user),
    membership: TenantMembership = Depends(require_role("tenant_admin")),
    session: Session = Depends(get_session),
) -> LocationRead:
    if membership.tenant_id != tenant_id:
        raise ApiError("TENANT_NOT_FOUND", "Tenant not found.", 404)
    try:
        ZoneInfo(body.timezone)
    except (ValueError, ZoneInfoNotFoundError) as error:
        raise ApiError("TIMEZONE_INVALID", "Use a valid IANA timezone.", 422) from error
    location = ClinicLocation(
        tenant_id=tenant_id,
        name=body.name,
        timezone=body.timezone,
        status="active",
    )
    try:
        with session.begin_nested():
            session.add(location)
            session.flush()
            append_audit_event(
                session,
                actor_user_id=user.id,
                tenant_id=tenant_id,
                action="clinic.location_created",
                subject_type="clinic_location",
                subject_id=location.id,
                request_id=_request_id(request),
            )
    except IntegrityError as error:
        raise ApiError(
            "LOCATION_NAME_UNAVAILABLE", "Location name is already in use.", 409
        ) from error
    response.headers["Cache-Control"] = "no-store"
    return LocationRead(
        location_id=location.id,
        name=location.name,
        timezone=location.timezone,
    )
