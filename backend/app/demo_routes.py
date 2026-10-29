"""Demo-only endpoints (refused unless DEMO_AUTH_SECRET is configured)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.auth import ApiError, get_current_user
from app.db import get_session
from app.demo_seed import seed_demo_clinic
from app.models import User
from app.schemas import DemoSeedRead
from app.storage import StorageUnavailable

router = APIRouter(prefix="/api/v1/demo", tags=["Demo"])


@router.post("/seed", response_model=DemoSeedRead)
def seed_demo(
    request: Request,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> DemoSeedRead:
    """
    Provision the shared synthetic sandbox clinic for demo personas.
    Idempotent — safe to call again; fills any missing pieces.
    """
    try:
        result = seed_demo_clinic(session, actor=user)
    except StorageUnavailable as error:
        raise ApiError(
            "DOCUMENT_STORAGE_UNAVAILABLE",
            "Document storage is not configured for this environment.",
            503,
        ) from error
    return DemoSeedRead(**result)
