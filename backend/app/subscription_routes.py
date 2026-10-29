"""V1.6 SaaS subscriptions, entitlements, and usage metering (separate from patient RCM)."""

from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit import append_audit_event
from app.auth import ApiError, get_current_user
from app.authorization import require_role
from app.db import get_session
from app.integrations.saas_billing_port import build_saas_billing_adapter
from app.models import TenantMembership, User, utcnow
from app.platform_routes import require_platform_admin
from app.rcm_models import (
    FeatureEntitlement,
    OrganizationSubscription,
    PlatformBillingEvent,
    SubscriptionPlan,
    UsageMeterEvent,
)
from app.schemas import (
    EntitlementRead,
    OrganizationSubscriptionRead,
    SubscriptionActivateWrite,
    SubscriptionPlanRead,
    UsageMeterRead,
    UsageMeterWrite,
)

router = APIRouter(prefix="/api/v1", tags=["saas-subscriptions"])

DEFAULT_PLANS = (
    ("starter", "Starter", "base", ["telehealth", "document_intelligence"]),
    ("professional", "Professional", "provider_seat", ["telehealth", "document_intelligence", "ai_scribe", "rcm", "analytics"]),
    ("enterprise", "Enterprise", "custom", ["telehealth", "document_intelligence", "ai_scribe", "rcm", "analytics", "multi_location"]),
)


def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", "")


def ensure_default_plans(session: Session) -> None:
    for code, name, model, features in DEFAULT_PLANS:
        existing = session.execute(
            select(SubscriptionPlan).where(SubscriptionPlan.plan_code == code)
        ).scalar_one_or_none()
        if existing is None:
            session.add(
                SubscriptionPlan(
                    plan_code=code,
                    name=name,
                    billing_model=model,
                    status="active",
                    feature_codes=list(features),
                )
            )
    session.flush()


def _apply_entitlements(session: Session, *, tenant_id: str, feature_codes: list[str]) -> None:
    for code in feature_codes:
        row = session.execute(
            select(FeatureEntitlement).where(
                FeatureEntitlement.tenant_id == tenant_id,
                FeatureEntitlement.feature_code == code,
            )
        ).scalar_one_or_none()
        if row is None:
            session.add(
                FeatureEntitlement(
                    tenant_id=tenant_id,
                    feature_code=code,
                    enabled=True,
                    effective_at=utcnow(),
                )
            )
        else:
            row.enabled = True
            row.effective_at = utcnow()
    session.flush()


@router.get("/platform/subscription-plans", response_model=list[SubscriptionPlanRead])
def list_plans(
    response: Response,
    _: User = Depends(require_platform_admin),
    session: Session = Depends(get_session),
) -> list[SubscriptionPlanRead]:
    ensure_default_plans(session)
    rows = session.execute(
        select(SubscriptionPlan).where(SubscriptionPlan.status == "active")
    ).scalars()
    response.headers["Cache-Control"] = "no-store"
    return [
        SubscriptionPlanRead(
            plan_id=row.id,
            plan_code=row.plan_code,
            name=row.name,
            billing_model=row.billing_model,
            feature_codes=list(row.feature_codes or []),
            status=row.status,
        )
        for row in rows
    ]


@router.post(
    "/tenants/{tenant_id}/subscriptions/activate",
    response_model=OrganizationSubscriptionRead,
    status_code=201,
)
def activate_subscription(
    tenant_id: str,
    body: SubscriptionActivateWrite,
    request: Request,
    response: Response,
    user: User = Depends(get_current_user),
    membership: TenantMembership = Depends(require_role("tenant_admin")),
    session: Session = Depends(get_session),
) -> OrganizationSubscriptionRead:
    if membership.tenant_id != tenant_id:
        raise ApiError("TENANT_NOT_FOUND", "Tenant not found.", 404)
    ensure_default_plans(session)
    plan = session.execute(
        select(SubscriptionPlan).where(
            SubscriptionPlan.plan_code == body.plan_code,
            SubscriptionPlan.status == "active",
        )
    ).scalar_one_or_none()
    if plan is None:
        raise ApiError("PLAN_NOT_FOUND", "Subscription plan not found.", 404)
    checkout = build_saas_billing_adapter().create_checkout(
        tenant_id=tenant_id, plan_code=plan.plan_code
    )
    today = date.today()
    sub = OrganizationSubscription(
        tenant_id=tenant_id,
        plan_id=plan.id,
        payment_provider_reference=checkout.provider_reference,
        status=checkout.status,
        billing_period_start=today,
        billing_period_end=today + timedelta(days=30),
    )
    session.add(sub)
    session.flush()
    _apply_entitlements(session, tenant_id=tenant_id, feature_codes=list(plan.feature_codes or []))
    session.add(
        PlatformBillingEvent(
            tenant_id=tenant_id,
            event_type="subscription.activated",
            provider_reference=checkout.provider_reference,
            status="recorded",
            payload={"invoice": checkout.invoice_reference, "plan_code": plan.plan_code},
        )
    )
    append_audit_event(
        session,
        actor_user_id=user.id,
        tenant_id=tenant_id,
        action="saas.subscription_activated",
        subject_type="OrganizationSubscription",
        subject_id=sub.id,
        request_id=_request_id(request),
    )
    response.headers["Cache-Control"] = "no-store"
    return OrganizationSubscriptionRead(
        subscription_id=sub.id,
        tenant_id=tenant_id,
        plan_code=plan.plan_code,
        status=sub.status,
        payment_provider_reference=sub.payment_provider_reference,
        billing_period_start=sub.billing_period_start,
        billing_period_end=sub.billing_period_end,
    )


