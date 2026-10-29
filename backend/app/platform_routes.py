from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.audit import append_audit_event
from app.auth import ApiError, get_current_user
from app.config import settings
from app.db import get_session
from app.models import (
    ClinicLocation,
    SupportAccessRequest,
    Tenant,
    TenantMembership,
    User,
)
from app.schemas import (
    PlatformTenantProvisionWrite,
    PlatformTenantRead,
    SupportAccessRequestRead,
    SupportAccessRequestWrite,
)
from app.security_hardening import enforce_platform_admin_mfa

router = APIRouter(prefix="/api/v1/platform")


def require_platform_admin(
    request: Request,
    user: User = Depends(get_current_user),
) -> User:
    if (user.issuer, user.subject) not in settings.platform_admin_identities:
        raise ApiError("PLATFORM_ADMIN_REQUIRED", "Platform administrator access required.", 403)
    enforce_platform_admin_mfa(request)
    return user


def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", "")


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


@router.get("/tenants", response_model=list[PlatformTenantRead])
def list_tenants(
    response: Response,
    _: User = Depends(require_platform_admin),
    session: Session = Depends(get_session),
) -> list[PlatformTenantRead]:
    response.headers["Cache-Control"] = "no-store"
    tenants = session.scalars(
        select(Tenant).order_by(Tenant.created_at.desc()).limit(100)
    ).all()
    return [
        PlatformTenantRead(
            tenant_id=tenant.id,
            slug=tenant.slug,
            display_name=tenant.display_name,
            status=tenant.status,
            created_at=tenant.created_at,
        )
        for tenant in tenants
    ]


@router.post("/tenants", response_model=PlatformTenantRead, status_code=201)
def provision_tenant(
    body: PlatformTenantProvisionWrite,
    request: Request,
    response: Response,
    administrator: User = Depends(require_platform_admin),
    session: Session = Depends(get_session),
) -> PlatformTenantRead:
    try:
        ZoneInfo(body.timezone)
    except (ValueError, ZoneInfoNotFoundError) as error:
        raise ApiError("TIMEZONE_INVALID", "Use a valid IANA timezone.", 422) from error

    owner = session.get(User, body.owner_user_id)
    if owner is None:
        raise ApiError("OWNER_NOT_FOUND", "Tenant owner not found.", 404)

    tenant = Tenant(slug=body.slug, display_name=body.display_name)
    location = ClinicLocation(
        name=body.location_name,
        timezone=body.timezone,
        status="active",
    )
    membership = TenantMembership(user_id=owner.id, role="tenant_admin")
    try:
        with session.begin_nested():
            session.add(tenant)
            session.flush()
            location.tenant_id = tenant.id
            membership.tenant_id = tenant.id
            session.add_all((location, membership))
            session.flush()
            append_audit_event(
                session,
                actor_user_id=administrator.id,
                tenant_id=tenant.id,
                action="platform.tenant_provisioned",
                subject_type="tenant",
                subject_id=tenant.id,
                request_id=_request_id(request),
            )
    except IntegrityError as error:
        raise ApiError("TENANT_SLUG_UNAVAILABLE", "Tenant slug is already in use.", 409) from error

    response.headers["Cache-Control"] = "no-store"
    return PlatformTenantRead(
        tenant_id=tenant.id,
        slug=tenant.slug,
        display_name=tenant.display_name,
        status=tenant.status,
        created_at=tenant.created_at,
    )


@router.get(
    "/support-access-requests",
    response_model=list[SupportAccessRequestRead],
)
def list_support_access_requests(
    response: Response,
    _: User = Depends(require_platform_admin),
    session: Session = Depends(get_session),
) -> list[SupportAccessRequestRead]:
    response.headers["Cache-Control"] = "no-store"
    requests = session.scalars(
        select(SupportAccessRequest)
        .order_by(SupportAccessRequest.created_at.desc())
        .limit(100)
    ).all()
    return [
        SupportAccessRequestRead(
            request_id=item.id,
            tenant_id=item.tenant_id,
            requested_by_user_id=item.requested_by_user_id,
            ticket_reference=item.ticket_reference,
            purpose=item.purpose,
            requested_until=_utc(item.requested_until),
            status=item.status,
            created_at=item.created_at,
        )
        for item in requests
    ]


@router.post(
    "/support-access-requests",
    response_model=SupportAccessRequestRead,
    status_code=201,
)
def create_support_access_request(
    body: SupportAccessRequestWrite,
    request: Request,
    response: Response,
    administrator: User = Depends(require_platform_admin),
    session: Session = Depends(get_session),
) -> SupportAccessRequestRead:
    tenant = session.get(Tenant, body.tenant_id)
    if tenant is None or tenant.status != "active":
        raise ApiError("TENANT_NOT_FOUND", "Tenant not found.", 404)

    support_request = SupportAccessRequest(
        tenant_id=tenant.id,
        requested_by_user_id=administrator.id,
        ticket_reference=body.ticket_reference,
        purpose=body.purpose,
        requested_until=body.requested_until,
    )
    with session.begin_nested():
        session.add(support_request)
        session.flush()
        append_audit_event(
            session,
            actor_user_id=administrator.id,
            tenant_id=tenant.id,
            action="platform.support_access.requested",
            subject_type="support_access_request",
            subject_id=support_request.id,
            request_id=_request_id(request),
        )

    response.headers["Cache-Control"] = "no-store"
    return SupportAccessRequestRead(
        request_id=support_request.id,
        tenant_id=support_request.tenant_id,
        requested_by_user_id=support_request.requested_by_user_id,
        ticket_reference=support_request.ticket_reference,
        purpose=support_request.purpose,
        requested_until=_utc(support_request.requested_until),
        status=support_request.status,
        created_at=support_request.created_at,
    )
