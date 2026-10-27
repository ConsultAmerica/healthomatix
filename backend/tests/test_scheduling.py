from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app import scheduling_routes
from app.auth import get_current_user
from app.db import Base, get_session
from app.main import app
from app.models import (
    Appointment,
    AuditEvent,
    ClinicLocation,
    ClinicPatient,
    NotificationOutbox,
    ProviderAvailability,
    ProviderCredential,
    ProviderProfile,
    Tenant,
    TenantMembership,
    User,
)


@pytest.fixture
def scheduling_client(
    monkeypatch: pytest.MonkeyPatch,
) -> Generator[
    tuple[TestClient, Session, User, User, Tenant, Tenant, ClinicLocation],
    None,
    None,
]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    session = session_factory()
    patient = User(issuer="https://identity.example", subject="patient-1")
    provider = User(issuer="https://identity.example", subject="provider-1")
    clinic_a = Tenant(slug="clinic-a", display_name="Clinic A")
    clinic_b = Tenant(slug="clinic-b", display_name="Clinic B")
    session.add_all((patient, provider, clinic_a, clinic_b))
    session.flush()
    location = ClinicLocation(
        tenant_id=clinic_a.id,
        name="Main clinic",
        timezone="America/New_York",
    )
    session.add_all(
        (
            TenantMembership(tenant_id=clinic_a.id, user_id=patient.id, role="patient"),
            TenantMembership(tenant_id=clinic_b.id, user_id=patient.id, role="patient"),
            TenantMembership(tenant_id=clinic_a.id, user_id=provider.id, role="provider"),
            ClinicPatient(tenant_id=clinic_a.id, patient_user_id=patient.id),
            ProviderProfile(
                user_id=provider.id,
                display_name="Synthetic Provider",
                specialty="Family medicine",
                profile_status="active",
            ),
            ProviderCredential(
                tenant_id=clinic_a.id,
                provider_user_id=provider.id,
                jurisdiction="US-NY",
                credential_type="medical-license",
                regulator="Synthetic regulator",
                verification_reference="synthetic-ref",
                status="verified",
                review_source="synthetic fixture",
            ),
            location,
        )
    )
    session.commit()

    actor = [patient]
    monkeypatch.setattr(
        scheduling_routes,
        "settings",
        SimpleNamespace(scheduling_enabled=True),
    )

    def override_session() -> Generator[Session, None, None]:
        yield session

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_current_user] = lambda: actor[0]
    try:
        with TestClient(app) as client:
            yield client, session, patient, provider, clinic_a, clinic_b, location
    finally:
        app.dependency_overrides.clear()
        session.close()
        Base.metadata.drop_all(engine)
        engine.dispose()


def _future_start(offset_hours: int = 2) -> datetime:
    value = datetime.now(UTC) + timedelta(hours=offset_hours)
    value = value.replace(second=0, microsecond=0, minute=0 if value.minute < 30 else 30)
    if value <= datetime.now(UTC) + timedelta(hours=1):
        value += timedelta(minutes=30)
    return value


def _create_slot(
    client: TestClient,
    provider: User,
    tenant: Tenant,
    location: ClinicLocation,
    starts_at: datetime,
) -> str:
    app.dependency_overrides[get_current_user] = lambda: provider
    response = client.post(
        f"/api/v1/tenants/{tenant.id}/providers/me/availability",
        json={"location_id": location.id, "starts_at": starts_at.isoformat()},
    )
    assert response.status_code == 201, response.text
    return response.json()["availability_id"]


def test_patient_booking_is_idempotent_and_creates_minimal_audit_and_notifications(
    scheduling_client: tuple[TestClient, Session, User, User, Tenant, Tenant, ClinicLocation],
) -> None:
    client, session, patient, provider, clinic_a, _, location = scheduling_client
    slot_id = _create_slot(client, provider, clinic_a, location, _future_start())
    app.dependency_overrides[get_current_user] = lambda: patient
    available = client.get(f"/api/v1/tenants/{clinic_a.id}/availability")

    payload = {"availability_id": slot_id, "idempotency_key": "booking-unique-001"}
    first = client.post(f"/api/v1/tenants/{clinic_a.id}/appointments", json=payload)
    replay = client.post(f"/api/v1/tenants/{clinic_a.id}/appointments", json=payload)

    assert first.status_code == 201, first.text
    assert available.status_code == 200, available.text
    assert [slot["availability_id"] for slot in available.json()] == [slot_id]
    assert replay.status_code == 200, replay.text
    assert first.json()["appointment_id"] == replay.json()["appointment_id"]
    assert first.json()["provider_name"] == "Synthetic Provider"
    assert session.scalar(select(Appointment).where(Appointment.status == "booked"))
    events = session.scalars(select(AuditEvent)).all()
    assert [event.action for event in events].count("appointment.booked") == 1
    jobs = session.scalars(select(NotificationOutbox)).all()
    assert len(jobs) == 2
    assert {job.status for job in jobs} == {"pending"}


