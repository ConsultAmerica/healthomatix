from __future__ import annotations

from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import ApiError, get_current_user
from app.db import get_session
from app.models import ClinicPatient, Tenant, TenantMembership, User


def require_membership(
    tenant_id: str,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> TenantMembership:
    membership = session.execute(
        select(TenantMembership).where(
            TenantMembership.tenant_id == tenant_id,
            TenantMembership.user_id == user.id,
            TenantMembership.status == "active",
            TenantMembership.tenant_id.in_(
                select(Tenant.id).where(Tenant.status == "active")
            ),
        )
    ).scalar_one_or_none()
    if membership is None:
        raise ApiError("TENANT_NOT_FOUND", "Tenant not found.", 404)
    return membership


def require_role(*roles: str):
    def dependency(
        membership: TenantMembership = Depends(require_membership),
    ) -> TenantMembership:
        if membership.role not in roles:
            raise ApiError("ROLE_REQUIRED", "You are not authorized for this action.", 403)
        return membership

    dependency.__name__ = "require_" + "_or_".join(roles)
    return dependency


def require_clinic_patient(
    session: Session,
    *,
    tenant_id: str,
    user_id: str,
) -> ClinicPatient:
    clinic_patient = session.execute(
        select(ClinicPatient).where(
            ClinicPatient.tenant_id == tenant_id,
            ClinicPatient.patient_user_id == user_id,
            ClinicPatient.status == "active",
        )
    ).scalar_one_or_none()
    if clinic_patient is None:
        raise ApiError("PATIENT_NOT_FOUND", "Patient not found.", 404)
    return clinic_patient
