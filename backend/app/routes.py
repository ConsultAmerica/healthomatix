from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit import append_audit_event
from app.auth import ApiError, get_current_user
from app.authorization import require_clinic_patient, require_role
from app.config import settings
from app.db import get_session
from app.models import (
    AuditEvent,
    ConsentGrant,
    ConsentWithdrawal,
    MedicalDocument,
    PatientProfile,
    ProviderCredential,
    ProviderProfile,
    Tenant,
    TenantMembership,
    User,
)
from app.schemas import (
    ConsentRead,
    ConsentWithdrawalWrite,
    ConsentWrite,
    CredentialRead,
    CredentialReview,
    CredentialReviewQueueRead,
    CredentialWrite,
    DocumentRead,
    MembershipRead,
    PatientProfileRead,
    PatientProfileWrite,
    ProviderProfileRead,
    ProviderProfileWrite,
    UserRead,
)

router = APIRouter(prefix="/api/v1")


def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", "")


def _is_withdrawn(session: Session, grant_id: str) -> datetime | None:
    return session.execute(
        select(ConsentWithdrawal.withdrawn_at).where(
            ConsentWithdrawal.grant_id == grant_id
        )
    ).scalar_one_or_none()


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "healthomatix-api"}


@router.get("/health/live")
def health_live() -> dict[str, str]:
    """Process liveness — no dependency details."""
    return {"status": "alive"}


@router.get("/health/ready")
def health_ready(session: Session = Depends(get_session)) -> dict[str, str]:
    """Readiness — verifies DB connectivity without exposing connection strings."""
    try:
        session.execute(select(1))
    except Exception as error:
        raise ApiError("NOT_READY", "Service dependencies are not ready.", 503) from error
    return {"status": "ready"}


@router.get("/auth/config")
def auth_config() -> dict[str, object]:
    return {
        "oidc_configured": settings.oidc_configured,
        "scheduling_enabled": settings.scheduling_enabled,
        "document_storage_configured": settings.document_storage_configured,
        "demo_auth_enabled": settings.demo_auth_enabled,
        "require_mfa_for_platform_admin": settings.require_mfa_for_platform_admin,
        "api_rate_limit_enabled": settings.api_rate_limit_enabled,
        "launch_mode": settings.launch_mode,
        "document_require_malware_clear": settings.document_require_malware_clear,
    }


