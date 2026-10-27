from __future__ import annotations

from collections.abc import Callable, Generator
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app import platform_routes
from app.auth import get_current_user
from app.db import Base, get_session
from app.main import app
from app.models import (
    AuditEvent,
    ClinicLocation,
    ClinicPatient,
    PatientProfile,
    Tenant,
    TenantMembership,
    User,
)


@pytest.fixture
def platform_client(
    monkeypatch: pytest.MonkeyPatch,
) -> Generator[tuple[TestClient, Session, User, User, Tenant], None, None]:
    engine: Engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    session = session_factory()
    admin = User(issuer="https://identity.example", subject="platform-admin")
    owner = User(issuer="https://identity.example", subject="clinic-owner")
    patient = User(issuer="https://identity.example", subject="synthetic-patient")
    tenant = Tenant(slug="existing-clinic", display_name="Existing Clinic")
    session.add_all((admin, owner, patient, tenant))
    session.flush()
    session.add_all(
        (
            TenantMembership(tenant_id=tenant.id, user_id=owner.id, role="tenant_admin"),
            ClinicPatient(
                tenant_id=tenant.id,
                patient_user_id=patient.id,
                chart_number="SYN-100",
            ),
            PatientProfile(
                user_id=patient.id,
                preferred_name="Synthetic Patient",
                legal_name="Synthetic Patient",
                phone="",
                preferred_language="en",
            ),
        )
    )
    session.commit()

    monkeypatch.setattr(
        platform_routes,
        "settings",
        SimpleNamespace(
            platform_admin_identities=((admin.issuer, admin.subject),),
        ),
    )

    def override_session() -> Generator[Session, None, None]:
        yield session

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_current_user] = lambda: admin
    try:
        with TestClient(app) as client:
            yield client, session, admin, owner, tenant
    finally:
        app.dependency_overrides.clear()
        session.close()
        Base.metadata.drop_all(engine)
        engine.dispose()


def test_platform_admin_scope_is_separate_from_tenant_roles(
    platform_client: tuple[TestClient, Session, User, User, Tenant],
) -> None:
    client, _, admin, _, tenant = platform_client

    tenants = client.get("/api/v1/platform/tenants")
    patient_directory = client.get(f"/api/v1/tenants/{tenant.id}/patients")

    assert tenants.status_code == 200
    assert tenants.json()[0]["slug"] == tenant.slug
    assert "owner_user_id" not in tenants.text
    assert "Synthetic Patient" not in tenants.text
    assert "SYN-100" not in tenants.text
    assert patient_directory.status_code == 404
    assert admin.id not in tenants.text


def test_tenant_role_cannot_use_platform_admin_routes(
    platform_client: tuple[TestClient, Session, User, User, Tenant],
) -> None:
    client, _, _, owner, _ = platform_client
    app.dependency_overrides[get_current_user] = lambda: owner

    response = client.get("/api/v1/platform/tenants")

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "PLATFORM_ADMIN_REQUIRED"


def test_platform_tenant_provisioning_is_minimal_and_audited(
    platform_client: tuple[TestClient, Session, User, User, Tenant],
) -> None:
    client, session, admin, owner, _ = platform_client

    response = client.post(
        "/api/v1/platform/tenants",
        json={
            "slug": "provisioned-clinic",
            "display_name": "Provisioned Clinic",
            "location_name": "Main office",
            "timezone": "UTC",
            "owner_user_id": owner.id,
        },
    )

    assert response.status_code == 201, response.text
    tenant_id = response.json()["tenant_id"]
    assert "owner_user_id" not in response.json()
    membership = session.scalar(
        select(TenantMembership).where(
            TenantMembership.tenant_id == tenant_id,
            TenantMembership.user_id == owner.id,
        )
    )
    assert membership is not None
    assert membership.role == "tenant_admin"
    assert (
        session.scalar(
            select(TenantMembership).where(
                TenantMembership.tenant_id == tenant_id,
                TenantMembership.user_id == admin.id,
            )
        )
        is None
    )
    assert session.scalar(
        select(ClinicLocation).where(ClinicLocation.tenant_id == tenant_id)
    )
    assert session.scalar(
        select(AuditEvent).where(
            AuditEvent.action == "platform.tenant_provisioned",
            AuditEvent.actor_user_id == admin.id,
            AuditEvent.tenant_id == tenant_id,
        )
    )


def test_support_access_request_is_purpose_bound_pending_and_audited(
    platform_client: tuple[TestClient, Session, User, User, Tenant],
) -> None:
    client, session, admin, _, tenant = platform_client
    requested_until = datetime.now(UTC) + timedelta(hours=1)

    response = client.post(
        "/api/v1/platform/support-access-requests",
        json={
            "tenant_id": tenant.id,
            "ticket_reference": "SUP-2026-10",
            "purpose": "security_investigation",
            "requested_until": requested_until.isoformat(),
        },
    )

    assert response.status_code == 201, response.text
    request = response.json()
    assert request["status"] == "pending"
    assert request["purpose"] == "security_investigation"
    assert session.scalar(
        select(AuditEvent).where(
            AuditEvent.action == "platform.support_access.requested",
            AuditEvent.actor_user_id == admin.id,
            AuditEvent.subject_id == request["request_id"],
        )
    )
    listed_request = client.get("/api/v1/platform/support-access-requests").json()[0]
    assert listed_request["request_id"] == request["request_id"]
    assert listed_request["status"] == "pending"
    assert listed_request["requested_until"].endswith(("Z", "+00:00"))

    invalid_purpose = client.post(
        "/api/v1/platform/support-access-requests",
        json={
            "tenant_id": tenant.id,
            "ticket_reference": "SUP-2026-11",
            "purpose": "freeform",
            "requested_until": requested_until.isoformat(),
        },
    )
    assert invalid_purpose.status_code == 422


@pytest.mark.parametrize(
    "requested_until",
    [
        lambda: datetime.now(UTC) - timedelta(seconds=1),
        lambda: datetime.now(UTC) + timedelta(hours=9),
        lambda: datetime.now() + timedelta(hours=1),
    ],
)
def test_support_access_expiry_must_be_bounded_and_timezone_aware(
    platform_client: tuple[TestClient, Session, User, User, Tenant],
    requested_until: Callable[[], datetime],
) -> None:
    client, _, _, _, tenant = platform_client
    expiry = requested_until()

    response = client.post(
        "/api/v1/platform/support-access-requests",
        json={
            "tenant_id": tenant.id,
            "ticket_reference": "SUP-2026-12",
            "purpose": "account_configuration",
            "requested_until": expiry.isoformat(),
        },
    )

    assert response.status_code == 422
