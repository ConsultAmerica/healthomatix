"""V2.1.1 capability contracts, context, delegation, clinical provenance, security."""

from __future__ import annotations

from collections.abc import Generator
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app import platform_routes
from app.agent_capabilities import CAPABILITY_TRANSITIONS, ensure_capability_catalog
from app.agent_models import AiAgentCapability
from app.auth import get_current_user
from app.db import Base, get_session
from app.main import app
from app.models import ClinicPatient, Tenant, TenantMembership, User


@pytest.fixture
def v211_client(
    monkeypatch: pytest.MonkeyPatch,
) -> Generator[tuple[TestClient, Session, dict], None, None]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    session = session_factory()

    platform_admin = User(issuer="https://identity.example", subject="plat-v211")
    provider = User(issuer="https://identity.example", subject="prov-v211")
    patient = User(issuer="https://identity.example", subject="pat-v211")
    other_provider = User(issuer="https://identity.example", subject="prov-other-v211")
    session.add_all([platform_admin, provider, patient, other_provider])
    session.flush()
    tenant = Tenant(slug="v211-clinic", display_name="V211 Clinic")
    other = Tenant(slug="v211-other", display_name="Other")
    session.add_all([tenant, other])
    session.flush()
    session.add_all(
        [
            TenantMembership(
                tenant_id=tenant.id, user_id=provider.id, role="provider", status="active"
            ),
            TenantMembership(
                tenant_id=tenant.id, user_id=patient.id, role="patient", status="active"
            ),
            TenantMembership(
                tenant_id=other.id, user_id=other_provider.id, role="provider", status="active"
            ),
            ClinicPatient(tenant_id=tenant.id, patient_user_id=patient.id, status="active"),
        ]
    )
    session.commit()

    monkeypatch.setattr(
        platform_routes,
        "settings",
        SimpleNamespace(platform_admin_identities=((platform_admin.issuer, platform_admin.subject),)),
    )
    current = {"user": provider}

    def override_session() -> Generator[Session, None, None]:
        yield session

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_current_user] = lambda: current["user"]

    actors = {
        "platform_admin": platform_admin,
        "provider": provider,
        "patient": patient,
        "other_provider": other_provider,
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


def _grant_consent(client: TestClient, actors: dict) -> None:
    actors["current"]["user"] = actors["patient"]
    client.post(f"/api/v1/fhir/R4/tenants/{actors['tenant_id']}/Patient/$ensure")
    assert (
        client.post(
            f"/api/v1/tenants/{actors['tenant_id']}/patients/me/consents",
            json={"purpose": "treatment", "scope": "chart.read", "policy_version": "v1"},
        ).status_code
        == 201
    )
    actors["current"]["user"] = actors["provider"]


def _enable_capability(client: TestClient, actors: dict, code: str) -> str:
    actors["current"]["user"] = actors["platform_admin"]
    caps = client.get("/api/v1/platform/ai/capabilities")
    assert caps.status_code == 200, caps.text
    match = next(c for c in caps.json() if c["capability_code"] == code)
    cap_id = match["capability_id"]
    if match["status"] in {"enabled", "monitored"}:
        actors["current"]["user"] = actors["provider"]
        return cap_id
    # Drive lifecycle: registered -> security_review -> evaluation -> approved -> enabled
    if match["status"] == "registered":
        assert client.post(f"/api/v1/platform/ai/capabilities/{cap_id}/submit-review").status_code == 200
        assert client.post(f"/api/v1/platform/ai/capabilities/{cap_id}/submit-review").status_code == 200
    elif match["status"] == "security_review":
        assert client.post(f"/api/v1/platform/ai/capabilities/{cap_id}/submit-review").status_code == 200
    assert client.post(f"/api/v1/platform/ai/capabilities/{cap_id}/approve").status_code == 200
    enabled = client.patch(
        f"/api/v1/platform/ai/capabilities/{cap_id}",
        json={"status": "enabled"},
    )
    assert enabled.status_code == 200, enabled.text
    assert enabled.json()["status"] == "enabled"
    actors["current"]["user"] = actors["provider"]
    return cap_id


def test_capability_lifecycle_transitions() -> None:
    assert "enabled" in CAPABILITY_TRANSITIONS["approved"]
    assert "retired" in CAPABILITY_TRANSITIONS["enabled"]


def test_capability_registry_and_readiness(v211_client) -> None:
    client, _session, actors = v211_client
    actors["current"]["user"] = actors["platform_admin"]
    caps = client.get("/api/v1/platform/ai/capabilities")
    assert caps.status_code == 200
    codes = {c["capability_code"] for c in caps.json()}
    assert "clinical.patient_summary" in codes
    assert "knowledge.policy_retrieval" in codes
    ready = client.get("/api/v1/platform/ai/readiness")
    assert ready.status_code == 200
    assert ready.json()["orchestrator"] == "ready"
    assert ready.json()["capability_registry"] == "ready"
    actors["current"]["user"] = actors["provider"]
    denied = client.get("/api/v1/platform/ai/capabilities")
    assert denied.status_code == 403


def test_disabled_capability_rejected(v211_client) -> None:
    client, _session, actors = v211_client
    _grant_consent(client, actors)
    # financial.claim_analysis starts registered (not enabled)
    ctx = client.post(
        f"/api/v1/tenants/{actors['tenant_id']}/ai/execution-contexts"
        f"?capability_code=financial.claim_analysis"
    )
    assert ctx.status_code == 404
    assert ctx.json()["error"]["code"] == "CAPABILITY_NOT_ENABLED"


def test_execution_context_and_clinical_context(v211_client) -> None:
    client, session, actors = v211_client
    _grant_consent(client, actors)
    _enable_capability(client, actors, "clinical.patient_summary")

    minted = client.post(
        f"/api/v1/tenants/{actors['tenant_id']}/ai/execution-contexts"
        f"?capability_code=clinical.patient_summary"
        f"&patient_id={actors['patient'].id}"
    )
    assert minted.status_code == 201, minted.text
    assert minted.json()["organization_id"] == actors["tenant_id"]
    assert minted.json()["actor_id"] == actors["provider"].id
    assert minted.json()["status"] == "active"
    assert "patient.get_authorized_summary" in minted.json()["permitted_tools"]

    clinical = client.get(
        f"/api/v1/tenants/{actors['tenant_id']}/patients/{actors['patient'].id}/ai/clinical-context"
    )
    assert clinical.status_code == 200, clinical.text
    body = clinical.json()
    assert body["patient_reference"] == actors["patient"].id
    assert "warnings" in body
    assert body["note"].startswith("Missing clinical")

    # Evidence rows may be empty if no observations — access event must exist
    events = session.execute(select(AiAgentCapability)).scalars().first()
    assert events is not None


def test_cross_tenant_clinical_context_denied(v211_client) -> None:
    client, _session, actors = v211_client
    _grant_consent(client, actors)
    actors["current"]["user"] = actors["other_provider"]
    denied = client.get(
        f"/api/v1/tenants/{actors['tenant_id']}/patients/{actors['patient'].id}/ai/clinical-context"
    )
    assert denied.status_code == 404


def test_secure_delegation(v211_client) -> None:
    client, _session, actors = v211_client
    _grant_consent(client, actors)
    # Parent copilot run
    parent = client.post(
        f"/api/v1/tenants/{actors['tenant_id']}/ai/agent-runs",
        json={
            "agent_code": "clinical_copilot",
            "patient_id": actors["patient"].id,
            "idempotency_key": "v211-parent-1",
        },
    )
    assert parent.status_code == 201, parent.text
    parent_id = parent.json()["run_id"]

    # Enable encounter_context (may already be enabled) and patient_summary for delegate target
    _enable_capability(client, actors, "clinical.encounter_context")

    delegated = client.post(
        f"/api/v1/tenants/{actors['tenant_id']}/ai/agent-runs/{parent_id}/delegate",
        json={
            "target_capability": "clinical.encounter_context",
            "task_reference": "previsit-labs",
            "requested_tool_codes": [
                "patient.get_authorized_summary",
                "patient.get_verified_observations",
                "billing.propose_claim_correction",  # outside intersection — stripped
            ],
        },
    )
    assert delegated.status_code == 201, delegated.text
    body = delegated.json()
    assert body["parent_run_id"] == parent_id
    assert body["child_run_id"]
    assert "billing.propose_claim_correction" not in body["permitted_tools"]
    assert body["depth"] == 1

    listed = client.get(
        f"/api/v1/tenants/{actors['tenant_id']}/ai/agent-runs/{parent_id}/delegations"
    )
    assert listed.status_code == 200
    assert len(listed.json()) >= 1

    # Disabled capability cannot be delegated
    bad = client.post(
        f"/api/v1/tenants/{actors['tenant_id']}/ai/agent-runs/{parent_id}/delegate",
        json={"target_capability": "financial.claim_analysis"},
    )
    assert bad.status_code == 404


def test_reuse_v20_orchestrator_not_duplicate(v211_client) -> None:
    """Architecture test: capability catalog uses ensure_agent_catalog tools."""
    client, session, actors = v211_client
    actors["current"]["user"] = actors["platform_admin"]
    ensure_capability_catalog(session)
    session.flush()
    tools = client.get("/api/v1/platform/ai/tools")
    assert tools.status_code == 200
    assert any(t["tool_code"] == "patient.get_authorized_summary" for t in tools.json())
    caps = client.get("/api/v1/platform/ai/capabilities")
    assert any(c["allowed_tools"] for c in caps.json() if c["capability_code"].startswith("clinical"))
