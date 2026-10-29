"""V1.6 insurance eligibility, claims sandbox, remittance ledger, SaaS entitlements."""

from __future__ import annotations

from collections.abc import Generator
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import get_current_user
from app.db import Base, get_session
from app.main import app
from app.models import Tenant, TenantMembership, User


@pytest.fixture
def v16_client() -> Generator[tuple[TestClient, Session, dict], None, None]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    session = session_factory()

    patient = User(issuer="https://identity.example", subject="p-v16")
    admin = User(issuer="https://identity.example", subject="a-v16")
    other_admin = User(issuer="https://identity.example", subject="a-other-v16")
    session.add_all([patient, admin, other_admin])
    session.flush()
    tenant = Tenant(slug="v16-clinic", display_name="V16 Clinic")
    other = Tenant(slug="v16-other", display_name="Other Clinic")
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


def _entitle_rcm(client: TestClient, actors: dict) -> None:
    actors["current"]["user"] = actors["admin"]
    activated = client.post(
        f"/api/v1/tenants/{actors['tenant_id']}/subscriptions/activate",
        json={"plan_code": "professional"},
    )
    assert activated.status_code == 201, activated.text
    entitlements = client.get(f"/api/v1/tenants/{actors['tenant_id']}/entitlements")
    assert entitlements.status_code == 200
    codes = {row["feature_code"] for row in entitlements.json() if row["enabled"]}
    assert "rcm" in codes


def test_rcm_requires_entitlement(v16_client) -> None:
    client, _session, actors = v16_client
    tenant_id = actors["tenant_id"]
    payer = client.post(
        f"/api/v1/tenants/{tenant_id}/insurance/payers",
        json={"name": "Acme Health", "payer_identifier": "ACME01"},
    )
    assert payer.status_code == 201
    blocked = client.post(
        f"/api/v1/tenants/{tenant_id}/patients/{actors['patient'].id}/insurance",
        json={
            "patient_id": actors["patient"].id,
            "payer_id": payer.json()["payer_id"],
            "member_identifier": "MEM123456",
            "plan_name": "Gold",
        },
    )
    assert blocked.status_code == 403
    assert blocked.json()["error"]["code"] == "FEATURE_NOT_ENTITLED"


def test_eligibility_claims_remittance_ledger_flow(v16_client) -> None:
    client, _session, actors = v16_client
    tenant_id = actors["tenant_id"]
    patient_id = actors["patient"].id
    _entitle_rcm(client, actors)

    payer = client.post(
        f"/api/v1/tenants/{tenant_id}/insurance/payers",
        json={"name": "Acme Health", "payer_identifier": "ACME01"},
    )
    assert payer.status_code == 201, payer.text
    payer_id = payer.json()["payer_id"]

    policy = client.post(
        f"/api/v1/tenants/{tenant_id}/patients/{patient_id}/insurance",
        json={
            "patient_id": patient_id,
            "payer_id": payer_id,
            "member_identifier": "MEM123456",
            "plan_name": "Gold PPO",
            "coverage_order": 1,
        },
    )
    assert policy.status_code == 201, policy.text
    assert policy.json()["member_identifier"].endswith("3456")
    assert "*" in policy.json()["member_identifier"]

    elig = client.post(
        f"/api/v1/tenants/{tenant_id}/insurance/policies/{policy.json()['policy_id']}/verify-eligibility",
        json={},
    )
    assert elig.status_code == 200, elig.text
    assert elig.json()["coverage_status"] == "active"
    assert "does not guarantee" in elig.json()["disclaimer"].lower()

    encounter_id = "00000000-0000-4000-8000-000000000101"
    charge = client.post(
        f"/api/v1/tenants/{tenant_id}/encounters/{encounter_id}/charges",
        json={
            "encounter_id": encounter_id,
            "patient_id": patient_id,
            "provider_user_id": actors["admin"].id,
            "service_date": date.today().isoformat(),
            "service_code": "99213",
            "diagnosis_codes": ["J06.9"],
            "units": 1,
            "charge_amount_cents": 15000,
            "documentation_references": [f"Encounter/{encounter_id}"],
        },
    )
    assert charge.status_code == 201, charge.text
    charge_id = charge.json()["charge_id"]
    reviewed = client.post(f"/api/v1/tenants/{tenant_id}/charges/{charge_id}/ai-review")
    assert reviewed.status_code == 200
    assert reviewed.json()["ai_suggested"] is True
    approved = client.post(f"/api/v1/tenants/{tenant_id}/charges/{charge_id}/approve")
    assert approved.status_code == 200
    assert approved.json()["status"] == "approved"

    claim = client.post(
        f"/api/v1/tenants/{tenant_id}/claims",
        json={
            "patient_id": patient_id,
            "encounter_id": encounter_id,
            "payer_id": payer_id,
            "insurance_policy_id": policy.json()["policy_id"],
            "rendering_provider_user_id": actors["admin"].id,
            "charge_ids": [charge_id],
            "diagnosis_codes": ["J06.9"],
        },
    )
    assert claim.status_code == 201, claim.text
    claim_id = claim.json()["claim_id"]
    assert client.post(f"/api/v1/tenants/{tenant_id}/claims/{claim_id}/approve").status_code == 200

    submitted = client.post(
        f"/api/v1/tenants/{tenant_id}/claims/{claim_id}/submit",
        json={"idempotency_key": "submit-1"},
    )
    assert submitted.status_code == 200, submitted.text
    assert submitted.json()["submission_status"] == "accepted"
    again = client.post(
        f"/api/v1/tenants/{tenant_id}/claims/{claim_id}/submit",
        json={"idempotency_key": "submit-1"},
    )
    assert again.json()["submission_id"] == submitted.json()["submission_id"]

    remit = client.post(
        f"/api/v1/tenants/{tenant_id}/rcm/remittances/import",
        json={"claim_id": claim_id, "deny": False},
    )
    assert remit.status_code == 201, remit.text

    billing = client.get(f"/api/v1/tenants/{tenant_id}/patients/{patient_id}/billing")
    assert billing.status_code == 200, billing.text
    assert isinstance(billing.json()["balance_cents"], int)
    assert len(billing.json()["transactions"]) >= 1

    analytics = client.get(f"/api/v1/tenants/{tenant_id}/analytics/rcm/overview")
    assert analytics.status_code == 200, analytics.text
    assert analytics.json()["overview"]["claims"] >= 1
    assert analytics.json()["overview"]["payments_posted_cents"] >= 0


