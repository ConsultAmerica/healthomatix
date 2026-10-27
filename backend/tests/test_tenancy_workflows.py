from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import get_current_user
from app.db import Base, get_session
from app.main import app
from app.models import (
    AuditEvent,
    ClinicInvitation,
    ClinicPatient,
    PatientProfile,
    TenantMembership,
    User,
)


@pytest.fixture
def tenancy_client() -> Generator[tuple[TestClient, Session, User, list[User]], None, None]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    session = session_factory()
    owner = User(issuer="https://identity.example", subject="clinic-owner")
    session.add(owner)
    session.commit()
    actor = [owner]
    invited_users: list[User] = []

    def override_session() -> Generator[Session, None, None]:
        yield session

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_current_user] = lambda: actor[0]
    try:
        with TestClient(app) as client:
            yield client, session, owner, invited_users
    finally:
        app.dependency_overrides.clear()
        session.close()
        Base.metadata.drop_all(engine)
        engine.dispose()


def test_clinic_onboarding_and_single_use_staff_invitation(
    tenancy_client: tuple[TestClient, Session, User, list[User]],
) -> None:
    client, session, _, invited_users = tenancy_client
    clinic = client.post(
        "/api/v1/tenants",
        json={
            "slug": "north-clinic",
            "display_name": "North Clinic",
            "location_name": "Main office",
            "timezone": "America/New_York",
        },
    )
    assert clinic.status_code == 201, clinic.text
    tenant_id = clinic.json()["tenant_id"]
    assert clinic.json()["role"] == "tenant_admin"

    created = client.post(
        f"/api/v1/tenants/{tenant_id}/invitations",
        json={"role": "staff"},
    )
    assert created.status_code == 201, created.text
    invitation_code = created.json()["invitation_code"]
    invitation_id = created.json()["invitation_id"]
    stored_invitation = session.get(ClinicInvitation, invitation_id)
    assert stored_invitation.token_hash != invitation_code

    listed = client.get(f"/api/v1/tenants/{tenant_id}/invitations")
    assert listed.status_code == 200
    assert "invitation_code" not in listed.text

    invitee = User(issuer="https://identity.example", subject="invited-staff")
    session.add(invitee)
    session.commit()
    invited_users.append(invitee)
    app.dependency_overrides[get_current_user] = lambda: invited_users[0]
    accepted = client.post(
        "/api/v1/invitations/accept",
        json={"invitation_code": invitation_code},
    )
    replay = client.post(
        "/api/v1/invitations/accept",
        json={"invitation_code": invitation_code},
    )

    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["role"] == "staff"
    assert replay.status_code == 404
    assert (
        session.scalar(
            select(TenantMembership).where(
                TenantMembership.tenant_id == tenant_id,
                TenantMembership.user_id == invitee.id,
            )
        ).role
        == "staff"
    )
    assert session.get(ClinicInvitation, invitation_id).status == "accepted"
    assert {event.action for event in session.scalars(select(AuditEvent)).all()} >= {
        "clinic.created",
        "clinic.invitation_created",
        "clinic.invitation_accepted",
    }


def test_patient_invitation_creates_tenant_scoped_patient_link(
    tenancy_client: tuple[TestClient, Session, User, list[User]],
) -> None:
    client, session, owner, invited_users = tenancy_client
    clinic = client.post(
        "/api/v1/tenants",
        json={
            "slug": "patient-clinic",
            "display_name": "Patient Clinic",
            "location_name": "Main office",
            "timezone": "UTC",
        },
    )
    tenant_id = clinic.json()["tenant_id"]
    created = client.post(
        f"/api/v1/tenants/{tenant_id}/invitations",
        json={"role": "patient"},
    )
    patient = User(issuer="https://identity.example", subject="invited-patient")
    session.add(patient)
    session.commit()
    invited_users.append(patient)
    app.dependency_overrides[get_current_user] = lambda: invited_users[0]
    accepted = client.post(
        "/api/v1/invitations/accept",
        json={"invitation_code": created.json()["invitation_code"]},
    )

    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["role"] == "patient"
    clinic_patient = session.scalar(
        select(ClinicPatient).where(
            ClinicPatient.tenant_id == tenant_id,
            ClinicPatient.patient_user_id == patient.id,
        )
    )
    assert clinic_patient is not None
    assert session.get(PatientProfile, patient.id) is not None

    app.dependency_overrides[get_current_user] = lambda: owner
    second_clinic = client.post(
        "/api/v1/tenants",
        json={
            "slug": "second-patient-clinic",
            "display_name": "Second Patient Clinic",
            "location_name": "Main office",
            "timezone": "UTC",
        },
    )
    second_tenant_id = second_clinic.json()["tenant_id"]
    second_invitation = client.post(
        f"/api/v1/tenants/{second_tenant_id}/invitations",
        json={"role": "patient"},
    )
    app.dependency_overrides[get_current_user] = lambda: invited_users[0]
    second_acceptance = client.post(
        "/api/v1/invitations/accept",
        json={"invitation_code": second_invitation.json()["invitation_code"]},
    )

    assert second_acceptance.status_code == 200
    assert (
        session.scalar(
            select(ClinicPatient).where(
                ClinicPatient.tenant_id == second_tenant_id,
                ClinicPatient.patient_user_id == patient.id,
            )
        )
        is not None
    )
    assert (
        len(
            session.scalars(
                select(PatientProfile).where(PatientProfile.user_id == patient.id)
            ).all()
        )
        == 1
    )
    app.dependency_overrides[get_current_user] = lambda: owner
    directory = client.get(f"/api/v1/tenants/{second_tenant_id}/patients")
    assert directory.status_code == 200
    assert directory.json()[0]["status"] == "active"
    assert "patient_user_id" not in directory.json()[0]


def test_invalid_timezone_and_duplicate_clinic_slug_are_reported(
    tenancy_client: tuple[TestClient, Session, User, list[User]],
) -> None:
    client, _, _, _ = tenancy_client
    payload = {
        "slug": "duplicate-clinic",
        "display_name": "Duplicate Clinic",
        "location_name": "Main office",
        "timezone": "Not/A_Timezone",
    }
    invalid_timezone = client.post("/api/v1/tenants", json=payload)
    assert invalid_timezone.status_code == 422
    assert invalid_timezone.json()["error"]["code"] == "TIMEZONE_INVALID"

    payload["timezone"] = "UTC"
    assert client.post("/api/v1/tenants", json=payload).status_code == 201
    duplicate = client.post("/api/v1/tenants", json=payload)
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "CLINIC_SLUG_UNAVAILABLE"
