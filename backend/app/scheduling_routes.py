from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy import exists, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.audit import append_audit_event
from app.auth import ApiError, get_current_user
from app.authorization import require_clinic_patient, require_role
from app.config import settings
from app.db import get_session
from app.models import (
    Appointment,
    ClinicLocation,
    NotificationOutbox,
    ProviderAvailability,
    ProviderCredential,
    ProviderProfile,
    TenantMembership,
    User,
)
from app.schemas import (
    AppointmentCreate,
    AppointmentRead,
    AppointmentRescheduleWrite,
    AvailabilityRead,
    AvailabilityWrite,
)


def require_scheduling_enabled() -> None:
    if not settings.scheduling_enabled:
        raise ApiError(
            "SCHEDULING_DISABLED",
            "Scheduling is disabled until this environment is approved.",
            503,
        )


router = APIRouter(
    prefix="/api/v1",
    dependencies=[Depends(require_scheduling_enabled)],
)
_SLOT_DURATION = timedelta(minutes=30)


def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", "")


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _verified_provider(session: Session, tenant_id: str, provider_user_id: str) -> bool:
    return (
        session.execute(
            select(ProviderProfile.user_id)
            .join(
                TenantMembership,
                TenantMembership.user_id == ProviderProfile.user_id,
            )
            .where(
                TenantMembership.tenant_id == tenant_id,
                TenantMembership.user_id == provider_user_id,
                TenantMembership.role == "provider",
                TenantMembership.status == "active",
                ProviderProfile.profile_status == "active",
                exists(
                    select(ProviderCredential.id).where(
                        ProviderCredential.tenant_id == tenant_id,
                        ProviderCredential.provider_user_id == provider_user_id,
                        ProviderCredential.status == "verified",
                    )
                ),
            )
        ).scalar_one_or_none()
        is not None
    )


def _appointment_read(session: Session, appointment: Appointment) -> AppointmentRead:
    row = session.execute(
        select(
            ProviderAvailability,
            ProviderProfile.display_name,
            ClinicLocation.name,
            ClinicLocation.timezone,
        )
        .join(
            ProviderProfile,
            ProviderProfile.user_id == ProviderAvailability.provider_user_id,
        )
        .join(
            ClinicLocation,
            ClinicLocation.id == ProviderAvailability.location_id,
        )
        .where(
            ProviderAvailability.tenant_id == appointment.tenant_id,
            ProviderAvailability.id == appointment.availability_id,
        )
    ).one()
    slot, provider_name, location_name, timezone_name = row
    return AppointmentRead(
        appointment_id=appointment.id,
        tenant_id=appointment.tenant_id,
        clinic_patient_id=appointment.clinic_patient_id,
        provider_user_id=slot.provider_user_id,
        provider_name=provider_name,
        location_id=slot.location_id,
        location_name=location_name,
        timezone=timezone_name,
        starts_at=_utc(slot.starts_at),
        ends_at=_utc(slot.ends_at),
        status=appointment.status,
        created_at=_utc(appointment.created_at),
    )


def _availability_read(session: Session, slot: ProviderAvailability) -> AvailabilityRead:
    row = session.execute(
        select(
            ProviderProfile.display_name,
            ClinicLocation.name,
            ClinicLocation.timezone,
        )
        .select_from(ProviderAvailability)
        .join(
            ProviderProfile,
            ProviderProfile.user_id == ProviderAvailability.provider_user_id,
        )
        .join(
            ClinicLocation,
            (ClinicLocation.tenant_id == ProviderAvailability.tenant_id)
            & (ClinicLocation.id == ProviderAvailability.location_id),
        )
        .where(
            ProviderAvailability.tenant_id == slot.tenant_id,
            ProviderAvailability.id == slot.id,
        )
    ).one()
    provider_name, location_name, timezone_name = row
    return AvailabilityRead(
        availability_id=slot.id,
        tenant_id=slot.tenant_id,
        provider_user_id=slot.provider_user_id,
        provider_name=provider_name,
        location_id=slot.location_id,
        location_name=location_name,
        timezone=timezone_name,
        starts_at=_utc(slot.starts_at),
        ends_at=_utc(slot.ends_at),
        status=slot.status,
    )


