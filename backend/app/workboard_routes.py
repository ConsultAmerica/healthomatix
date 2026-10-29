"""Clinician workboard for operational dashboards."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy.orm import Session

from app.auth import ApiError, get_current_user
from app.authorization import require_role
from app.clinical_queue import build_clinical_workboard
from app.db import get_session
from app.models import TenantMembership, User
from app.schemas import ClinicalWorkboardRead

router = APIRouter(prefix="/api/v1", tags=["Workboard"])


@router.get(
    "/tenants/{tenant_id}/workboard",
    response_model=ClinicalWorkboardRead,
)
def read_workboard(
    tenant_id: str,
    request: Request,
    response: Response,
    scope: str = Query(default="me", pattern="^(me|clinic)$"),
    user: User = Depends(get_current_user),
    membership: TenantMembership = Depends(
        require_role("tenant_admin", "staff", "provider")
    ),
    session: Session = Depends(get_session),
) -> ClinicalWorkboardRead:
    if membership.tenant_id != tenant_id:
        raise ApiError("TENANT_NOT_FOUND", "Tenant not found.", 404)
    provider_filter = None
    if scope == "me" and membership.role == "provider":
        provider_filter = user.id
    elif scope == "me" and membership.role in {"tenant_admin", "staff"}:
        # Admins/staff see clinic-wide queues by default.
        provider_filter = None
    payload = build_clinical_workboard(
        session, tenant_id=tenant_id, provider_user_id=provider_filter
    )
    response.headers["Cache-Control"] = "no-store"
    return ClinicalWorkboardRead(**payload)