def test_patient_cannot_book_across_tenants_or_access_unlinked_availability(
    scheduling_client: tuple[TestClient, Session, User, User, Tenant, Tenant, ClinicLocation],
) -> None:
    client, _, patient, provider, clinic_a, clinic_b, location = scheduling_client
    slot_id = _create_slot(client, provider, clinic_a, location, _future_start())
    app.dependency_overrides[get_current_user] = lambda: patient

    listing = client.get(f"/api/v1/tenants/{clinic_b.id}/availability")
    booking = client.post(
        f"/api/v1/tenants/{clinic_b.id}/appointments",
        json={"availability_id": slot_id, "idempotency_key": "cross-tenant-001"},
    )

    assert listing.status_code == 404
    assert booking.status_code == 404
    assert booking.json()["error"]["code"] == "PATIENT_NOT_FOUND"


def test_slot_cannot_be_double_booked_and_can_be_rebooked_after_cancellation(
    scheduling_client: tuple[TestClient, Session, User, User, Tenant, Tenant, ClinicLocation],
) -> None:
    client, session, patient, provider, clinic_a, _, location = scheduling_client
    slot_id = _create_slot(client, provider, clinic_a, location, _future_start())
    app.dependency_overrides[get_current_user] = lambda: patient

    first = client.post(
        f"/api/v1/tenants/{clinic_a.id}/appointments",
        json={"availability_id": slot_id, "idempotency_key": "booking-first-001"},
    )
    conflict = client.post(
        f"/api/v1/tenants/{clinic_a.id}/appointments",
        json={"availability_id": slot_id, "idempotency_key": "booking-again-001"},
    )
    cancellation = client.post(
        f"/api/v1/tenants/{clinic_a.id}/appointments/{first.json()['appointment_id']}/cancel"
    )
    second = client.post(
        f"/api/v1/tenants/{clinic_a.id}/appointments",
        json={"availability_id": slot_id, "idempotency_key": "booking-after-001"},
    )

    assert first.status_code == 201
    assert conflict.status_code == 409
    assert cancellation.status_code == 200
    assert cancellation.json()["status"] == "cancelled"
    assert second.status_code == 201
    assert (
        session.scalar(
            select(Appointment).where(Appointment.id == first.json()["appointment_id"])
        ).status
        == "cancelled"
    )


def test_rescheduling_atomically_moves_slot_and_queues_notifications(
    scheduling_client: tuple[TestClient, Session, User, User, Tenant, Tenant, ClinicLocation],
) -> None:
    client, session, patient, provider, clinic_a, _, location = scheduling_client
    start = _future_start()
    first_slot = _create_slot(client, provider, clinic_a, location, start)
    next_slot = _create_slot(
        client,
        provider,
        clinic_a,
        location,
        start + timedelta(minutes=30),
    )
    app.dependency_overrides[get_current_user] = lambda: patient
    booking = client.post(
        f"/api/v1/tenants/{clinic_a.id}/appointments",
        json={"availability_id": first_slot, "idempotency_key": "booking-move-001"},
    )

    response = client.post(
        f"/api/v1/tenants/{clinic_a.id}/appointments/{booking.json()['appointment_id']}/reschedule",
        json={"availability_id": next_slot},
    )

    assert response.status_code == 200, response.text
    assert response.json()["starts_at"] != booking.json()["starts_at"]
    assert session.get(ProviderAvailability, first_slot).status == "open"
    assert session.get(ProviderAvailability, next_slot).status == "booked"
    assert (
        session.scalar(
            select(Appointment).where(Appointment.id == booking.json()["appointment_id"])
        ).availability_id
        == next_slot
    )
    assert session.scalar(select(AuditEvent).where(AuditEvent.action == "appointment.rescheduled"))
    assert session.scalar(
        select(NotificationOutbox).where(NotificationOutbox.event_type == "appointment.rescheduled")
    )


def test_unverified_provider_cannot_publish_availability(
    scheduling_client: tuple[TestClient, Session, User, User, Tenant, Tenant, ClinicLocation],
) -> None:
    client, session, _, provider, clinic_a, _, location = scheduling_client
    session.query(ProviderCredential).filter_by(
        tenant_id=clinic_a.id,
        provider_user_id=provider.id,
    ).update({"status": "pending"})
    session.commit()
    app.dependency_overrides[get_current_user] = lambda: provider

    response = client.post(
        f"/api/v1/tenants/{clinic_a.id}/providers/me/availability",
        json={"location_id": location.id, "starts_at": _future_start().isoformat()},
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "PROVIDER_NOT_VERIFIED"


def test_scheduling_fails_closed_when_feature_gate_is_disabled(
    scheduling_client: tuple[TestClient, Session, User, User, Tenant, Tenant, ClinicLocation],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, _, _, _, clinic_a, _, _ = scheduling_client
    monkeypatch.setattr(
        scheduling_routes,
        "settings",
        SimpleNamespace(scheduling_enabled=False),
    )

    response = client.get(f"/api/v1/tenants/{clinic_a.id}/availability")

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "SCHEDULING_DISABLED"
