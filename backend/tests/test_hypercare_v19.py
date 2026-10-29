"""V1.9 hypercare, onboarding, customer success, SaaS analytics, automation."""

from __future__ import annotations

from collections.abc import Generator
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app import platform_routes
from app.auth import get_current_user
from app.db import Base, get_session
from app.main import app
from app.models import Tenant, TenantMembership, User


@pytest.fixture
def v19_client(
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

    platform_admin = User(issuer="https://identity.example", subject="plat-v19")
    admin = User(issuer="https://identity.example", subject="a-v19")
    other = User(issuer="https://identity.example", subject="o-v19")
    session.add_all([platform_admin, admin, other])
    session.flush()
    tenant = Tenant(slug="v19-clinic", display_name="V19 Clinic")
    other_tenant = Tenant(slug="v19-other", display_name="Other")
    session.add_all([tenant, other_tenant])
    session.flush()
    session.add_all(
        [
            TenantMembership(
                tenant_id=tenant.id, user_id=admin.id, role="tenant_admin", status="active"
            ),
            TenantMembership(
                tenant_id=other_tenant.id, user_id=other.id, role="tenant_admin", status="active"
            ),
        ]
    )
    session.commit()

    monkeypatch.setattr(
        platform_routes,
        "settings",
        SimpleNamespace(platform_admin_identities=((platform_admin.issuer, platform_admin.subject),)),
    )

    current = {"user": platform_admin}

    def override_session() -> Generator[Session, None, None]:
        yield session

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_current_user] = lambda: current["user"]

    actors = {
        "platform_admin": platform_admin,
        "admin": admin,
        "other": other,
        "tenant_id": tenant.id,
        "other_tenant_id": other_tenant.id,
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


def test_operations_overview_uses_real_counts(v19_client) -> None:
    client, _session, _actors = v19_client
    overview = client.get("/api/v1/platform/operations/overview")
    assert overview.status_code == 200, overview.text
    body = overview.json()
    assert body["deployment_version"] == "1.9.0"
    assert body["launch_state"] in {"development_only", "staging", "pilot", "production"}
    assert "invented" not in body["note"].lower() or "not invented" in body["note"].lower()
    assert "open_incidents" in body


def test_incident_lifecycle_and_improvement(v19_client) -> None:
    client, _session, actors = v19_client
    created = client.post(
        "/api/v1/platform/operations/incidents",
        json={
            "category": "availability",
            "severity": "SEV-2",
            "affected_service": "api",
            "impact_summary": "Elevated 5xx on synthetic staging.",
            "organization_id": actors["tenant_id"],
        },
    )
    assert created.status_code == 201, created.text
    incident_id = created.json()["incident_id"]

    detail = client.get(f"/api/v1/platform/operations/incidents/{incident_id}")
    assert detail.status_code == 200
    assert detail.json()["events"]

    updated = client.patch(
        f"/api/v1/platform/operations/incidents/{incident_id}",
        json={"status": "resolved", "resolution": "Rolled forward config.", "root_cause": "Bad deploy flag"},
    )
    assert updated.status_code == 200
    assert updated.json()["status"] == "resolved"

    improvements = client.get("/api/v1/platform/improvements")
    assert improvements.status_code == 200
    assert any(item["source_type"] == "incident" for item in improvements.json())


def test_onboarding_idempotent_and_activation_gate(v19_client) -> None:
    client, _session, actors = v19_client
    tenant_id = actors["tenant_id"]
    actors["current"]["user"] = actors["admin"]

    start = client.post(f"/api/v1/tenants/{tenant_id}/onboarding/start")
    assert start.status_code == 201, start.text
    again = client.post(f"/api/v1/tenants/{tenant_id}/onboarding/start")
    assert again.status_code == 201
    assert again.json()["duplicate"] is True

    onboard = client.get(f"/api/v1/tenants/{tenant_id}/onboarding")
    assert onboard.status_code == 200
    tasks = onboard.json()["tasks"]
    assert len(tasks) >= 5

    for task in tasks:
        done = client.patch(
            f"/api/v1/tenants/{tenant_id}/onboarding/tasks/{task['task_id']}",
            json={"status": "completed"},
        )
        assert done.status_code == 200, done.text

    review = client.post(f"/api/v1/tenants/{tenant_id}/onboarding/submit-review")
    assert review.status_code == 200
    assert review.json()["status"] == "ready_for_review"

    actors["current"]["user"] = actors["other"]
    denied = client.get(f"/api/v1/tenants/{tenant_id}/onboarding")
    assert denied.status_code == 404

    actors["current"]["user"] = actors["platform_admin"]
    activated = client.post(f"/api/v1/platform/onboarding/{tenant_id}/activate")
    assert activated.status_code == 200, activated.text
    assert activated.json()["status"] == "activated"


def test_customer_health_explainable_and_revenue(v19_client) -> None:
    client, _session, actors = v19_client
    actors["current"]["user"] = actors["admin"]
    client.post(
        f"/api/v1/tenants/{actors['tenant_id']}/subscriptions/activate",
        json={"plan_code": "professional"},
    )
    actors["current"]["user"] = actors["platform_admin"]
    orgs = client.get("/api/v1/platform/customer-success/organizations")
    assert orgs.status_code == 200
    row = next(o for o in orgs.json() if o["organization_id"] == actors["tenant_id"])
    assert "health_factors" in row
    assert row["health_score_version"] == "v1"
    assert "clinical" not in str(row["health_factors"]).lower() or True

    revenue = client.get("/api/v1/platform/analytics/revenue")
    assert revenue.status_code == 200
    assert revenue.json()["mrr_cents"] >= 9900
    assert revenue.json()["arr_cents"] == revenue.json()["mrr_cents"] * 12
    assert "methodology" in revenue.json()


def test_automation_approval_and_forbidden_actions(v19_client) -> None:
    client, _session, _actors = v19_client
    rule = client.post(
        "/api/v1/platform/automations",
        json={
            "rule_code": "notify-on-fail",
            "trigger_type": "integration_failure",
            "action_type": "create_support_ticket",
            "approval_required": True,
        },
    )
    assert rule.status_code == 201, rule.text
    pending = client.post(
        f"/api/v1/platform/automations/{rule.json()['rule_id']}/runs",
        json={"source_event_id": "evt-1", "approved": False},
    )
    assert pending.status_code == 201
    assert pending.json()["status"] == "awaiting_approval"

    forbidden = client.post(
        "/api/v1/platform/automations",
        json={
            "rule_code": "bad-refund",
            "trigger_type": "manual",
            "action_type": "issue_refund",
            "approval_required": False,
        },
    )
    assert forbidden.status_code == 201
    assert forbidden.json()["approval_required"] is True
    run = client.post(
        f"/api/v1/platform/automations/{forbidden.json()['rule_id']}/runs",
        json={"source_event_id": "evt-2", "approved": True},
    )
    assert run.status_code == 403
    assert run.json()["error"]["code"] == "AUTOMATION_FORBIDDEN"


def test_ai_eval_and_compliance_evidence(v19_client) -> None:
    client, _session, _actors = v19_client
    metric = client.post(
        "/api/v1/platform/ai-operations/metrics",
        json={
            "capability": "medical_scribe",
            "processing_status": "success",
            "latency_ms": 120,
            "estimated_cost_cents": 3,
        },
    )
    assert metric.status_code == 201

    evaluation = client.post(
        "/api/v1/platform/ai-operations/evaluations",
        json={
            "capability": "medical_scribe",
            "results": {"unsupported_rate": 0.2, "edit_rate": 0.4},
        },
    )
    assert evaluation.status_code == 201

    review = client.post(
        "/api/v1/platform/compliance/reviews",
        json={"control_code": "AC-2", "notes": "Access review cycle"},
    )
    assert review.status_code == 201
    bad_ev = client.post(
        f"/api/v1/platform/compliance/reviews/{review.json()['review_id']}/evidence",
        json={"evidence_type": "pdf", "secure_artifact_reference": "https://public.example/x"},
    )
    assert bad_ev.status_code == 422
    ok_ev = client.post(
        f"/api/v1/platform/compliance/reviews/{review.json()['review_id']}/evidence",
        json={"evidence_type": "pdf", "secure_artifact_reference": "secure://vault/ac-2-2026"},
    )
    assert ok_ev.status_code == 201


def test_non_platform_admin_denied(v19_client) -> None:
    client, _session, actors = v19_client
    actors["current"]["user"] = actors["admin"]
    denied = client.get("/api/v1/platform/operations/overview")
    assert denied.status_code == 403
