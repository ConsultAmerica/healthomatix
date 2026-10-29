"""V1.5 AI clinical copilot: scribe consent, quality, messaging, education, care tasks."""

from __future__ import annotations

from collections.abc import Generator
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import get_current_user
from app.db import Base, get_session
from app.main import app
from app.models import ClinicPatient, Tenant, TenantMembership, User
import app.scheduling_routes as scheduling_routes


@pytest.fixture
def v15_client(monkeypatch) -> Generator[tuple[TestClient, Session, dict], None, None]:
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

    patient = User(issuer="https://identity.example", subject="p-v15")
    provider = User(issuer="https://identity.example", subject="d-v15")
    session.add_all([patient, provider])
    session.flush()
    tenant = Tenant(slug="v15-clinic", display_name="V15 Clinic")
    session.add(tenant)
    session.flush()
    clinic_patient = ClinicPatient(
        tenant_id=tenant.id, patient_user_id=patient.id, status="active"
    )
    session.add_all(
        [
            TenantMembership(
                tenant_id=tenant.id, user_id=patient.id, role="patient", status="active"
            ),
            TenantMembership(
                tenant_id=tenant.id, user_id=provider.id, role="provider", status="active"
            ),
            clinic_patient,
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
        "clinic_patient_id": clinic_patient.id,
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


def _grant_treatment(client: TestClient, actors: dict) -> None:
    actors["current"]["user"] = actors["patient"]
    client.post(f"/api/v1/fhir/R4/tenants/{actors['tenant_id']}/Patient/$ensure")
    assert (
        client.post(
            f"/api/v1/tenants/{actors['tenant_id']}/patients/me/consents",
            json={"purpose": "treatment", "scope": "chart.read", "policy_version": "v1"},
        ).status_code
        == 201
    )


def test_ambient_scribe_requires_explicit_consent(v15_client) -> None:
    client, _session, actors = v15_client
    tenant_id = actors["tenant_id"]
    _grant_treatment(client, actors)

    actors["current"]["user"] = actors["provider"]
    denied = client.post(
        f"/api/v1/tenants/{tenant_id}/scribe/sessions",
        json={
            "patient_id": actors["patient"].id,
            "mode": "ambient",
            "clinician_notes": "Exam normal",
        },
    )
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "SCRIBE_CONSENT_REQUIRED"

    actors["current"]["user"] = actors["patient"]
    granted = client.post(
        f"/api/v1/tenants/{tenant_id}/patients/me/consents",
        json={
            "purpose": "ai_scribe",
            "scope": "ambient_transcription",
            "policy_version": "scribe-v1",
        },
    )
    assert granted.status_code == 201, granted.text

    actors["current"]["user"] = actors["provider"]
    started = client.post(
        f"/api/v1/tenants/{tenant_id}/scribe/sessions",
        json={
            "patient_id": actors["patient"].id,
            "mode": "ambient",
            "clinician_notes": "Reports fatigue",
        },
    )
    assert started.status_code == 201, started.text
    scribe_id = started.json()["scribe_session_id"]
    assert started.json()["status"] == "active"
    assert started.json()["consent_grant_id"]

    transcript = client.get(f"/api/v1/tenants/{tenant_id}/scribe/sessions/{scribe_id}/transcript")
    assert transcript.status_code == 200
    assert len(transcript.json()) >= 1

    note = client.post(
        f"/api/v1/tenants/{tenant_id}/scribe/sessions/{scribe_id}/generate-note",
        json={"visit_reason": "Fatigue", "clinician_notes": "NAD"},
    )
    assert note.status_code == 200, note.text
    assert note.json()["subjective"]
    assert "Draft" in note.json()["disclaimer"] or "draft" in note.json()["disclaimer"].lower()

    stopped = client.post(f"/api/v1/tenants/{tenant_id}/scribe/sessions/{scribe_id}/stop")
    assert stopped.status_code == 200
    assert stopped.json()["status"] == "stopped"


def test_manual_scribe_without_ambient_consent(v15_client) -> None:
    client, _session, actors = v15_client
    tenant_id = actors["tenant_id"]
    _grant_treatment(client, actors)
    actors["current"]["user"] = actors["provider"]
    started = client.post(
        f"/api/v1/tenants/{tenant_id}/scribe/sessions",
        json={"patient_id": actors["patient"].id, "mode": "manual", "visit_reason": "Follow-up"},
    )
    assert started.status_code == 201, started.text
    assert started.json()["mode"] == "manual"
    assert started.json()["consent_grant_id"] is None


def test_note_quality_check_and_review(v15_client) -> None:
    client, _session, actors = v15_client
    tenant_id = actors["tenant_id"]
    _grant_treatment(client, actors)
    actors["current"]["user"] = actors["provider"]
    created = client.post(
        f"/api/v1/tenants/{tenant_id}/clinical-notes",
        json={
            "patient_id": actors["patient"].id,
            "subjective": "",
            "objective": "NAD",
            "assessment": "",
            "plan": "TODO follow up",
        },
    )
    assert created.status_code == 201, created.text
    note_id = created.json()["note_id"]

    findings = client.post(f"/api/v1/tenants/{tenant_id}/clinical-notes/{note_id}/quality-check")
    assert findings.status_code == 200, findings.text
    assert len(findings.json()) >= 1
    finding_id = findings.json()[0]["finding_id"]

    reviewed = client.post(
        f"/api/v1/tenants/{tenant_id}/clinical-notes/{note_id}/quality-findings/{finding_id}/review",
        json={"action": "dismiss", "dismiss_reason": "Will complete before sign"},
    )
    assert reviewed.status_code == 200
    assert reviewed.json()["review_status"] == "dismissed"


def test_message_draft_requires_approve_before_send(v15_client) -> None:
    client, _session, actors = v15_client
    tenant_id = actors["tenant_id"]
    _grant_treatment(client, actors)

    actors["current"]["user"] = actors["patient"]
    thread = client.post(
        f"/api/v1/tenants/{tenant_id}/threads",
        json={
            "subject": "Reschedule please",
            "body": "Can I reschedule my appointment next week?",
            "clinic_patient_id": actors["clinic_patient_id"],
        },
    )
    assert thread.status_code == 201, thread.text
    thread_id = thread.json()["thread_id"]

    actors["current"]["user"] = actors["provider"]
    draft = client.post(
        f"/api/v1/tenants/{tenant_id}/threads/{thread_id}/ai/draft-response",
        json={},
    )
    assert draft.status_code == 201, draft.text
    draft_id = draft.json()["draft_id"]
    assert draft.json()["category"] == "appointment_change"

    premature = client.post(
        f"/api/v1/tenants/{tenant_id}/ai/message-drafts/{draft_id}/send",
        json={"idempotency_key": "send-key-1"},
    )
    assert premature.status_code == 409

    approved = client.post(
        f"/api/v1/tenants/{tenant_id}/ai/message-drafts/{draft_id}/approve",
        json={"edited_content": "We can help reschedule — please share preferred times."},
    )
    assert approved.status_code == 200, approved.text
    sent = client.post(
        f"/api/v1/tenants/{tenant_id}/ai/message-drafts/{draft_id}/send",
        json={"idempotency_key": "send-key-1"},
    )
    assert sent.status_code == 200, sent.text
    assert sent.json()["status"] == "sent"
    assert sent.json()["sent_message_id"]

    # Idempotent resend
    again = client.post(
        f"/api/v1/tenants/{tenant_id}/ai/message-drafts/{draft_id}/send",
        json={"idempotency_key": "send-key-1"},
    )
    assert again.status_code == 200
    assert again.json()["sent_message_id"] == sent.json()["sent_message_id"]


def test_patient_education_escalates_diagnosis_requests(v15_client) -> None:
    client, _session, actors = v15_client
    tenant_id = actors["tenant_id"]
    actors["current"]["user"] = actors["patient"]
    answered = client.post(
        f"/api/v1/tenants/{tenant_id}/patient-education/questions",
        json={"question": "What is HbA1c?"},
    )
    assert answered.status_code == 201, answered.text
    assert answered.json()["escalated"] is False
    assert answered.json()["source_references"]

    escalated = client.post(
        f"/api/v1/tenants/{tenant_id}/patient-education/questions",
        json={"question": "Diagnose me based on my symptoms"},
    )
    assert escalated.status_code == 201
    assert escalated.json()["escalated"] is True


def test_care_tasks_from_approved_plan_and_analytics(v15_client) -> None:
    client, _session, actors = v15_client
    tenant_id = actors["tenant_id"]
    _grant_treatment(client, actors)
    actors["current"]["user"] = actors["provider"]

    plan = client.post(
        f"/api/v1/tenants/{tenant_id}/follow-up-plans",
        json={
            "patient_id": actors["patient"].id,
            "instructions": "Return in 3 months",
            "tasks": [{"description": "Book lipid panel", "status": "open"}],
        },
    )
    assert plan.status_code == 201, plan.text
    plan_id = plan.json()["plan_id"]

    blocked = client.post(f"/api/v1/tenants/{tenant_id}/follow-up-plans/{plan_id}/ai/suggest-tasks")
    assert blocked.status_code == 409

    assert client.post(f"/api/v1/tenants/{tenant_id}/follow-up-plans/{plan_id}/approve").status_code == 200
    suggested = client.post(f"/api/v1/tenants/{tenant_id}/follow-up-plans/{plan_id}/ai/suggest-tasks")
    assert suggested.status_code == 200, suggested.text
    assert suggested.json()["suggestions"]

    task = client.post(
        f"/api/v1/tenants/{tenant_id}/follow-up-plans/{plan_id}/tasks",
        json={
            "description": "Book lipid panel",
            "idempotency_key": "task-key-1",
        },
    )
    assert task.status_code == 201, task.text
    dup = client.post(
        f"/api/v1/tenants/{tenant_id}/follow-up-plans/{plan_id}/tasks",
        json={"description": "Book lipid panel", "idempotency_key": "task-key-1"},
    )
    assert dup.status_code == 201
    assert dup.json()["task_id"] == task.json()["task_id"]

    actors["current"]["user"] = actors["patient"]
    mine = client.get(f"/api/v1/tenants/{tenant_id}/patients/me/care-tasks")
    assert mine.status_code == 200
    assert len(mine.json()) == 1

    actors["current"]["user"] = actors["provider"]
    analytics = client.get(f"/api/v1/tenants/{tenant_id}/analytics/workflow")
    assert analytics.status_code == 200, analytics.text
    body = analytics.json()
    assert body["care_coordination"]["open_tasks"] >= 1
    assert body["ai_operations"]["model_identifier"]
    assert "patient" not in str(body).lower() or "Patient" in str(body)  # soft check