def _check_date_range(
    from_time: datetime | None, to_time: datetime | None
) -> tuple[datetime, datetime]:
    now = datetime.now(UTC)
    if any(
        value is not None and (value.tzinfo is None or value.utcoffset() is None)
        for value in (from_time, to_time)
    ):
        raise ApiError("TIMEZONE_REQUIRED", "Date range timestamps must include a timezone.", 422)
    start = _utc(from_time) if from_time is not None else now
    end = _utc(to_time) if to_time is not None else start + timedelta(days=30)
    if end <= start or end - start > timedelta(days=31):
        raise ApiError(
            "INVALID_DATE_RANGE", "Date range must be positive and no longer than 31 days.", 422
        )
    return start, end


def _lock_slot(session: Session, tenant_id: str, availability_id: str) -> ProviderAvailability:
    slot = session.execute(
        select(ProviderAvailability)
        .where(
            ProviderAvailability.tenant_id == tenant_id,
            ProviderAvailability.id == availability_id,
        )
        .with_for_update()
    ).scalar_one_or_none()
    if slot is None:
        raise ApiError("AVAILABILITY_NOT_FOUND", "Availability not found.", 404)
    return slot


def _queue_notifications(
    session: Session,
    *,
    tenant_id: str,
    appointment_id: str,
    event_type: str,
    recipient_ids: set[str],
) -> None:
    for recipient_user_id in recipient_ids:
        session.add(
            NotificationOutbox(
                tenant_id=tenant_id,
                appointment_id=appointment_id,
                recipient_user_id=recipient_user_id,
                event_type=event_type,
            )
        )


@router.get(
    "/tenants/{tenant_id}/availability",
    response_model=list[AvailabilityRead],
)
def list_bookable_availability(
    tenant_id: str,
    response: Response,
    from_time: datetime | None = Query(default=None, alias="from"),
    to_time: datetime | None = Query(default=None, alias="to"),
    user: User = Depends(get_current_user),
    membership: TenantMembership = Depends(require_role("patient")),
    session: Session = Depends(get_session),
) -> list[AvailabilityRead]:
    if membership.tenant_id != tenant_id:
        raise ApiError("TENANT_NOT_FOUND", "Tenant not found.", 404)
    require_clinic_patient(session, tenant_id=tenant_id, user_id=user.id)
    start, end = _check_date_range(from_time, to_time)
    response.headers["Cache-Control"] = "no-store"
    slots = session.execute(
        select(ProviderAvailability)
        .join(
            ProviderProfile,
            ProviderProfile.user_id == ProviderAvailability.provider_user_id,
        )
        .join(
            TenantMembership,
            (TenantMembership.tenant_id == ProviderAvailability.tenant_id)
            & (TenantMembership.user_id == ProviderAvailability.provider_user_id),
        )
        .where(
            ProviderAvailability.tenant_id == tenant_id,
            ProviderAvailability.status == "open",
            ProviderAvailability.starts_at >= start,
            ProviderAvailability.starts_at < end,
            ProviderProfile.profile_status == "active",
            TenantMembership.role == "provider",
            TenantMembership.status == "active",
            exists(
                select(ProviderCredential.id).where(
                    ProviderCredential.tenant_id == tenant_id,
                    ProviderCredential.provider_user_id == ProviderAvailability.provider_user_id,
                    ProviderCredential.status == "verified",
                )
            ),
        )
        .order_by(ProviderAvailability.starts_at)
        .limit(200)
    ).scalars()
    return [_availability_read(session, slot) for slot in slots]


@router.get(
    "/tenants/{tenant_id}/providers/me/availability",
    response_model=list[AvailabilityRead],
)
def list_provider_availability(
    tenant_id: str,
    response: Response,
    from_time: datetime | None = Query(default=None, alias="from"),
    to_time: datetime | None = Query(default=None, alias="to"),
    user: User = Depends(get_current_user),
    membership: TenantMembership = Depends(require_role("provider")),
    session: Session = Depends(get_session),
) -> list[AvailabilityRead]:
    if membership.tenant_id != tenant_id:
        raise ApiError("TENANT_NOT_FOUND", "Tenant not found.", 404)
    start, end = _check_date_range(from_time, to_time)
    response.headers["Cache-Control"] = "no-store"
    slots = session.execute(
        select(ProviderAvailability)
        .where(
            ProviderAvailability.tenant_id == tenant_id,
            ProviderAvailability.provider_user_id == user.id,
            ProviderAvailability.starts_at >= start,
            ProviderAvailability.starts_at < end,
        )
        .order_by(ProviderAvailability.starts_at)
    ).scalars()
    return [_availability_read(session, slot) for slot in slots]


