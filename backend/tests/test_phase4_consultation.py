from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import get_current_user
from app.db import Base, get_session
from app.fhir_models import FhirResource
from app.main import app
from app.models import (
    ClinicLocation,
    ClinicPatient,
    ProviderCredential,
    ProviderProfile,
    Tenant,
    TenantMembership,
    User,
)
import app.scheduling_routes as scheduling_routes


@pytest.fixture
def consult_client(monkeypatch) -> Generator[tuple[TestClient, Session, dict], None, None]:
    monkeypatch.setattr(
        scheduling_routes,
        "settings",
        SimpleNamespace(scheduling_enabled=True),
    )
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    session = session_factory()

    patient = User(issuer="https://identity.example", subject="p-visit")
    clinician = User(issuer="https://identity.example", subject="c-visit")
    session.add_all([patient, clinician])
    session.flush()
    tenant = Tenant(slug="visit-clinic", display_name="Visit Clinic")
    session.add(tenant)
    session.flush()
    location = ClinicLocation(
        tenant_id=tenant.id, name="Main", timezone="America/New_York", status="active"
    )
    session.add(location)
    session.flush()
    session.add_all(
        [
            TenantMembership(
                tenant_id=tenant.id, user_id=patient.id, role="patient", status="active"
            ),
            TenantMembership(
                tenant_id=tenant.id, user_id=clinician.id, role="provider", status="active"
            ),
            ClinicPatient(tenant_id=tenant.id, patient_user_id=patient.id, status="active"),
            ProviderProfile(
                user_id=clinician.id,
                display_name="Dr Visit",
                specialty="Family",
                profile_status="active",
            ),
            ProviderCredential(
                tenant_id=tenant.id,
                provider_user_id=clinician.id,
                jurisdiction="NY",
                credential_type="MD",
                regulator="Board",
                status="verified",
            ),
        ]
    )
    session.commit()

    current = {"user": patient}

    def override_session() -> Generator[Session, None, None]:
        yield session

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_current_user] = lambda: current["user"]

    actors = {
        "patient": patient,
        "clinician": clinician,
        "tenant_id": tenant.id,
        "location_id": location.id,
        "current": current,
    }
    try:
        with TestClient(app) as client:
            yield client, session, actors
    finally:
        app.dependency_overrides.clear()
        session.close()
        Base.metadata.drop_all(engine)
        engine.dispose()


def _book_appointment(client: TestClient, actors: dict) -> str:
    tenant_id = actors["tenant_id"]
    current = actors["current"]
    current["user"] = actors["clinician"]
    starts = datetime.now(UTC) + timedelta(days=1)
    starts = starts.replace(minute=0, second=0, microsecond=0)
    slot = client.post(
        f"/api/v1/tenants/{tenant_id}/providers/me/availability",
        json={"location_id": actors["location_id"], "starts_at": starts.isoformat()},
    )
    assert slot.status_code == 201, slot.text
    availability_id = slot.json()["availability_id"]

    current["user"] = actors["patient"]
    client.post(f"/api/v1/fhir/R4/tenants/{tenant_id}/Patient/$ensure")
    client.post(
        f"/api/v1/tenants/{tenant_id}/patients/me/consents",
        json={"purpose": "treatment", "scope": "chart.read", "policy_version": "v1"},
    )
    booked = client.post(
        f"/api/v1/tenants/{tenant_id}/appointments",
        json={"availability_id": availability_id, "idempotency_key": "visit-key-001234"},
    )
    assert booked.status_code == 201, booked.text
    return booked.json()["appointment_id"]


def test_book_join_complete_records_encounter(consult_client: tuple) -> None:
    client, session, actors = consult_client
    tenant_id = actors["tenant_id"]
    appointment_id = _book_appointment(client, actors)

    # FHIR Appointment mirrored on book
    assert session.scalar(
        select(FhirResource).where(
            FhirResource.resource_type == "Appointment",
            FhirResource.id == appointment_id,
        )
    )

    current = actors["current"]
    current["user"] = actors["patient"]
    created = client.post(
        f"/api/v1/tenants/{tenant_id}/sessions",
        json={"appointment_id": appointment_id},
    )
    assert created.status_code == 201, created.text
    session_id = created.json()["session_id"]

    joined = client.post(f"/api/v1/tenants/{tenant_id}/sessions/{session_id}/join")
    assert joined.status_code == 200, joined.text
    assert joined.json()["token"]
    assert joined.json()["video_provider"] == "fake"

    current["user"] = actors["clinician"]
    clinician_join = client.post(f"/api/v1/tenants/{tenant_id}/sessions/{session_id}/join")
    assert clinician_join.status_code == 200

    completed = client.post(
        f"/api/v1/tenants/{tenant_id}/sessions/{session_id}/complete",
        json={"follow_up_plan": "Recheck labs in 3 months. Continue current medications."},
    )
    assert completed.status_code == 200, completed.text
    body = completed.json()
    assert body["status"] == "completed"
    assert body["encounter_id"]
    assert "Recheck labs" in body["follow_up_plan"]

    encounter = session.execute(
        select(FhirResource).where(
            FhirResource.id == body["encounter_id"],
            FhirResource.resource_type == "Encounter",
        )
    ).scalar_one()
    assert encounter.patient_id == actors["patient"].id
    assert (encounter.resource.get("class") or {}).get("code") == "VR"


def test_session_requires_consent(consult_client: tuple) -> None:
    client, _session, actors = consult_client
    tenant_id = actors["tenant_id"]
    # Book without relying on consent helper — still need scheduling path
    appointment_id = _book_appointment(client, actors)
    # Withdraw consent
    current = actors["current"]
    current["user"] = actors["patient"]
    grants = client.get(f"/api/v1/tenants/{tenant_id}/patients/me/consents")
    grant_id = grants.json()[0]["grant_id"]
    client.post(
        f"/api/v1/tenants/{tenant_id}/patients/me/consents/{grant_id}/withdraw",
        json={"reason_code": "no_longer_wanted"},
    )

    current["user"] = actors["clinician"]
    denied = client.post(
        f"/api/v1/tenants/{tenant_id}/sessions",
        json={"appointment_id": appointment_id},
    )
    assert denied.status_code == 403
