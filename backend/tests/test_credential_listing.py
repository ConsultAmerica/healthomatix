from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import get_current_user
from app.db import Base, get_session
from app.main import app
from app.models import ProviderProfile, Tenant, TenantMembership, User


@pytest.fixture
def credential_client() -> Generator[
    tuple[TestClient, list[User], User, User, Tenant, Tenant], None, None
]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    session = session_factory()
    admin = User(issuer="https://identity.example", subject="admin-1")
    provider = User(issuer="https://identity.example", subject="provider-1")
    clinic_a = Tenant(slug="clinic-a", display_name="Clinic A")
    clinic_b = Tenant(slug="clinic-b", display_name="Clinic B")
    session.add_all((admin, provider, clinic_a, clinic_b))
    session.flush()
    session.add_all(
        (
            TenantMembership(tenant_id=clinic_a.id, user_id=admin.id, role="tenant_admin"),
            TenantMembership(tenant_id=clinic_b.id, user_id=admin.id, role="tenant_admin"),
            TenantMembership(tenant_id=clinic_a.id, user_id=provider.id, role="provider"),
            ProviderProfile(
                user_id=provider.id,
                display_name="Synthetic Provider",
                specialty="Family medicine",
                profile_status="active",
            ),
        )
    )
    session.commit()
    actor = [provider]

    def override_session() -> Generator[Session, None, None]:
        yield session

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_current_user] = lambda: actor[0]
    try:
        with TestClient(app) as client:
            yield client, actor, admin, provider, clinic_a, clinic_b
    finally:
        app.dependency_overrides.clear()
        session.close()
        Base.metadata.drop_all(engine)
        engine.dispose()


def _submit(client: TestClient, tenant_id: str) -> str:
    created = client.post(
        f"/api/v1/tenants/{tenant_id}/providers/me/credentials",
        json={
            "jurisdiction": "US-NY",
            "credential_type": "medical_license",
            "regulator": "Synthetic Licensing Board",
        },
    )
    assert created.status_code == 201, created.text
    return created.json()["credential_id"]


def test_provider_lists_own_credentials(
    credential_client: tuple[TestClient, list[User], User, User, Tenant, Tenant],
) -> None:
    client, _, _, _, clinic_a, _ = credential_client
    credential_id = _submit(client, clinic_a.id)

    listed = client.get(f"/api/v1/tenants/{clinic_a.id}/providers/me/credentials")

    assert listed.status_code == 200, listed.text
    assert listed.headers["cache-control"] == "no-store"
    assert [row["credential_id"] for row in listed.json()] == [credential_id]
    assert "verification_reference" not in listed.text


def test_admin_review_queue_is_tenant_scoped_and_reflects_decisions(
    credential_client: tuple[TestClient, list[User], User, User, Tenant, Tenant],
) -> None:
    client, actor, admin, provider, clinic_a, clinic_b = credential_client
    credential_id = _submit(client, clinic_a.id)

    forbidden = client.get(f"/api/v1/tenants/{clinic_a.id}/provider-credentials")
    assert forbidden.status_code == 403

    actor[0] = admin
    queue = client.get(f"/api/v1/tenants/{clinic_a.id}/provider-credentials")
    other_clinic = client.get(f"/api/v1/tenants/{clinic_b.id}/provider-credentials")
    invalid = client.get(
        f"/api/v1/tenants/{clinic_a.id}/provider-credentials", params={"status": "bogus"}
    )

    assert queue.status_code == 200, queue.text
    assert queue.json()[0]["credential_id"] == credential_id
    assert queue.json()[0]["provider_user_id"] == provider.id
    assert queue.json()[0]["provider_display_name"] == "Synthetic Provider"
    assert other_clinic.json() == []
    assert invalid.status_code == 422

    reviewed = client.post(
        f"/api/v1/tenants/{clinic_a.id}/providers/{provider.id}"
        f"/credentials/{credential_id}/review",
        json={"decision": "verified", "review_source": "Synthetic registry lookup"},
    )
    assert reviewed.status_code == 200, reviewed.text
    assert client.get(f"/api/v1/tenants/{clinic_a.id}/provider-credentials").json() == []
    verified = client.get(
        f"/api/v1/tenants/{clinic_a.id}/provider-credentials", params={"status": "verified"}
    )
    assert [row["credential_id"] for row in verified.json()] == [credential_id]
