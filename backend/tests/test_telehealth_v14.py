"""V1.4 waiting room, clinical notes, and follow-up publish tests."""

from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import get_current_user
from app.db import Base, get_session
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
def tele_client(monkeypatch) -> Generator[tuple[TestClient, Session, dict], None, None]:
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

    patient = User(issuer="https://identity.example", subject="p-v14")
    provider = User(issuer="https://identity.example", subject="d-v14")
    session.add_all([patient, provider])
    session.flush()
    tenant = Tenant(slug="v14-clinic", display_name="V14 Clinic")
    session.add(tenant)
    session.flush()
    location = ClinicLocation(
        tenant_id=tenant.id, name="Main", timezone="America/Toronto", status="active"
    )
    session.add(location)
    session.flush()
    session.add_all(
        [
            TenantMembership(
                tenant_id=tenant.id, user_id=patient.id, role="patient", status="active"
            ),
            TenantMembership(
                tenant_id=tenant.id, user_id=provider.id, role="provider", status="active"
            ),
            ClinicPatient(tenant_id=tenant.id, patient_user_id=patient.id, status="active"),
            ProviderProfile(
                user_id=provider.id,
                display_name="Dr Demo",
                specialty="Family",
                profile_status="active",
            ),
            ProviderCredential(
                tenant_id=tenant.id,
                provider_user_id=provider.id,
                jurisdiction="ON",
                credential_type="medical_license",
                regulator="CPSO",
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
        "provider": provider,
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


def _book(client: TestClient, actors: dict) -> str:
    tenant_id = actors["tenant_id"]
    current = actors["current"]
    current["user"] = actors["provider"]
    starts = datetime.now(UTC) + timedelta(days=1)
    starts = starts.replace(minute=0, second=0, microsecond=0)
    slot = client.post(
        f"/api/v1/tenants/{tenant_id}/providers/me/availability",
        json={"location_id": actors["location_id"], "starts_at": starts.isoformat()},
    )
    assert slot.status_code == 201, slot.text
    current["user"] = actors["patient"]
    client.post(f"/api/v1/fhir/R4/tenants/{tenant_id}/Patient/$ensure")
    client.post(
        f"/api/v1/tenants/{tenant_id}/patients/me/consents",
        json={"purpose": "treatment", "scope": "chart.read", "policy_version": "v1"},
    )
    booked = client.post(
        f"/api/v1/tenants/{tenant_id}/appointments",
        json={"availability_id": slot.json()["availability_id"], "idempotency_key": "v14-key-001"},
    )
    assert booked.status_code == 201, booked.text
    return booked.json()["appointment_id"]


def test_check_in_admit_and_list_waiting_room(tele_client) -> None:
    client, _session, actors = tele_client
    tenant_id = actors["tenant_id"]
    appointment_id = _book(client, actors)

    actors["current"]["user"] = actors["patient"]
    checked = client.post(f"/api/v1/tenants/{tenant_id}/appointments/{appointment_id}/check-in")
    assert checked.status_code == 200, checked.text
    assert checked.json()["status"] == "waiting"
    assert checked.json()["session_id"]

    actors["current"]["user"] = actors["provider"]
    queue = client.get(f"/api/v1/tenants/{tenant_id}/waiting-room")
    assert queue.status_code == 200
    assert any(row["appointment_id"] == appointment_id for row in queue.json())

    admitted = client.post(f"/api/v1/tenants/{tenant_id}/appointments/{appointment_id}/admit")
    assert admitted.status_code == 200, admitted.text
    assert admitted.json()["status"] == "admitted"


def test_clinical_note_sign_is_immutable_without_amend(tele_client) -> None:
    client, _session, actors = tele_client
    tenant_id = actors["tenant_id"]
    _book(client, actors)
    actors["current"]["user"] = actors["provider"]

    created = client.post(
        f"/api/v1/tenants/{tenant_id}/clinical-notes",
        json={
            "patient_id": actors["patient"].id,
            "subjective": "Reports fatigue",
            "objective": "NAD",
            "assessment": "Follow-up",
            "plan": "Return in 3 months",
        },
    )
    assert created.status_code == 201, created.text
    note_id = created.json()["note_id"]

    signed = client.post(f"/api/v1/tenants/{tenant_id}/clinical-notes/{note_id}/sign")
    assert signed.status_code == 200, signed.text
    assert signed.json()["status"] == "signed"
    version = signed.json()["version"]

    blocked = client.patch(
        f"/api/v1/tenants/{tenant_id}/clinical-notes/{note_id}",
        json={
            "patient_id": actors["patient"].id,
            "subjective": "changed",
            "objective": "",
            "assessment": "",
            "plan": "",
            "expected_version": version,
        },
    )
    assert blocked.status_code == 409

    amended = client.post(
        f"/api/v1/tenants/{tenant_id}/clinical-notes/{note_id}/amend",
        json={
            "plan": "Return in 2 months",
            "change_reason": "Clarify interval",
            "expected_version": version,
        },
    )
    assert amended.status_code == 200, amended.text
    assert amended.json()["plan"] == "Return in 2 months"


def test_provider_cannot_admit_other_providers_patient(tele_client) -> None:
    client, session, actors = tele_client
    tenant_id = actors["tenant_id"]
    appointment_id = _book(client, actors)

    other = User(issuer="https://identity.example", subject="d-other-v14")
    session.add(other)
    session.flush()
    session.add(
        TenantMembership(
            tenant_id=tenant_id, user_id=other.id, role="provider", status="active"
        )
    )
    session.commit()

    actors["current"]["user"] = actors["patient"]
    assert (
        client.post(f"/api/v1/tenants/{tenant_id}/appointments/{appointment_id}/check-in").status_code
        == 200
    )

    actors["current"]["user"] = other
    denied = client.post(f"/api/v1/tenants/{tenant_id}/appointments/{appointment_id}/admit")
    assert denied.status_code == 404


def test_follow_up_requires_approve_before_publish(tele_client) -> None:
    client, _session, actors = tele_client
    tenant_id = actors["tenant_id"]
    _book(client, actors)
    actors["current"]["user"] = actors["provider"]

    created = client.post(
        f"/api/v1/tenants/{tenant_id}/follow-up-plans",
        json={
            "patient_id": actors["patient"].id,
            "instructions": "Hydrate and rest",
            "tasks": [{"description": "Book labs in 2 weeks", "status": "open"}],
        },
    )
    assert created.status_code == 201, created.text
    plan_id = created.json()["plan_id"]

    premature = client.post(f"/api/v1/tenants/{tenant_id}/follow-up-plans/{plan_id}/publish")
    assert premature.status_code == 409

    approved = client.post(f"/api/v1/tenants/{tenant_id}/follow-up-plans/{plan_id}/approve")
    assert approved.status_code == 200
    published = client.post(f"/api/v1/tenants/{tenant_id}/follow-up-plans/{plan_id}/publish")
    assert published.status_code == 200
    assert published.json()["status"] == "published"

    actors["current"]["user"] = actors["patient"]
    mine = client.get(f"/api/v1/tenants/{tenant_id}/patients/me/follow-up-plans")
    assert mine.status_code == 200
    assert len(mine.json()) == 1
