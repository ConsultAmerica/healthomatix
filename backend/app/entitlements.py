"""Backend feature entitlement checks for SaaS modules (V1.6)."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import ApiError
from app.rcm_models import FeatureEntitlement


def has_entitlement(session: Session, *, tenant_id: str, feature_code: str) -> bool:
    row = session.execute(
        select(FeatureEntitlement).where(
            FeatureEntitlement.tenant_id == tenant_id,
            FeatureEntitlement.feature_code == feature_code,
            FeatureEntitlement.enabled.is_(True),
        )
    ).scalar_one_or_none()
    return row is not None


def require_entitlement(session: Session, *, tenant_id: str, feature_code: str) -> None:
    if has_entitlement(session, tenant_id=tenant_id, feature_code=feature_code):
        return
    raise ApiError(
        "FEATURE_NOT_ENTITLED",
        f"Organization is not entitled to feature '{feature_code}'.",
        403,
    )