@router.post(
    "/tenants/{tenant_id}/providers/me/availability",
    response_model=AvailabilityRead,
    status_code=201,
)
def create_provider_availability(
    tenant_id: str,
    body: AvailabilityWrite,
    request: Request,
    response: Response,
    user: User = Depends(get_current_user),
    membership: TenantMembership = Depends(require_role("provider")),
    session: Session = Depends(get_session),
) -> AvailabilityRead:
    if membership.tenant_id != tenant_id:
        raise ApiError("TENANT_NOT_FOUND", "Tenant not found.", 404)
    if not _verified_provider(session, tenant_id, user.id):
        raise ApiError("PROVIDER_NOT_VERIFIED", "Verified provider status is required.", 403)
    starts_at = _utc(body.starts_at)
    if starts_at <= datetime.now(UTC):
        raise ApiError("AVAILABILITY_IN_PAST", "Availability must be in the future.", 422)
    location = session.execute(
        select(ClinicLocation).where(
            ClinicLocation.id == body.location_id,
            ClinicLocation.tenant_id == tenant_id,
            ClinicLocation.status == "active",
        )
    ).scalar_one_or_none()
    if location is None:
        raise ApiError("LOCATION_NOT_FOUND", "Location not found.", 404)
    slot = ProviderAvailability(
        tenant_id=tenant_id,
        provider_user_id=user.id,
        location_id=location.id,
        starts_at=starts_at,
        ends_at=starts_at + _SLOT_DURATION,
        status="open",
    )
    try:
        with session.begin_nested():
            session.add(slot)
            session.flush()
            append_audit_event(
                session,
                actor_user_id=user.id,
                tenant_id=tenant_id,
                action="provider.availability_created",
                subject_type="provider_availability",
                subject_id=slot.id,
                request_id=_request_id(request),
            )
    except IntegrityError as error:
        raise ApiError(
            "AVAILABILITY_CONFLICT",
            "An availability slot already exists for this start time.",
            409,
        ) from error
    response.headers["Cache-Control"] = "no-store"
    return _availability_read(session, slot)


@router.post(
    "/tenants/{tenant_id}/appointments",
    response_model=AppointmentRead,
    status_code=201,
)
def book_appointment(
    tenant_id: str,
    body: AppointmentCreate,
    request: Request,
    response: Response,
    user: User = Depends(get_current_user),
    membership: TenantMembership = Depends(require_role("patient")),
    session: Session = Depends(get_session),
) -> AppointmentRead:
    if membership.tenant_id != tenant_id:
        raise ApiError("TENANT_NOT_FOUND", "Tenant not found.", 404)
    clinic_patient = require_clinic_patient(session, tenant_id=tenant_id, user_id=user.id)
    existing = session.execute(
        select(Appointment).where(
            Appointment.tenant_id == tenant_id,
            Appointment.patient_user_id == user.id,
            Appointment.idempotency_key == body.idempotency_key,
        )
    ).scalar_one_or_none()
    if existing is not None:
        if existing.availability_id != body.availability_id:
            raise ApiError(
                "IDEMPOTENCY_KEY_REUSED", "Idempotency key was used for another slot.", 409
            )
        response.headers["Cache-Control"] = "no-store"
        response.status_code = 200
        return _appointment_read(session, existing)

    slot = _lock_slot(session, tenant_id, body.availability_id)
    existing = session.execute(
        select(Appointment).where(
            Appointment.tenant_id == tenant_id,
            Appointment.patient_user_id == user.id,
            Appointment.idempotency_key == body.idempotency_key,
        )
    ).scalar_one_or_none()
    if existing is not None:
        if existing.availability_id != body.availability_id:
            raise ApiError(
                "IDEMPOTENCY_KEY_REUSED", "Idempotency key was used for another slot.", 409
            )
        response.headers["Cache-Control"] = "no-store"
        response.status_code = 200
        return _appointment_read(session, existing)
    if slot.status != "open" or _utc(slot.starts_at) <= datetime.now(UTC):
        raise ApiError("SLOT_UNAVAILABLE", "Availability is no longer bookable.", 409)
    if not _verified_provider(session, tenant_id, slot.provider_user_id):
        raise ApiError("PROVIDER_NOT_VERIFIED", "Provider is no longer eligible for booking.", 409)
    appointment = Appointment(
        tenant_id=tenant_id,
        clinic_patient_id=clinic_patient.id,
        patient_user_id=user.id,
        availability_id=slot.id,
        idempotency_key=body.idempotency_key,
        status="booked",
    )
    try:
        with session.begin_nested():
            slot.status = "booked"
            session.add(appointment)
            session.flush()
            _queue_notifications(
                session,
                tenant_id=tenant_id,
                appointment_id=appointment.id,
                event_type="appointment.booked",
                recipient_ids={user.id, slot.provider_user_id},
            )
            append_audit_event(
                session,
                actor_user_id=user.id,
                tenant_id=tenant_id,
                action="appointment.booked",
                subject_type="appointment",
                subject_id=appointment.id,
                request_id=_request_id(request),
            )
    except IntegrityError as error:
        raise ApiError("SLOT_UNAVAILABLE", "Availability is no longer bookable.", 409) from error
    response.headers["Cache-Control"] = "no-store"
    return _appointment_read(session, appointment)


