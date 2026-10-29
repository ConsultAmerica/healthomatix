"""Idempotent synthetic demo clinic for DEMO_AUTH personas."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import DEMO_ISSUER, ApiError
from app.config import settings
from app.consent_gate import sync_fhir_consent_from_grant
from app.fhir_store import create_resource, ensure_patient_for_user, get_resource
from app.models import (
    AuditEvent,
    ClinicLocation,
    ClinicPatient,
    ConsentGrant,
    MedicalDocument,
    PatientProfile,
    ProviderAvailability,
    ProviderCredential,
    ProviderProfile,
    Tenant,
    TenantMembership,
    User,
    utcnow,
)
from app.storage import build_private_storage

DEMO_TENANT_SLUG = "demo-sandbox"
DEMO_TENANT_NAME = "Healthomatix Demo Clinic"

PERSONAS = {
    "admin": "demo-admin",
    "provider": "demo-provider",
    "patient": "demo-patient",
    "staff": "demo-staff",
}


def _require_demo_mode() -> None:
    if not settings.demo_auth_enabled:
        raise ApiError(
            "DEMO_UNAVAILABLE",
            "Demo seeding is only available when DEMO_AUTH_SECRET is configured.",
            404,
        )


def _ensure_user(session: Session, subject: str) -> User:
    user = session.execute(
        select(User).where(User.issuer == DEMO_ISSUER, User.subject == subject)
    ).scalar_one_or_none()
    if user is not None:
        return user
    user = User(issuer=DEMO_ISSUER, subject=subject)
    session.add(user)
    session.flush()
    return user


def _ensure_membership(
    session: Session, *, tenant_id: str, user_id: str, role: str
) -> TenantMembership:
    membership = session.execute(
        select(TenantMembership).where(
            TenantMembership.tenant_id == tenant_id,
            TenantMembership.user_id == user_id,
        )
    ).scalar_one_or_none()
    if membership is None:
        membership = TenantMembership(
            tenant_id=tenant_id, user_id=user_id, role=role, status="active"
        )
        session.add(membership)
        session.flush()
        return membership
    membership.role = role
    membership.status = "active"
    session.flush()
    return membership


def _ensure_consent(
    session: Session,
    *,
    tenant_id: str,
    patient: User,
    purpose: str,
    scope: str,
) -> None:
    existing = session.execute(
        select(ConsentGrant).where(
            ConsentGrant.tenant_id == tenant_id,
            ConsentGrant.patient_user_id == patient.id,
            ConsentGrant.purpose == purpose,
        )
    ).scalars().all()
    if existing:
        return
    grant = ConsentGrant(
        tenant_id=tenant_id,
        patient_user_id=patient.id,
        granted_by_user_id=patient.id,
        purpose=purpose,
        scope=scope,
        policy_version="v1-synthetic",
    )
    session.add(grant)
    session.flush()
    sync_fhir_consent_from_grant(session, tenant_id=tenant_id, grant=grant)


def seed_demo_clinic(session: Session, *, actor: User) -> dict[str, Any]:
    """
    Create (or complete) the shared demo sandbox tenant linking admin, provider,
    staff, and patient personas with consent, verified credential, availability,
    a sample lab document, and glucose observations.
    """
    _require_demo_mode()
    if actor.issuer != DEMO_ISSUER:
        raise ApiError(
            "DEMO_ACTOR_REQUIRED",
            "Sign in with a demo account to seed the sandbox clinic.",
            403,
        )

    admin = _ensure_user(session, PERSONAS["admin"])
    provider = _ensure_user(session, PERSONAS["provider"])
    patient = _ensure_user(session, PERSONAS["patient"])
    staff = _ensure_user(session, PERSONAS["staff"])

    tenant = session.execute(
        select(Tenant).where(Tenant.slug == DEMO_TENANT_SLUG)
    ).scalar_one_or_none()
    created = False
    if tenant is None:
        tenant = Tenant(slug=DEMO_TENANT_SLUG, display_name=DEMO_TENANT_NAME, status="active")
        session.add(tenant)
        session.flush()
        created = True

    _ensure_membership(session, tenant_id=tenant.id, user_id=admin.id, role="tenant_admin")
    _ensure_membership(session, tenant_id=tenant.id, user_id=provider.id, role="provider")
    _ensure_membership(session, tenant_id=tenant.id, user_id=staff.id, role="staff")
    _ensure_membership(session, tenant_id=tenant.id, user_id=patient.id, role="patient")

    clinic_patient = session.execute(
        select(ClinicPatient).where(
            ClinicPatient.tenant_id == tenant.id,
            ClinicPatient.patient_user_id == patient.id,
        )
    ).scalar_one_or_none()
    if clinic_patient is None:
        clinic_patient = ClinicPatient(
            tenant_id=tenant.id,
            patient_user_id=patient.id,
            chart_number="DEMO-1001",
            status="active",
        )
        session.add(clinic_patient)
        session.flush()

    if session.get(PatientProfile, patient.id) is None:
        session.add(
            PatientProfile(
                user_id=patient.id,
                preferred_name="Alex Demo",
                legal_name="Alexandra Demo",
                phone="+1-555-0100",
                preferred_language="en",
            )
        )
    profile = session.get(ProviderProfile, provider.id)
    if profile is None:
        session.add(
            ProviderProfile(
                user_id=provider.id,
                display_name="Dr. Jordan Lee",
                specialty="Family Medicine",
                profile_status="active",
            )
        )
    else:
        profile.display_name = profile.display_name or "Dr. Jordan Lee"
        profile.specialty = profile.specialty or "Family Medicine"
        profile.profile_status = "active"

    location = session.execute(
        select(ClinicLocation).where(
            ClinicLocation.tenant_id == tenant.id,
            ClinicLocation.name == "Main clinic",
        )
    ).scalar_one_or_none()
    if location is None:
        location = ClinicLocation(
            tenant_id=tenant.id,
            name="Main clinic",
            timezone="America/Toronto",
            status="active",
        )
        session.add(location)
        session.flush()

    credential = session.execute(
        select(ProviderCredential).where(
            ProviderCredential.tenant_id == tenant.id,
            ProviderCredential.provider_user_id == provider.id,
        )
    ).scalar_one_or_none()
    if credential is None:
        credential = ProviderCredential(
            tenant_id=tenant.id,
            provider_user_id=provider.id,
            jurisdiction="ON",
            credential_type="medical_license",
            regulator="College of Physicians and Surgeons of Ontario",
            verification_reference="DEMO-LIC-001",
            status="verified",
            reviewed_by_user_id=admin.id,
            reviewed_at=utcnow(),
            review_source="demo_seed",
        )
        session.add(credential)
        session.flush()
    elif credential.status != "verified":
        credential.status = "verified"
        credential.reviewed_by_user_id = admin.id
        credential.reviewed_at = utcnow()
        credential.review_source = "demo_seed"

    ensure_patient_for_user(
        session,
        tenant_id=tenant.id,
        user_id=patient.id,
        display_name="Alex Demo",
    )

    for purpose, scope in (
        ("treatment", "chart.read"),
        ("care_coordination", "clinic_care_team"),
        ("appointment_communication", "contact_details"),
    ):
        _ensure_consent(
            session,
            tenant_id=tenant.id,
            patient=patient,
            purpose=purpose,
            scope=scope,
        )

    # Sample lab document + glucose observations for Health Timeline / Trends.
    doc_id = f"demo-doc-{tenant.id[:8]}"
    document = session.get(MedicalDocument, doc_id)
    if document is None:
        content = (
            b"Healthomatix synthetic lab report\n"
            b"Patient: Alex Demo\n"
            b"Glucose fasting: 95 / 110 / 128 mg/dL\n"
            b"HbA1c: 5.8%\n"
        )
        digest = hashlib.sha256(content).hexdigest()
        storage = build_private_storage(settings.document_storage_path)
        stored = storage.put(tenant_id=tenant.id, document_id=doc_id, content=content)
        document = MedicalDocument(
            id=doc_id,
            tenant_id=tenant.id,
            patient_user_id=patient.id,
            clinic_patient_id=clinic_patient.id,
            uploaded_by_user_id=patient.id,
            storage_key=stored.key,
            original_filename="demo-lab-report.txt",
            content_type="text/plain",
            size_bytes=stored.size_bytes,
            sha256=digest,
            lifecycle_state="stored",
        )
        session.add(document)
        session.flush()
        if get_resource(
            session, tenant_id=tenant.id, resource_type="DocumentReference", resource_id=doc_id
        ) is None:
            create_resource(
                session,
                tenant_id=tenant.id,
                resource_type="DocumentReference",
                resource_id=doc_id,
                body={
                    "resourceType": "DocumentReference",
                    "status": "current",
                    "type": {"text": "Laboratory report"},
                    "subject": {"reference": f"Patient/{patient.id}"},
                    "date": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
                    "content": [
                        {
                            "attachment": {
                                "contentType": "text/plain",
                                "title": "demo-lab-report.txt",
                            }
                        }
                    ],
                },
            )

    samples = [
        ("2025-06-01T10:00:00Z", 95),
        ("2025-09-01T10:00:00Z", 110),
        ("2026-01-15T10:00:00Z", 128),
    ]
    for index, (effective, value) in enumerate(samples, start=1):
        obs_id = f"demo-obs-glucose-{index}-{tenant.id[:8]}"
        if get_resource(
            session, tenant_id=tenant.id, resource_type="Observation", resource_id=obs_id
        ):
            continue
        create_resource(
            session,
            tenant_id=tenant.id,
            resource_type="Observation",
            resource_id=obs_id,
            body={
                "resourceType": "Observation",
                "status": "final",
                "code": {"text": "Glucose"},
                "subject": {"reference": f"Patient/{patient.id}"},
                "effectiveDateTime": effective,
                "valueQuantity": {"value": value, "unit": "mg/dL"},
                "referenceRange": [{"text": "70-99"}],
                "derivedFrom": [{"reference": f"DocumentReference/{doc_id}"}],
            },
        )

    # Open availability slots starting tomorrow (scheduling demos).
    base = datetime.now(UTC).replace(microsecond=0, second=0, minute=0) + timedelta(days=1)
    base = base.replace(hour=14)
    open_slots = 0
    for offset_hours in (0, 24, 48):
        starts = base + timedelta(hours=offset_hours)
        ends = starts + timedelta(minutes=30)
        existing = session.execute(
            select(ProviderAvailability).where(
                ProviderAvailability.tenant_id == tenant.id,
                ProviderAvailability.provider_user_id == provider.id,
                ProviderAvailability.starts_at == starts,
            )
        ).scalar_one_or_none()
        if existing is None:
            session.add(
                ProviderAvailability(
                    tenant_id=tenant.id,
                    provider_user_id=provider.id,
                    location_id=location.id,
                    starts_at=starts,
                    ends_at=ends,
                    status="open",
                )
            )
            open_slots += 1
        elif existing.status == "open":
            open_slots += 1

    session.add(
        AuditEvent(
            tenant_id=tenant.id,
            actor_user_id=actor.id,
            action="demo.seed_applied",
            subject_type="tenant",
            subject_id=tenant.id,
            request_id="",
        )
    )
    session.commit()

    return {
        "tenant_id": tenant.id,
        "tenant_name": tenant.display_name,
        "slug": tenant.slug,
        "created": created,
        "clinic_patient_id": clinic_patient.id,
        "patient_user_id": patient.id,
        "provider_user_id": provider.id,
        "location_id": location.id,
        "document_id": doc_id,
        "open_availability_slots": open_slots,
        "personas": {
            "admin": "admin",
            "provider": "provider",
            "staff": "staff",
            "patient": "patient",
        },
    }