def test_denial_import_and_resolve(v16_client) -> None:
    client, _session, actors = v16_client
    tenant_id = actors["tenant_id"]
    patient_id = actors["patient"].id
    _entitle_rcm(client, actors)
    payer_id = client.post(
        f"/api/v1/tenants/{tenant_id}/insurance/payers",
        json={"name": "DenyCo", "payer_identifier": "DENY01"},
    ).json()["payer_id"]
    encounter_id = "00000000-0000-4000-8000-000000000202"
    charge_id = client.post(
        f"/api/v1/tenants/{tenant_id}/encounters/{encounter_id}/charges",
        json={
            "encounter_id": encounter_id,
            "patient_id": patient_id,
            "provider_user_id": actors["admin"].id,
            "service_date": date.today().isoformat(),
            "service_code": "99214",
            "diagnosis_codes": ["R53.83"],
            "charge_amount_cents": 20000,
        },
    ).json()["charge_id"]
    client.post(f"/api/v1/tenants/{tenant_id}/charges/{charge_id}/approve")
    claim_id = client.post(
        f"/api/v1/tenants/{tenant_id}/claims",
        json={
            "patient_id": patient_id,
            "encounter_id": encounter_id,
            "payer_id": payer_id,
            "rendering_provider_user_id": actors["admin"].id,
            "charge_ids": [charge_id],
            "diagnosis_codes": ["R53.83"],
        },
    ).json()["claim_id"]
    client.post(f"/api/v1/tenants/{tenant_id}/claims/{claim_id}/approve")
    client.post(
        f"/api/v1/tenants/{tenant_id}/claims/{claim_id}/submit",
        json={"idempotency_key": "deny-submit"},
    )
    assert (
        client.post(
            f"/api/v1/tenants/{tenant_id}/rcm/remittances/import",
            json={"claim_id": claim_id, "deny": True},
        ).status_code
        == 201
    )
    denials = client.get(f"/api/v1/tenants/{tenant_id}/rcm/denials")
    assert denials.status_code == 200
    assert len(denials.json()) >= 1
    denial_id = denials.json()[0]["denial_id"]
    assigned = client.post(
        f"/api/v1/tenants/{tenant_id}/rcm/denials/{denial_id}/assign",
        json={"assigned_to_user_id": actors["admin"].id},
    )
    assert assigned.status_code == 200
    resolved = client.post(
        f"/api/v1/tenants/{tenant_id}/rcm/denials/{denial_id}/resolve",
        json={"resolution_notes": "Corrected coding; will resubmit after review."},
    )
    assert resolved.status_code == 200
    assert resolved.json()["status"] == "resolved"


def test_usage_meter_idempotent_and_cross_tenant_denied(v16_client) -> None:
    client, _session, actors = v16_client
    tenant_id = actors["tenant_id"]
    _entitle_rcm(client, actors)
    first = client.post(
        f"/api/v1/tenants/{tenant_id}/usage-meter",
        json={
            "meter_type": "ai_transcription_minutes",
            "quantity": 12,
            "source_event_id": "evt-usage-1",
        },
    )
    assert first.status_code == 201, first.text
    second = client.post(
        f"/api/v1/tenants/{tenant_id}/usage-meter",
        json={
            "meter_type": "ai_transcription_minutes",
            "quantity": 12,
            "source_event_id": "evt-usage-1",
        },
    )
    assert second.status_code == 201
    assert second.json()["meter_event_id"] == first.json()["meter_event_id"]

    actors["current"]["user"] = actors["other_admin"]
    denied = client.get(f"/api/v1/tenants/{tenant_id}/analytics/rcm/overview")
    assert denied.status_code == 404
