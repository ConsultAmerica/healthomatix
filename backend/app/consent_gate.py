"""Consent enforcement for clinician/staff reads of patient-scoped PHI."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit import append_audit_event
from app.auth import ApiError
from app.fhir_store import create_resource, get_resource, search_resources, update_resource
from app.models import ConsentGrant, ConsentWithdrawal, TenantMembership, User
from app.roles import CLINICIAN_READ_ROLES

CHART_PURPOSES = frozenset({"treatment", "care_coordination"})


def _consent_purpose_codes(consent: dict) -> set[str]:
    codes: set[str] = set()
    provision = consent.get("provision") or {}
    for purpose in provision.get("purpose") or []:
        if isinstance(purpose, dict):
            for coding in purpose.get("coding") or []:
                if isinstance(coding, dict) and coding.get("code"):
                    codes.add(str(coding["code"]))
            if purpose.get("text"):
                codes.add(str(purpose["text"]))
    return codes


def _active_legacy_consent(
    session: Session,
    *,
    tenant_id: str,
    patient_user_id: str,
    purpose: str | None = None,
) -> bool:
    now = datetime.now(UTC)
    grants = session.execute(
        select(ConsentGrant).where(
            ConsentGrant.tenant_id == tenant_id,
            ConsentGrant.patient_user_id == patient_user_id,
        )
    ).scalars().all()
    for grant in grants:
        withdrawn = session.execute(
            select(ConsentWithdrawal.id).where(ConsentWithdrawal.grant_id == grant.id)
        ).scalar_one_or_none()
        if withdrawn is not None:
            continue
        if grant.expires_at is not None and grant.expires_at <= now:
            continue
        if purpose == "treatment" and grant.purpose not in CHART_PURPOSES:
            continue
        if purpose not in (None, "treatment") and grant.purpose != purpose:
            continue
        return True
    return False


def _active_fhir_consent(
    session: Session,
    *,
    tenant_id: str,
    patient_id: str,
    purpose: str = "treatment",
) -> bool:
    consents = search_resources(
        session, tenant_id=tenant_id, resource_type="Consent", patient_id=patient_id
    )
    now = datetime.now(UTC)
    for consent in consents:
        if consent.get("status") != "active":
            continue
        period = consent.get("provision", {}).get("period") or {}
        end = period.get("end")
        if end:
            try:
                end_dt = datetime.fromisoformat(end.replace("Z", "+00:00"))
                if end_dt <= now:
                    continue
            except ValueError:
                pass
        codes = _consent_purpose_codes(consent)
        if purpose == "treatment":
            if codes and not (codes & CHART_PURPOSES):
                continue
        elif purpose and codes and purpose not in codes:
            continue
        return True
    return False


def has_patient_consent(
    session: Session,
    *,
    tenant_id: str,
    patient_id: str,
    purpose: str = "treatment",
) -> bool:
    """patient_id is the FHIR Patient.id (aligned with user id in this facade)."""
    if _active_fhir_consent(
        session, tenant_id=tenant_id, patient_id=patient_id, purpose=purpose
    ):
        return True
    return _active_legacy_consent(
        session, tenant_id=tenant_id, patient_user_id=patient_id, purpose=purpose
    )


def find_active_consent_grant(
    session: Session,
    *,
    tenant_id: str,
    patient_user_id: str,
    purpose: str,
    scope: str | None = None,
) -> ConsentGrant | None:
    """Return the newest active ConsentGrant matching purpose/scope, or None."""
    now = datetime.now(UTC)
    grants = session.execute(
        select(ConsentGrant)
        .where(
            ConsentGrant.tenant_id == tenant_id,
            ConsentGrant.patient_user_id == patient_user_id,
            ConsentGrant.purpose == purpose,
        )
        .order_by(ConsentGrant.granted_at.desc())
    ).scalars().all()
    for grant in grants:
        if scope is not None and grant.scope != scope:
            continue
        withdrawn = session.execute(
            select(ConsentWithdrawal.id).where(ConsentWithdrawal.grant_id == grant.id)
        ).scalar_one_or_none()
        if withdrawn is not None:
            continue
        if grant.expires_at is not None and grant.expires_at <= now:
            continue
        return grant
    return None


def require_scribe_ambient_consent(
    session: Session,
    *,
    tenant_id: str,
    patient_id: str,
    actor: User,
    request_id: str = "",
) -> ConsentGrant:
    """Ambient AI transcription requires explicit ai_scribe consent (not telehealth alone)."""
    grant = find_active_consent_grant(
        session,
        tenant_id=tenant_id,
        patient_user_id=patient_id,
        purpose="ai_scribe",
        scope="ambient_transcription",
    )
    if grant is not None:
        return grant
    append_audit_event(
        session,
        actor_user_id=actor.id,
        tenant_id=tenant_id,
        action="consent.denied",
        subject_type="AiScribeSession",
        subject_id=patient_id,
        request_id=request_id,
        fhir_outcome="deny",
    )
    raise ApiError(
        "SCRIBE_CONSENT_REQUIRED",
        "Ambient AI transcription requires explicit patient consent "
        "(purpose=ai_scribe, scope=ambient_transcription).",
        403,
    )


def require_patient_consent(
    session: Session,
    *,
    tenant_id: str,
    patient_id: str,
    actor: User,
    membership: TenantMembership,
    purpose: str = "treatment",
    request_id: str = "",
    subject_type: str = "Patient",
    subject_id: str | None = None,
) -> None:
    """
    Patients may always access their own record.
    Clinician/staff/admin require an active Consent; denials are audited.
    """
    if membership.role == "patient":
        if actor.id != patient_id:
            append_audit_event(
                session,
                actor_user_id=actor.id,
                tenant_id=tenant_id,
                action="consent.denied",
                subject_type=subject_type,
                subject_id=subject_id or patient_id,
                request_id=request_id,
                fhir_outcome="deny",
            )
            raise ApiError("CONSENT_DENIED", "Consent is required to access this record.", 403)
        return

    if membership.role not in CLINICIAN_READ_ROLES:
        append_audit_event(
            session,
            actor_user_id=actor.id,
            tenant_id=tenant_id,
            action="consent.denied",
            subject_type=subject_type,
            subject_id=subject_id or patient_id,
            request_id=request_id,
            fhir_outcome="deny",
        )
        raise ApiError("CONSENT_DENIED", "Consent is required to access this record.", 403)

    if has_patient_consent(
        session, tenant_id=tenant_id, patient_id=patient_id, purpose=purpose
    ):
        return

    append_audit_event(
        session,
        actor_user_id=actor.id,
        tenant_id=tenant_id,
        action="consent.denied",
        subject_type=subject_type,
        subject_id=subject_id or patient_id,
        request_id=request_id,
        fhir_outcome="deny",
    )
    raise ApiError("CONSENT_DENIED", "Consent is required to access this record.", 403)


def sync_fhir_consent_from_grant(
    session: Session,
    *,
    tenant_id: str,
    grant: ConsentGrant,
) -> dict:
    """Mirror a ConsentGrant into a FHIR Consent resource (same id)."""
    body = {
        "resourceType": "Consent",
        "status": "active",
        "scope": {
            "coding": [
                {
                    "system": "http://terminology.hl7.org/CodeSystem/consentscope",
                    "code": "patient-privacy",
                }
            ]
        },
        "category": [
            {
                "coding": [
                    {
                        "system": "http://terminology.hl7.org/CodeSystem/consentcategorycodes",
                        "code": "npp",
                    }
                ]
            }
        ],
        "patient": {"reference": f"Patient/{grant.patient_user_id}"},
        "dateTime": (
            grant.granted_at.astimezone(UTC)
            if grant.granted_at.tzinfo
            else grant.granted_at.replace(tzinfo=UTC)
        )
        .isoformat()
        .replace("+00:00", "Z"),
        "provision": {
            "type": "permit",
            "purpose": [
                {
                    "coding": [
                        {
                            "system": "urn:healthomatix:consent-purpose",
                            "code": grant.purpose,
                        }
                    ],
                    "text": grant.purpose,
                }
            ],
            "period": {},
        },
        "policyRule": {"text": grant.policy_version},
        "extension": [
            {"url": "urn:healthomatix:consent-scope", "valueString": grant.scope},
            {"url": "urn:healthomatix:grant-id", "valueString": grant.id},
        ],
    }
    if grant.expires_at is not None:
        body["provision"]["period"]["end"] = (
            grant.expires_at.astimezone(UTC).isoformat().replace("+00:00", "Z")
        )
    existing = get_resource(
        session, tenant_id=tenant_id, resource_type="Consent", resource_id=grant.id
    )
    if existing:
        return update_resource(
            session,
            tenant_id=tenant_id,
            resource_type="Consent",
            resource_id=grant.id,
            body=body,
        ) or body
    return create_resource(
        session,
        tenant_id=tenant_id,
        resource_type="Consent",
        resource_id=grant.id,
        body=body,
    )


def inactivate_fhir_consent(
    session: Session,
    *,
    tenant_id: str,
    grant_id: str,
) -> None:
    """Mark mirrored FHIR Consent inactive after withdrawal."""
    existing = get_resource(
        session, tenant_id=tenant_id, resource_type="Consent", resource_id=grant_id
    )
    if not existing:
        return
    now = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    existing["status"] = "inactive"
    provision = dict(existing.get("provision") or {})
    period = dict(provision.get("period") or {})
    period["end"] = now
    provision["period"] = period
    existing["provision"] = provision
    update_resource(
        session,
        tenant_id=tenant_id,
        resource_type="Consent",
        resource_id=grant_id,
        body=existing,
    )
