from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import get_current_user
from app.db import Base, get_session
from app.fhir_models import FhirResource
from app.main import app
from app.models import AuditEvent, ClinicPatient, Tenant, TenantMembership, User


@pytest.fixture
def fhir_client() -> Generator[tuple[TestClient, Session, dict[str, User]], None, None]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    session = session_factory()

    patient = User(issuer="https://identity.example", subject="patient-1")
    clinician = User(issuer="https://identity.example", subject="clinician-1")
    other = User(issuer="https://identity.example", subject="clinician-2")
    session.add_all([patient, clinician, other])
    session.flush()

    tenant = Tenant(slug="fhir-clinic", display_name="FHIR Clinic")
    session.add(tenant)
    session.flush()
    session.add_all(
        [
            TenantMembership(
                tenant_id=tenant.id, user_id=patient.id, role="patient", status="active"
            ),
            TenantMembership(
                tenant_id=tenant.id, user_id=clinician.id, role="provider", status="active"
            ),
            TenantMembership(
                tenant_id=tenant.id, user_id=other.id, role="provider", status="active"
            ),
            ClinicPatient(
                tenant_id=tenant.id,
                patient_user_id=patient.id,
                status="active",
            ),
        ]
    )
    session.commit()

    actors = {"patient": patient, "clinician": clinician, "other": other, "tenant_id": tenant.id}
    current = {"user": patient}

    def override_session() -> Generator[Session, None, None]:
        yield session

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_current_user] = lambda: current["user"]
    try:
        with TestClient(app) as client:
            yield client, session, actors, current  # type: ignore[misc]
    finally:
        app.dependency_overrides.clear()
        session.close()
        Base.metadata.drop_all(engine)
        engine.dispose()


def test_patient_stores_and_views_observation_under_own_access(
    fhir_client: tuple,
) -> None:
    client, session, actors, current = fhir_client
    tenant_id = actors["tenant_id"]
    patient: User = actors["patient"]
    current["user"] = patient

    ensured = client.post(f"/api/v1/fhir/R4/tenants/{tenant_id}/Patient/$ensure")
    assert ensured.status_code == 200, ensured.text
    assert ensured.json()["id"] == patient.id

    # Patient cannot create Observation (clinician role) — clinician creates after consent
    current["user"] = actors["clinician"]
    denied = client.get(
        f"/api/v1/fhir/R4/tenants/{tenant_id}/Observation",
        params={"patient": patient.id},
    )
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "CONSENT_DENIED"
    assert session.scalar(
        select(AuditEvent).where(AuditEvent.action == "consent.denied")
    )

    current["user"] = patient
    grant = client.post(
        f"/api/v1/tenants/{tenant_id}/patients/me/consents",
        json={
            "purpose": "treatment",
            "scope": "chart.read",
            "policy_version": "v1",
        },
    )
    assert grant.status_code == 201, grant.text

    current["user"] = actors["clinician"]
    created = client.post(
        f"/api/v1/fhir/R4/tenants/{tenant_id}/Observation",
        json={
            "resourceType": "Observation",
            "status": "final",
            "code": {"text": "Heart rate"},
            "subject": {"reference": f"Patient/{patient.id}"},
            "valueQuantity": {"value": 72, "unit": "/min"},
        },
    )
    assert created.status_code == 201, created.text
    obs_id = created.json()["id"]

    read = client.get(f"/api/v1/fhir/R4/tenants/{tenant_id}/Observation/{obs_id}")
    assert read.status_code == 200
    assert read.json()["code"]["text"] == "Heart rate"

    searched = client.get(
        f"/api/v1/fhir/R4/tenants/{tenant_id}/Observation",
        params={"patient": patient.id},
    )
    assert searched.status_code == 200
    assert searched.json()["total"] >= 1

    # Provenance written
    assert session.scalar(
        select(FhirResource).where(
            FhirResource.resource_type == "Provenance",
            FhirResource.tenant_id == tenant_id,
        )
    )


def test_clinician_without_consent_denied_and_audited(fhir_client: tuple) -> None:
    client, session, actors, current = fhir_client
    tenant_id = actors["tenant_id"]
    patient: User = actors["patient"]
    current["user"] = patient
    client.post(f"/api/v1/fhir/R4/tenants/{tenant_id}/Patient/$ensure")

    current["user"] = actors["other"]
    response = client.get(f"/api/v1/fhir/R4/tenants/{tenant_id}/Patient/{patient.id}")
    assert response.status_code == 403
    deny = session.execute(
        select(AuditEvent).where(AuditEvent.action == "consent.denied")
    ).scalars().all()
    assert deny
    fhir_audits = session.execute(
        select(FhirResource).where(FhirResource.resource_type == "AuditEvent")
    ).scalars().all()
    assert any(
        (r.resource or {}).get("outcomeDesc") == "consent.denied" for r in fhir_audits
    )


def test_withdraw_consent_inactivates_fhir_and_blocks_reads(fhir_client: tuple) -> None:
    client, session, actors, current = fhir_client
    tenant_id = actors["tenant_id"]
    patient: User = actors["patient"]
    current["user"] = patient
    client.post(f"/api/v1/fhir/R4/tenants/{tenant_id}/Patient/$ensure")
    grant = client.post(
        f"/api/v1/tenants/{tenant_id}/patients/me/consents",
        json={"purpose": "treatment", "scope": "chart.read", "policy_version": "v1"},
    )
    assert grant.status_code == 201, grant.text
    grant_id = grant.json()["grant_id"]

    current["user"] = actors["clinician"]
    ok = client.get(f"/api/v1/fhir/R4/tenants/{tenant_id}/Patient/{patient.id}")
    assert ok.status_code == 200

    current["user"] = patient
    withdrawn = client.post(
        f"/api/v1/tenants/{tenant_id}/patients/me/consents/{grant_id}/withdraw",
        json={"reason_code": "no_longer_wanted"},
    )
    assert withdrawn.status_code == 200, withdrawn.text

    consent = session.execute(
        select(FhirResource).where(
            FhirResource.id == grant_id,
            FhirResource.resource_type == "Consent",
        )
    ).scalar_one()
    assert consent.resource.get("status") == "inactive"
    period = (consent.resource.get("provision") or {}).get("period") or {}
    assert period.get("end"), "withdrawal should close the FHIR Consent period"

    current["user"] = actors["clinician"]
    blocked = client.get(f"/api/v1/fhir/R4/tenants/{tenant_id}/Patient/{patient.id}")
    assert blocked.status_code == 403


def test_care_coordination_consent_opens_treatment_chart(fhir_client: tuple) -> None:
    client, _session, actors, current = fhir_client
    tenant_id = actors["tenant_id"]
    patient: User = actors["patient"]
    current["user"] = patient
    client.post(f"/api/v1/fhir/R4/tenants/{tenant_id}/Patient/$ensure")
    grant = client.post(
        f"/api/v1/tenants/{tenant_id}/patients/me/consents",
        json={
            "purpose": "care_coordination",
            "scope": "clinic_care_team",
            "policy_version": "v1",
        },
    )
    assert grant.status_code == 201, grant.text

    current["user"] = actors["clinician"]
    ok = client.get(f"/api/v1/fhir/R4/tenants/{tenant_id}/Patient/{patient.id}")
    assert ok.status_code == 200
