"""Patient Health Timeline — merged labs, documents, visits, and appointments."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import ApiError, get_current_user
from app.authorization import require_role
from app.consent_gate import require_patient_consent
from app.db import get_session
from app.models import ClinicPatient, TenantMembership, User
from app.schemas import TimelineEventRead, TimelineRead
from app.timeline_service import build_health_timeline

router = APIRouter(prefix="/api/v1", tags=["Timeline"])


@router.get(
    "/tenants/{tenant_id}/patients/me/timeline",
    response_model=TimelineRead,
)
def read_my_timeline(
    tenant_id: str,
    request: Request,
    limit: int = Query(default=50, ge=1, le=100),
    membership: TenantMembership = Depends(require_role("patient")),
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> TimelineRead:
    events = build_health_timeline(
        session, tenant_id=tenant_id, patient_user_id=user.id, limit=limit
    )
    return TimelineRead(
        patient_user_id=user.id,
        events=[TimelineEventRead(**event) for event in events],
    )


@router.get(
    "/tenants/{tenant_id}/patients/{clinic_patient_id}/timeline",
    response_model=TimelineRead,
)
def read_patient_timeline(
    tenant_id: str,
    clinic_patient_id: str,
    request: Request,
    limit: int = Query(default=50, ge=1, le=100),
    membership: TenantMembership = Depends(
        require_role("tenant_admin", "staff", "provider")
    ),
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> TimelineRead:
    clinic_patient = session.execute(
        select(ClinicPatient).where(
            ClinicPatient.tenant_id == tenant_id,
            ClinicPatient.id == clinic_patient_id,
            ClinicPatient.status == "active",
        )
    ).scalar_one_or_none()
    if clinic_patient is None:
        raise ApiError("PATIENT_NOT_FOUND", "Patient not found.", 404)

    require_patient_consent(
        session,
        tenant_id=tenant_id,
        patient_id=clinic_patient.patient_user_id,
        actor=user,
        membership=membership,
        purpose="treatment",
        request_id=getattr(request.state, "request_id", ""),
        subject_type="ClinicPatient",
        subject_id=clinic_patient_id,
    )

    events = build_health_timeline(
        session,
        tenant_id=tenant_id,
        patient_user_id=clinic_patient.patient_user_id,
        limit=limit,
    )
    return TimelineRead(
        patient_user_id=clinic_patient.patient_user_id,
        events=[TimelineEventRead(**event) for event in events],
    )