@router.get(
    "/tenants/{tenant_id}/patients/me/appointments",
    response_model=list[AppointmentRead],
)
def list_patient_appointments(
    tenant_id: str,
    response: Response,
    user: User = Depends(get_current_user),
    membership: TenantMembership = Depends(require_role("patient")),
    session: Session = Depends(get_session),
) -> list[AppointmentRead]:
    if membership.tenant_id != tenant_id:
        raise ApiError("TENANT_NOT_FOUND", "Tenant not found.", 404)
    require_clinic_patient(session, tenant_id=tenant_id, user_id=user.id)
    response.headers["Cache-Control"] = "no-store"
    rows = session.execute(
        select(Appointment)
        .where(
            Appointment.tenant_id == tenant_id,
            Appointment.patient_user_id == user.id,
        )
        .order_by(Appointment.created_at.desc())
        .limit(100)
    ).scalars()
    return [_appointment_read(session, row) for row in rows]


@router.get(
    "/tenants/{tenant_id}/appointments",
    response_model=list[AppointmentRead],
)
def list_clinic_appointments(
    tenant_id: str,
    response: Response,
    from_time: datetime | None = Query(default=None, alias="from"),
    to_time: datetime | None = Query(default=None, alias="to"),
    user: User = Depends(get_current_user),
    membership: TenantMembership = Depends(require_role("tenant_admin", "staff", "provider")),
    session: Session = Depends(get_session),
) -> list[AppointmentRead]:
    if membership.tenant_id != tenant_id:
        raise ApiError("TENANT_NOT_FOUND", "Tenant not found.", 404)
    start, end = _check_date_range(from_time, to_time)
    query = (
        select(Appointment)
        .join(
            ProviderAvailability,
            (ProviderAvailability.tenant_id == Appointment.tenant_id)
            & (ProviderAvailability.id == Appointment.availability_id),
        )
        .where(
            Appointment.tenant_id == tenant_id,
            Appointment.status == "booked",
            ProviderAvailability.starts_at >= start,
            ProviderAvailability.starts_at < end,
        )
    )
    if membership.role == "provider":
        query = query.where(ProviderAvailability.provider_user_id == user.id)
    rows = session.execute(query.order_by(ProviderAvailability.starts_at).limit(200)).scalars()
    response.headers["Cache-Control"] = "no-store"
    return [_appointment_read(session, row) for row in rows]