@router.get("/me", response_model=UserRead)
def me(
    request: Request,
    response: Response,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> UserRead:
    response.headers["Cache-Control"] = "no-store"
    rows = session.execute(
        select(TenantMembership, Tenant.display_name)
        .join(Tenant, Tenant.id == TenantMembership.tenant_id)
        .where(
            TenantMembership.user_id == user.id,
            TenantMembership.status == "active",
            Tenant.status == "active",
        )
        .order_by(Tenant.display_name)
    ).all()
    return UserRead(
        user_id=user.id,
        memberships=[
            MembershipRead(
                tenant_id=membership.tenant_id,
                tenant_name=tenant_name,
                role=membership.role,
                status=membership.status,
            )
            for membership, tenant_name in rows
        ],
    )


@router.get("/tenants/{tenant_id}/patients/me", response_model=PatientProfileRead)
def get_patient_profile(
    tenant_id: str,
    response: Response,
    user: User = Depends(get_current_user),
    membership: TenantMembership = Depends(require_role("patient")),
    session: Session = Depends(get_session),
) -> PatientProfileRead:
    if membership.tenant_id != tenant_id:
        raise ApiError("TENANT_NOT_FOUND", "Tenant not found.", 404)
    require_clinic_patient(session, tenant_id=tenant_id, user_id=user.id)
    response.headers["Cache-Control"] = "no-store"
    profile = session.get(PatientProfile, user.id)
    if profile is None:
        raise ApiError("PROFILE_NOT_FOUND", "Patient profile not found.", 404)
    return PatientProfileRead(user_id=user.id, **{
        field: getattr(profile, field)
        for field in ("preferred_name", "legal_name", "phone", "preferred_language", "updated_at")
    })


@router.put("/tenants/{tenant_id}/patients/me", response_model=PatientProfileRead)
def put_patient_profile(
    tenant_id: str,
    body: PatientProfileWrite,
    request: Request,
    response: Response,
    user: User = Depends(get_current_user),
    membership: TenantMembership = Depends(require_role("patient")),
    session: Session = Depends(get_session),
) -> PatientProfileRead:
    if membership.tenant_id != tenant_id:
        raise ApiError("TENANT_NOT_FOUND", "Tenant not found.", 404)
    clinic_patient = require_clinic_patient(session, tenant_id=tenant_id, user_id=user.id)
    response.headers["Cache-Control"] = "no-store"
    with session.begin_nested():
        profile = session.get(PatientProfile, user.id)
        if profile is None:
            profile = PatientProfile(user_id=user.id)
            session.add(profile)
        for key, value in body.model_dump().items():
            setattr(profile, key, value)
        session.flush()
        append_audit_event(
            session,
            actor_user_id=user.id,
            tenant_id=tenant_id,
            action="patient.profile_updated",
            subject_type="clinic_patient",
            subject_id=clinic_patient.id,
            request_id=_request_id(request),
        )
    return PatientProfileRead(
        user_id=user.id,
        **{
            field: getattr(profile, field)
            for field in ("preferred_name", "legal_name", "phone", "preferred_language", "updated_at")
        },
    )


@router.get("/tenants/{tenant_id}/providers/me", response_model=ProviderProfileRead)
def get_provider_profile(
    tenant_id: str,
    response: Response,
    user: User = Depends(get_current_user),
    membership: TenantMembership = Depends(require_role("provider")),
    session: Session = Depends(get_session),
) -> ProviderProfileRead:
    if membership.tenant_id != tenant_id:
        raise ApiError("TENANT_NOT_FOUND", "Tenant not found.", 404)
    response.headers["Cache-Control"] = "no-store"
    profile = session.get(ProviderProfile, user.id)
    if profile is None:
        raise ApiError("PROFILE_NOT_FOUND", "Provider profile not found.", 404)
    return ProviderProfileRead(
        user_id=user.id,
        display_name=profile.display_name,
        specialty=profile.specialty,
        profile_status=profile.profile_status,
        updated_at=profile.updated_at,
    )


@router.put("/tenants/{tenant_id}/providers/me", response_model=ProviderProfileRead)
def put_provider_profile(
    tenant_id: str,
    body: ProviderProfileWrite,
    request: Request,
    response: Response,
    user: User = Depends(get_current_user),
    membership: TenantMembership = Depends(require_role("provider")),
    session: Session = Depends(get_session),
) -> ProviderProfileRead:
    if membership.tenant_id != tenant_id:
        raise ApiError("TENANT_NOT_FOUND", "Tenant not found.", 404)
    response.headers["Cache-Control"] = "no-store"
    with session.begin_nested():
        profile = session.get(ProviderProfile, user.id)
        if profile is None:
            profile = ProviderProfile(user_id=user.id, profile_status="pending")
            session.add(profile)
        profile.display_name = body.display_name
        profile.specialty = body.specialty
        session.flush()
        append_audit_event(
            session,
            actor_user_id=user.id,
            tenant_id=tenant_id,
            action="provider.profile_updated",
            subject_type="provider_profile",
            subject_id=user.id,
            request_id=_request_id(request),
        )
    return ProviderProfileRead(
        user_id=user.id,
        display_name=profile.display_name,
        specialty=profile.specialty,
        profile_status=profile.profile_status,
        updated_at=profile.updated_at,
    )


def _credential_read(credential: ProviderCredential) -> CredentialRead:
    return CredentialRead(
        credential_id=credential.id,
        jurisdiction=credential.jurisdiction,
        credential_type=credential.credential_type,
        regulator=credential.regulator,
        status=credential.status,
        submitted_at=credential.submitted_at,
        reviewed_at=credential.reviewed_at,
    )


@router.get(
    "/tenants/{tenant_id}/providers/me/credentials",
    response_model=list[CredentialRead],
)
def list_own_provider_credentials(
    tenant_id: str,
    response: Response,
    user: User = Depends(get_current_user),
    membership: TenantMembership = Depends(require_role("provider")),
    session: Session = Depends(get_session),
) -> list[CredentialRead]:
    if membership.tenant_id != tenant_id:
        raise ApiError("TENANT_NOT_FOUND", "Tenant not found.", 404)
    response.headers["Cache-Control"] = "no-store"
    rows = session.execute(
        select(ProviderCredential)
        .where(
            ProviderCredential.tenant_id == tenant_id,
            ProviderCredential.provider_user_id == user.id,
        )
        .order_by(ProviderCredential.submitted_at.desc())
        .limit(100)
    ).scalars()
    return [_credential_read(row) for row in rows]


@router.get(
    "/tenants/{tenant_id}/provider-credentials",
    response_model=list[CredentialReviewQueueRead],
)
def list_provider_credentials_for_review(
    tenant_id: str,
    response: Response,
    status: str = "pending",
    membership: TenantMembership = Depends(require_role("tenant_admin")),
    session: Session = Depends(get_session),
) -> list[CredentialReviewQueueRead]:
    if membership.tenant_id != tenant_id:
        raise ApiError("TENANT_NOT_FOUND", "Tenant not found.", 404)
    if status not in {"pending", "verified", "rejected", "revoked"}:
        raise ApiError("INVALID_STATUS", "Unknown credential status.", 422)
    response.headers["Cache-Control"] = "no-store"
    rows = session.execute(
        select(ProviderCredential, ProviderProfile)
        .join(
            TenantMembership,
            (TenantMembership.tenant_id == ProviderCredential.tenant_id)
            & (TenantMembership.user_id == ProviderCredential.provider_user_id)
            & (TenantMembership.role == "provider"),
        )
        .outerjoin(
            ProviderProfile, ProviderProfile.user_id == ProviderCredential.provider_user_id
        )
        .where(
            ProviderCredential.tenant_id == tenant_id,
            ProviderCredential.status == status,
        )
        .order_by(ProviderCredential.submitted_at)
        .limit(100)
    ).all()
    return [
        CredentialReviewQueueRead(
            **_credential_read(credential).model_dump(),
            provider_user_id=credential.provider_user_id,
            provider_display_name=profile.display_name if profile else "",
            provider_specialty=profile.specialty if profile else "",
        )
        for credential, profile in rows
    ]


@router.post(
    "/tenants/{tenant_id}/providers/me/credentials",
    response_model=CredentialRead,
    status_code=201,
)
def submit_provider_credential(
    tenant_id: str,
    body: CredentialWrite,
    request: Request,
    response: Response,
    user: User = Depends(get_current_user),
    membership: TenantMembership = Depends(require_role("provider")),
    session: Session = Depends(get_session),
) -> CredentialRead:
    if membership.tenant_id != tenant_id:
        raise ApiError("TENANT_NOT_FOUND", "Tenant not found.", 404)
    response.headers["Cache-Control"] = "no-store"
    credential = ProviderCredential(
        tenant_id=tenant_id,
        provider_user_id=user.id,
        **body.model_dump(),
    )
    with session.begin_nested():
        session.add(credential)
        session.flush()
        append_audit_event(
            session,
            actor_user_id=user.id,
            tenant_id=tenant_id,
            action="provider.credential_submitted",
            subject_type="provider_credential",
            subject_id=credential.id,
            request_id=_request_id(request),
        )
    return CredentialRead(
        credential_id=credential.id,
        jurisdiction=credential.jurisdiction,
        credential_type=credential.credential_type,
        regulator=credential.regulator,
        status=credential.status,
        submitted_at=credential.submitted_at,
        reviewed_at=credential.reviewed_at,
    )


@router.post(
    "/tenants/{tenant_id}/providers/{provider_user_id}/credentials/{credential_id}/review",
    response_model=CredentialRead,
)
def review_provider_credential(
    tenant_id: str,
    provider_user_id: str,
    credential_id: str,
    body: CredentialReview,
    request: Request,
    response: Response,
    reviewer: User = Depends(get_current_user),
    membership: TenantMembership = Depends(require_role("tenant_admin")),
    session: Session = Depends(get_session),
) -> CredentialRead:
    if membership.tenant_id != tenant_id:
        raise ApiError("TENANT_NOT_FOUND", "Tenant not found.", 404)
    response.headers["Cache-Control"] = "no-store"
    with session.begin_nested():
        credential = session.execute(
            select(ProviderCredential).where(
                ProviderCredential.id == credential_id,
                ProviderCredential.tenant_id == tenant_id,
                ProviderCredential.provider_user_id == provider_user_id,
                ProviderCredential.status == "pending",
            )
        ).scalar_one_or_none()
        if credential is None:
            raise ApiError("CREDENTIAL_NOT_FOUND", "Credential not found.", 404)
        credential.status = body.decision
        credential.reviewed_by_user_id = reviewer.id
        credential.reviewed_at = datetime.now(UTC)
        credential.review_source = body.review_source
        if body.decision == "verified":
            # A verified credential completes onboarding; suspended profiles stay suspended.
            profile = session.get(ProviderProfile, provider_user_id)
            if profile is not None and profile.profile_status in {"draft", "pending"}:
                profile.profile_status = "active"
        session.flush()
        append_audit_event(
            session,
            actor_user_id=reviewer.id,
            tenant_id=tenant_id,
            action=f"provider.credential_{body.decision}",
            subject_type="provider_credential",
            subject_id=credential.id,
            request_id=_request_id(request),
        )
    return CredentialRead(
        credential_id=credential.id,
        jurisdiction=credential.jurisdiction,
        credential_type=credential.credential_type,
        regulator=credential.regulator,
        status=credential.status,
        submitted_at=credential.submitted_at,
        reviewed_at=credential.reviewed_at,
    )


@router.get(
    "/tenants/{tenant_id}/patients/me/consents",
    response_model=list[ConsentRead],
)
def list_consents(
    tenant_id: str,
    response: Response,
    user: User = Depends(get_current_user),
    membership: TenantMembership = Depends(require_role("patient")),
    session: Session = Depends(get_session),
) -> list[ConsentRead]:
    if membership.tenant_id != tenant_id:
        raise ApiError("TENANT_NOT_FOUND", "Tenant not found.", 404)
    require_clinic_patient(session, tenant_id=tenant_id, user_id=user.id)
    response.headers["Cache-Control"] = "no-store"
    grants = session.execute(
        select(ConsentGrant)
        .where(
            ConsentGrant.tenant_id == tenant_id,
            ConsentGrant.patient_user_id == user.id,
        )
        .order_by(ConsentGrant.granted_at.desc())
    ).scalars()
    return [
        ConsentRead(
            grant_id=grant.id,
            purpose=grant.purpose,
            scope=grant.scope,
            policy_version=grant.policy_version,
            granted_at=grant.granted_at,
            expires_at=grant.expires_at,
            withdrawn_at=_is_withdrawn(session, grant.id),
        )
        for grant in grants
    ]


@router.post(
    "/tenants/{tenant_id}/patients/me/consents",
    response_model=ConsentRead,
    status_code=201,
)
def grant_consent(
    tenant_id: str,
    body: ConsentWrite,
    request: Request,
    response: Response,
    user: User = Depends(get_current_user),
    membership: TenantMembership = Depends(require_role("patient")),
    session: Session = Depends(get_session),
) -> ConsentRead:
    if membership.tenant_id != tenant_id:
        raise ApiError("TENANT_NOT_FOUND", "Tenant not found.", 404)
    require_clinic_patient(session, tenant_id=tenant_id, user_id=user.id)
    if body.expires_at is not None and body.expires_at <= datetime.now(UTC):
        raise ApiError("CONSENT_EXPIRY_INVALID", "Consent expiry must be in the future.", 422)
    consent = ConsentGrant(
        tenant_id=tenant_id,
        patient_user_id=user.id,
        granted_by_user_id=user.id,
        **body.model_dump(),
    )
    with session.begin_nested():
        session.add(consent)
        session.flush()
        from app.consent_gate import sync_fhir_consent_from_grant
        from app.fhir_store import ensure_patient_for_user

        ensure_patient_for_user(session, tenant_id=tenant_id, user_id=user.id)
        sync_fhir_consent_from_grant(session, tenant_id=tenant_id, grant=consent)
        append_audit_event(
            session,
            actor_user_id=user.id,
            tenant_id=tenant_id,
            action="consent.granted",
            subject_type="consent_grant",
            subject_id=consent.id,
            request_id=_request_id(request),
        )
    response.headers["Cache-Control"] = "no-store"
    return ConsentRead(
        grant_id=consent.id,
        purpose=consent.purpose,
        scope=consent.scope,
        policy_version=consent.policy_version,
        granted_at=consent.granted_at,
        expires_at=consent.expires_at,
        withdrawn_at=None,
    )


@router.post(
    "/tenants/{tenant_id}/patients/me/consents/{consent_id}/withdraw",
    response_model=ConsentRead,
)
def withdraw_consent(
    tenant_id: str,
    consent_id: str,
    body: ConsentWithdrawalWrite,
    request: Request,
    response: Response,
    user: User = Depends(get_current_user),
    membership: TenantMembership = Depends(require_role("patient")),
    session: Session = Depends(get_session),
) -> ConsentRead:
    if membership.tenant_id != tenant_id:
        raise ApiError("TENANT_NOT_FOUND", "Tenant not found.", 404)
    require_clinic_patient(session, tenant_id=tenant_id, user_id=user.id)
    response.headers["Cache-Control"] = "no-store"
    with session.begin_nested():
        consent = session.execute(
            select(ConsentGrant).where(
                ConsentGrant.id == consent_id,
                ConsentGrant.tenant_id == tenant_id,
                ConsentGrant.patient_user_id == user.id,
            )
        ).scalar_one_or_none()
        if consent is None:
            raise ApiError("CONSENT_NOT_FOUND", "Consent not found.", 404)
        if _is_withdrawn(session, consent.id) is not None:
            raise ApiError("CONSENT_ALREADY_WITHDRAWN", "Consent is already withdrawn.", 409)
        withdrawal = ConsentWithdrawal(
            grant_id=consent.id,
            actor_user_id=user.id,
            reason_code=body.reason_code,
        )
        session.add(withdrawal)
        session.flush()
        from app.consent_gate import inactivate_fhir_consent

        inactivate_fhir_consent(session, tenant_id=tenant_id, grant_id=consent.id)
        append_audit_event(
            session,
            actor_user_id=user.id,
            tenant_id=tenant_id,
            action="consent.withdrawn",
            subject_type="consent_grant",
            subject_id=consent.id,
            request_id=_request_id(request),
        )
    return ConsentRead(
        grant_id=consent.id,
        purpose=consent.purpose,
        scope=consent.scope,
        policy_version=consent.policy_version,
        granted_at=consent.granted_at,
        expires_at=consent.expires_at,
        withdrawn_at=withdrawal.withdrawn_at,
    )


@router.get("/tenants/{tenant_id}/documents", response_model=list[DocumentRead])
def list_documents(
    tenant_id: str,
    response: Response,
    user: User = Depends(get_current_user),
    membership: TenantMembership = Depends(require_role("patient")),
    session: Session = Depends(get_session),
) -> list[DocumentRead]:
    if membership.tenant_id != tenant_id:
        raise ApiError("TENANT_NOT_FOUND", "Tenant not found.", 404)
    require_clinic_patient(session, tenant_id=tenant_id, user_id=user.id)
    response.headers["Cache-Control"] = "no-store"
    rows = session.execute(
        select(MedicalDocument)
        .where(
            MedicalDocument.tenant_id == tenant_id,
            MedicalDocument.patient_user_id == user.id,
            MedicalDocument.lifecycle_state != "deleted",
        )
        .order_by(MedicalDocument.created_at.desc())
    ).scalars()
    return [
        DocumentRead(
            document_id=row.id,
            original_filename=row.original_filename,
            content_type=row.content_type,
            size_bytes=row.size_bytes,
            lifecycle_state=row.lifecycle_state,
            created_at=row.created_at,
            clinic_patient_id=row.clinic_patient_id,
        )
        for row in rows
    ]


@router.get("/tenants/{tenant_id}/audit-events")
def list_audit_events(
    tenant_id: str,
    response: Response,
    membership: TenantMembership = Depends(require_role("tenant_admin", "auditor")),
    session: Session = Depends(get_session),
    limit: int = 50,
) -> list[dict[str, str]]:
    if membership.tenant_id != tenant_id:
        raise ApiError("TENANT_NOT_FOUND", "Tenant not found.", 404)
    if not 1 <= limit <= 100:
        raise ApiError("INVALID_LIMIT", "Limit must be between 1 and 100.", 422)
    response.headers["Cache-Control"] = "no-store"
    events = session.execute(
        select(AuditEvent)
        .where(AuditEvent.tenant_id == tenant_id)
        .order_by(AuditEvent.created_at.desc())
        .limit(limit)
    ).scalars()
    return [
        {
            "event_id": row.id,
            "action": row.action,
            "subject_type": row.subject_type,
            "subject_id": row.subject_id,
            "actor_user_id": row.actor_user_id or "",
            "request_id": row.request_id,
            "created_at": row.created_at.isoformat(),
        }
        for row in events
    ]