@router.get(
    "/tenants/{tenant_id}/entitlements",
    response_model=list[EntitlementRead],
)
def list_entitlements(
    tenant_id: str,
    response: Response,
    user: User = Depends(get_current_user),
    membership: TenantMembership = Depends(require_role("tenant_admin", "staff", "provider")),
    session: Session = Depends(get_session),
) -> list[EntitlementRead]:
    if membership.tenant_id != tenant_id:
        raise ApiError("TENANT_NOT_FOUND", "Tenant not found.", 404)
    rows = session.execute(
        select(FeatureEntitlement).where(FeatureEntitlement.tenant_id == tenant_id)
    ).scalars()
    response.headers["Cache-Control"] = "no-store"
    return [
        EntitlementRead(
            feature_code=row.feature_code,
            enabled=row.enabled,
            limit_value=row.limit_value,
        )
        for row in rows
    ]


@router.post(
    "/tenants/{tenant_id}/usage-meter",
    response_model=UsageMeterRead,
    status_code=201,
)
def record_usage(
    tenant_id: str,
    body: UsageMeterWrite,
    response: Response,
    user: User = Depends(get_current_user),
    membership: TenantMembership = Depends(require_role("tenant_admin", "staff")),
    session: Session = Depends(get_session),
) -> UsageMeterRead:
    if membership.tenant_id != tenant_id:
        raise ApiError("TENANT_NOT_FOUND", "Tenant not found.", 404)
    existing = session.execute(
        select(UsageMeterEvent).where(
            UsageMeterEvent.tenant_id == tenant_id,
            UsageMeterEvent.source_event_id == body.source_event_id,
        )
    ).scalar_one_or_none()
    if existing:
        response.headers["Cache-Control"] = "no-store"
        return UsageMeterRead(
            meter_event_id=existing.id,
            meter_type=existing.meter_type,
            quantity=existing.quantity,
            source_event_id=existing.source_event_id,
            occurred_at=existing.occurred_at,
        )
    sub = session.execute(
        select(OrganizationSubscription)
        .where(
            OrganizationSubscription.tenant_id == tenant_id,
            OrganizationSubscription.status == "active",
        )
        .order_by(OrganizationSubscription.created_at.desc())
    ).scalars().first()
    row = UsageMeterEvent(
        tenant_id=tenant_id,
        subscription_id=sub.id if sub else None,
        meter_type=body.meter_type,
        quantity=body.quantity,
        source_event_id=body.source_event_id,
        billing_period_reference=body.billing_period_reference,
    )
    session.add(row)
    session.flush()
    response.headers["Cache-Control"] = "no-store"
    return UsageMeterRead(
        meter_event_id=row.id,
        meter_type=row.meter_type,
        quantity=row.quantity,
        source_event_id=row.source_event_id,
        occurred_at=row.occurred_at,
    )


@router.get("/platform/usage", response_model=list[dict[str, object]])
def platform_usage(
    response: Response,
    _: User = Depends(require_platform_admin),
    session: Session = Depends(get_session),
) -> list[dict[str, object]]:
    rows = session.execute(
        select(UsageMeterEvent).order_by(UsageMeterEvent.occurred_at.desc()).limit(100)
    ).scalars()
    response.headers["Cache-Control"] = "no-store"
    return [
        {
            "tenant_id": row.tenant_id,
            "meter_type": row.meter_type,
            "quantity": row.quantity,
            "source_event_id": row.source_event_id,
            "occurred_at": row.occurred_at.isoformat(),
        }
        for row in rows
    ]
