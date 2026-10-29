"""Health Trends: /trends and /insights (consent-gated)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy.orm import Session

from app.audit import append_audit_event
from app.auth import ApiError, get_current_user
from app.authorization import require_role
from app.consent_gate import require_patient_consent
from app.db import get_session
from app.intelligence.insights_port import TrendSample, build_insights_adapter
from app.models import TenantMembership, User
from app.roles import CLINICIAN_READ_ROLES
from app.schemas import (
    InsightFlagRead,
    TrendInsightsRead,
    TrendSeriesRead,
    TrendTestRead,
)
from app.trends_service import (
    build_trend_series,
    list_patient_trend_tests,
    list_supported_tests,
    normalize_test_code,
)

router = APIRouter(prefix="/api/v1", tags=["trends"])

INSIGHT_DISCLAIMER = (
    "These notes are educational and meant to support a conversation with your "
    "clinician. They are not a diagnosis, prognosis, or treatment recommendation."
)


def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", "")


def _resolve_patient_id(
    *,
    membership: TenantMembership,
    user: User,
    patient_id: str | None,
) -> str:
    if membership.role == "patient":
        if patient_id and patient_id != user.id:
            raise ApiError("CONSENT_DENIED", "Consent is required to access this record.", 403)
        return user.id
    if membership.role not in CLINICIAN_READ_ROLES:
        raise ApiError("ROLE_REQUIRED", "You are not authorized for this action.", 403)
    if not patient_id:
        raise ApiError(
            "FHIR_PATIENT_REQUIRED",
            "patient_id is required for clinician trend queries.",
            422,
        )
    return patient_id


@router.get("/tenants/{tenant_id}/trend-tests", response_model=list[TrendTestRead])
def list_trend_tests(
    tenant_id: str,
    request: Request,
    response: Response,
    patient_id: str | None = Query(default=None),
    user: User = Depends(get_current_user),
    membership: TenantMembership = Depends(
        require_role("tenant_admin", "staff", "provider", "patient")
    ),
    session: Session = Depends(get_session),
) -> list[TrendTestRead]:
    """Catalog of supported tests. Pass patient_id to annotate counts (consent-gated)."""
    if membership.tenant_id != tenant_id:
        raise ApiError("TENANT_NOT_FOUND", "Tenant not found.", 404)
    response.headers["Cache-Control"] = "no-store"

    if patient_id is None and membership.role == "patient":
        patient_id = user.id

    if patient_id:
        pid = _resolve_patient_id(membership=membership, user=user, patient_id=patient_id)
        require_patient_consent(
            session,
            tenant_id=tenant_id,
            patient_id=pid,
            actor=user,
            membership=membership,
            request_id=_request_id(request),
            subject_type="Observation",
            subject_id=pid,
        )
        rows = list_patient_trend_tests(
            session, tenant_id=tenant_id, patient_id=pid
        )
        return [TrendTestRead.model_validate(item) for item in rows]

    return [
        TrendTestRead.model_validate({**item, "point_count": 0, "has_data": False})
        for item in list_supported_tests()
    ]


@router.get("/tenants/{tenant_id}/trends", response_model=TrendSeriesRead)
def get_trends(
    tenant_id: str,
    request: Request,
    response: Response,
    code: str = Query(..., min_length=2, max_length=64, description="Test code, e.g. glucose"),
    patient_id: str | None = Query(default=None),
    date_from: str | None = Query(default=None, description="Inclusive ISO start"),
    date_to: str | None = Query(default=None, description="Inclusive ISO end"),
    user: User = Depends(get_current_user),
    membership: TenantMembership = Depends(
        require_role("tenant_admin", "staff", "provider", "patient")
    ),
    session: Session = Depends(get_session),
) -> TrendSeriesRead:
    if membership.tenant_id != tenant_id:
        raise ApiError("TENANT_NOT_FOUND", "Tenant not found.", 404)
    test_code = normalize_test_code(code)
    if test_code is None:
        raise ApiError("TREND_TEST_UNKNOWN", f"Unsupported test code: {code}.", 422)
    pid = _resolve_patient_id(membership=membership, user=user, patient_id=patient_id)
    require_patient_consent(
        session,
        tenant_id=tenant_id,
        patient_id=pid,
        actor=user,
        membership=membership,
        request_id=_request_id(request),
        subject_type="Observation",
        subject_id=pid,
    )
    series = build_trend_series(
        session,
        tenant_id=tenant_id,
        patient_id=pid,
        test_code=test_code,
        date_from=date_from,
        date_to=date_to,
    )
    append_audit_event(
        session,
        actor_user_id=user.id,
        tenant_id=tenant_id,
        action="trends.read",
        subject_type="Patient",
        subject_id=pid,
        request_id=_request_id(request),
    )
    response.headers["Cache-Control"] = "no-store"
    return TrendSeriesRead.model_validate(series)


@router.get("/tenants/{tenant_id}/insights", response_model=TrendInsightsRead)
def get_insights(
    tenant_id: str,
    request: Request,
    response: Response,
    code: str = Query(..., min_length=2, max_length=64),
    patient_id: str | None = Query(default=None),
    user: User = Depends(get_current_user),
    membership: TenantMembership = Depends(
        require_role("tenant_admin", "staff", "provider", "patient")
    ),
    session: Session = Depends(get_session),
) -> TrendInsightsRead:
    """Educational AI change flags — never diagnostic."""
    if membership.tenant_id != tenant_id:
        raise ApiError("TENANT_NOT_FOUND", "Tenant not found.", 404)
    test_code = normalize_test_code(code)
    if test_code is None:
        raise ApiError("TREND_TEST_UNKNOWN", f"Unsupported test code: {code}.", 422)
    pid = _resolve_patient_id(membership=membership, user=user, patient_id=patient_id)
    require_patient_consent(
        session,
        tenant_id=tenant_id,
        patient_id=pid,
        actor=user,
        membership=membership,
        request_id=_request_id(request),
        subject_type="Observation",
        subject_id=pid,
    )
    series = build_trend_series(
        session, tenant_id=tenant_id, patient_id=pid, test_code=test_code
    )
    samples = [
        TrendSample(
            effective_at=p["effective_at"],
            value=float(p["value"]),
            unit=str(p["unit"] or series["unit"]),
            reference_low=p.get("reference_low"),
            reference_high=p.get("reference_high"),
        )
        for p in series["points"]
    ]
    flags = build_insights_adapter().explain_changes(
        test_code=test_code,
        test_label=series["test_label"],
        samples=samples,
    )
    append_audit_event(
        session,
        actor_user_id=user.id,
        tenant_id=tenant_id,
        action="insights.read",
        subject_type="Patient",
        subject_id=pid,
        request_id=_request_id(request),
    )
    response.headers["Cache-Control"] = "no-store"
    return TrendInsightsRead(
        patient_id=pid,
        test_code=test_code,
        test_label=series["test_label"],
        flags=[InsightFlagRead.model_validate(f.__dict__) for f in flags],
        disclaimer=INSIGHT_DISCLAIMER,
        point_count=len(series["points"]),
    )