@router.post(
    "/tenants/{tenant_id}/appointments/{appointment_id}/cancel",
    response_model=AppointmentRead,
)
def cancel_appointment(
    tenant_id: str,
    appointment_id: str,
    request: Request,
    response: Response,
    user: User = Depends(get_current_user),
    membership: TenantMembership = Depends(require_role("patient")),
    session: Session = Depends(get_session),
) -> AppointmentRead:
    if membership.tenant_id != tenant_id:
        raise ApiError("TENANT_NOT_FOUND", "Tenant not found.", 404)
    appointment = session.execute(
        select(Appointment)
        .where(
            Appointment.id == appointment_id,
            Appointment.tenant_id == tenant_id,
            Appointment.patient_user_id == user.id,
        )
        .with_for_update()
    ).scalar_one_or_none()
    if appointment is None:
        raise ApiError("APPOINTMENT_NOT_FOUND", "Appointment not found.", 404)
    if appointment.status != "booked":
        raise ApiError("APPOINTMENT_NOT_BOOKED", "Appointment is not active.", 409)
    slot = _lock_slot(session, tenant_id, appointment.availability_id)
    appointment.status = "cancelled"
    slot.status = "open"
    append_audit_event(
        session,
        actor_user_id=user.id,
        tenant_id=tenant_id,
        action="appointment.cancelled",
        subject_type="appointment",
        subject_id=appointment.id,
        request_id=_request_id(request),
    )
    _queue_notifications(
        session,
        tenant_id=tenant_id,
        appointment_id=appointment.id,
        event_type="appointment.cancelled",
        recipient_ids={user.id, slot.provider_user_id},
    )
    response.headers["Cache-Control"] = "no-store"
    return _appointment_read(session, appointment)


@router.post(
    "/tenants/{tenant_id}/appointments/{appointment_id}/reschedule",
    response_model=AppointmentRead,
)
def reschedule_appointment(
    tenant_id: str,
    appointment_id: str,
    body: AppointmentRescheduleWrite,
    request: Request,
    response: Response,
    user: User = Depends(get_current_user),
    membership: TenantMembership = Depends(require_role("patient")),
    session: Session = Depends(get_session),
) -> AppointmentRead:
    if membership.tenant_id != tenant_id:
        raise ApiError("TENANT_NOT_FOUND", "Tenant not found.", 404)
    appointment = session.execute(
        select(Appointment)
        .where(
            Appointment.id == appointment_id,
            Appointment.tenant_id == tenant_id,
            Appointment.patient_user_id == user.id,
        )
        .with_for_update()
    ).scalar_one_or_none()
    if appointment is None:
        raise ApiError("APPOINTMENT_NOT_FOUND", "Appointment not found.", 404)
    if appointment.status != "booked":
        raise ApiError("APPOINTMENT_NOT_BOOKED", "Appointment is not active.", 409)
    if appointment.availability_id == body.availability_id:
        raise ApiError("SAME_AVAILABILITY", "Choose a different appointment time.", 409)
    locked_slots = {
        slot_id: _lock_slot(session, tenant_id, slot_id)
        for slot_id in sorted((appointment.availability_id, body.availability_id))
    }
    old_slot = locked_slots[appointment.availability_id]
    new_slot = locked_slots[body.availability_id]
    if new_slot.status != "open" or _utc(new_slot.starts_at) <= datetime.now(UTC):
        raise ApiError("SLOT_UNAVAILABLE", "Availability is no longer bookable.", 409)
    if not _verified_provider(session, tenant_id, new_slot.provider_user_id):
        raise ApiError("PROVIDER_NOT_VERIFIED", "Provider is no longer eligible for booking.", 409)
    try:
        with session.begin_nested():
            old_slot.status = "open"
            new_slot.status = "booked"
            appointment.availability_id = new_slot.id
            session.flush()
            _queue_notifications(
                session,
                tenant_id=tenant_id,
                appointment_id=appointment.id,
                event_type="appointment.rescheduled",
                recipient_ids={user.id, old_slot.provider_user_id, new_slot.provider_user_id},
            )
            append_audit_event(
                session,
                actor_user_id=user.id,
                tenant_id=tenant_id,
                action="appointment.rescheduled",
                subject_type="appointment",
                subject_id=appointment.id,
                request_id=_request_id(request),
            )
    except IntegrityError as error:
        raise ApiError("SLOT_UNAVAILABLE", "Availability is no longer bookable.", 409) from error
    response.headers["Cache-Control"] = "no-store"
    return _appointment_read(session, appointment)
