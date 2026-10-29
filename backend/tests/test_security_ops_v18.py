"""V1.8 security hardening, health probes, support tickets, tenant isolation."""

from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import get_current_user
from app.config import settings
from app.db import Base, get_session
from app.main import app
from app.models import ClinicPatient, Tenant, TenantMembership, User
from app.security_hardening import token_has_mfa


@pytest.fixture
def v18_client() -> Generator[tuple[TestClient, Session, dict], None, None]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    session = session_factory()

    patient = User(issuer="https://identity.example", subject="p-v18")
    admin = User(issuer="https://identity.example", subject="a-v18")
    other_admin = User(issuer="https://identity.example", subject="a-other-v18")
    session.add_all([patient, admin, other_admin])
    session.flush()
    tenant = Tenant(slug="v18-clinic", display_name="V18 Clinic")
    other = Tenant(slug="v18-other", display_name="Other Clinic")
    session.add_all([tenant, other])
    session.flush()
    session.add_all(
        [
            TenantMembership(
                tenant_id=tenant.id, user_id=patient.id, role="patient", status="active"
            ),
            TenantMembership(
                tenant_id=tenant.id, user_id=admin.id, role="tenant_admin", status="active"
            ),
            TenantMembership(
                tenant_id=other.id, user_id=other_admin.id, role="tenant_admin", status="active"
            ),
            ClinicPatient(tenant_id=tenant.id, patient_user_id=patient.id, status="active"),
        ]
    )
    session.commit()

    current = {"user": admin}

    def override_session() -> Generator[Session, None, None]:
        yield session

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_current_user] = lambda: current["user"]

    actors = {
        "patient": patient,
        "admin": admin,
        "other_admin": other_admin,
        "tenant_id": tenant.id,
        "other_tenant_id": other.id,
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


def test_health_live_and_ready(v18_client) -> None:
    client, _session, _actors = v18_client
    live = client.get("/api/v1/health/live")
    assert live.status_code == 200
    assert live.json()["status"] == "alive"
    assert "X-Content-Type-Options" in live.headers
    assert live.headers["X-Content-Type-Options"] == "nosniff"
    assert live.headers["X-Frame-Options"] == "DENY"

    ready = client.get("/api/v1/health/ready")
    assert ready.status_code == 200
    assert ready.json()["status"] == "ready"


def test_auth_config_exposes_hardening_flags(v18_client) -> None:
    client, _session, _actors = v18_client
    cfg = client.get("/api/v1/auth/config")
    assert cfg.status_code == 200
    body = cfg.json()
    assert "require_mfa_for_platform_admin" in body
    assert "api_rate_limit_enabled" in body
    assert "launch_mode" in body


def test_mfa_claim_detection() -> None:
    assert token_has_mfa({"amr": ["pwd", "mfa"]}) is True
    assert token_has_mfa({"amr": ["pwd"]}) is False
    assert token_has_mfa({"acr": "aal2"}) is True
    assert token_has_mfa({"healthomatix_mfa": True}) is True
    assert token_has_mfa({}) is False


def test_cross_tenant_integrations_denied(v18_client) -> None:
    client, _session, actors = v18_client
    actors["current"]["user"] = actors["other_admin"]
    denied = client.get(
        f"/api/v1/tenants/{actors['tenant_id']}/integrations/connections"
    )
    assert denied.status_code == 404
    assert denied.json()["error"]["code"] == "TENANT_NOT_FOUND"


def test_cross_tenant_support_tickets_denied(v18_client) -> None:
    client, _session, actors = v18_client
    actors["current"]["user"] = actors["admin"]
    created = client.post(
        f"/api/v1/tenants/{actors['tenant_id']}/support/tickets",
        json={
            "category": "technical",
            "subject": "Cannot open schedule",
            "summary": "Clinic admin cannot open schedule page after login.",
        },
    )
    assert created.status_code == 201, created.text

    actors["current"]["user"] = actors["other_admin"]
    denied = client.get(f"/api/v1/tenants/{actors['tenant_id']}/support/tickets")
    assert denied.status_code == 404


def test_support_ticket_rejects_clinical_dump(v18_client) -> None:
    client, _session, actors = v18_client
    blocked = client.post(
        f"/api/v1/tenants/{actors['tenant_id']}/support/tickets",
        json={
            "category": "patient",
            "subject": "Question",
            "summary": "My diagnosis: diabetes and MRN: 12345",
        },
    )
    assert blocked.status_code == 422
    assert blocked.json()["error"]["code"] == "SUPPORT_SUMMARY_RESTRICTED"


def test_malware_marker_rejected(v18_client) -> None:
    client, _session, actors = v18_client
    actors["current"]["user"] = actors["patient"]
    # Document storage must be configured in settings for upload path
    if not settings.document_storage_configured:
        pytest.skip("document storage not configured")
    response = client.post(
        f"/api/v1/tenants/{actors['tenant_id']}/documents",
        files={
            "file": (
                "evil.txt",
                b"HEALTHOMATIX-FAKE-MALWARE payload",
                "text/plain",
            )
        },
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "DOCUMENT_REJECTED"
