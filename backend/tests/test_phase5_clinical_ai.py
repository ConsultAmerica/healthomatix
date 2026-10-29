from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import get_current_user
from app.db import Base, get_session
from app.fhir_models import ClinicalDraft, FhirResource
from app.main import app
from app.models import ClinicPatient, Tenant, TenantMembership, User


@pytest.fixture
def ai_client() -> Generator[tuple[TestClient, Session, dict], None, None]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    session = session_factory()

    patient = User(issuer="https://identity.example", subject="p-ai")
    clinician = User(issuer="https://identity.example", subject="c-ai")
    session.add_all([patient, clinician])
    session.flush()
    tenant = Tenant(slug="ai-clinic", display_name="AI Clinic")
    session.add(tenant)
    session.flush()
    session.add_all(
        [
            TenantMembership(
                tenant_id=tenant.id, user_id=patient.id, role="patient", status="active"
            ),
            TenantMembership(
                tenant_id=tenant.id, user_id=clinician.id, role="provider", status="active"
            ),
            ClinicPatient(tenant_id=tenant.id, patient_user_id=patient.id, status="active"),
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
        "clinician": clinician,
        "tenant_id": tenant.id,
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


def _consent_and_obs(client: TestClient, actors: dict) -> None:
    tenant_id = actors["tenant_id"]
    patient: User = actors["patient"]
    current = actors["current"]
    current["user"] = patient
    client.post(f"/api/v1/fhir/R4/tenants/{tenant_id}/Patient/$ensure")
    assert (
        client.post(
            f"/api/v1/tenants/{tenant_id}/patients/me/consents",
            json={"purpose": "treatment", "scope": "chart.read", "policy_version": "v1"},
        ).status_code
        == 201
    )
    current["user"] = actors["clinician"]
    assert (
        client.post(
            f"/api/v1/fhir/R4/tenants/{tenant_id}/Observation",
            json={
                "resourceType": "Observation",
                "status": "final",
                "code": {"text": "Glucose"},
                "subject": {"reference": f"Patient/{patient.id}"},
                "valueQuantity": {"value": 118, "unit": "mg/dL"},
            },
        ).status_code
        == 201
    )


def test_summary_stays_draft_until_approved(ai_client: tuple) -> None:
    client, session, actors = ai_client
    tenant_id = actors["tenant_id"]
    patient: User = actors["patient"]
    _consent_and_obs(client, actors)

    current = actors["current"]
    current["user"] = actors["clinician"]
    created = client.post(
        f"/api/v1/tenants/{tenant_id}/summaries",
        json={"patient_id": patient.id},
    )
    assert created.status_code == 201, created.text
    draft = created.json()
    assert draft["status"] == "draft"
    assert draft["draft_type"] == "summary"
    assert draft["source_links"]

    # Unapproved draft must not appear as Composition in FHIR store
    assert (
        session.scalar(
            select(FhirResource).where(FhirResource.resource_type == "Composition")
        )
        is None
    )

    approved = client.post(
        f"/api/v1/tenants/{tenant_id}/drafts/{draft['draft_id']}/approve",
        json={},
    )
    assert approved.status_code == 200, approved.text
    body = approved.json()
    assert body["status"] == "approved"
    assert body["approved_resource_id"]

    composition = session.execute(
        select(FhirResource).where(
            FhirResource.id == body["approved_resource_id"],
            FhirResource.resource_type == "Composition",
        )
    ).scalar_one()
    assert composition.patient_id == patient.id

    stored = session.get(ClinicalDraft, draft["draft_id"])
    assert stored is not None and stored.status == "approved"


def test_note_and_tasks_approval(ai_client: tuple) -> None:
    client, session, actors = ai_client
    tenant_id = actors["tenant_id"]
    patient: User = actors["patient"]
    _consent_and_obs(client, actors)
    current = actors["current"]
    current["user"] = actors["clinician"]

    note = client.post(
        f"/api/v1/tenants/{tenant_id}/notes",
        json={"patient_id": patient.id},
    )
    assert note.status_code == 201, note.text
    note_id = note.json()["draft_id"]
    approved_note = client.post(
        f"/api/v1/tenants/{tenant_id}/drafts/{note_id}/approve",
        json={"edited_title": "Approved visit note"},
    )
    assert approved_note.status_code == 200
    assert approved_note.json()["title"] == "Approved visit note"

    tasks = client.post(
        f"/api/v1/tenants/{tenant_id}/tasks",
        json={"patient_id": patient.id},
    )
    assert tasks.status_code == 201, tasks.text
    task_draft_id = tasks.json()["draft_id"]
    approved_tasks = client.post(
        f"/api/v1/tenants/{tenant_id}/drafts/{task_draft_id}/approve",
        json={},
    )
    assert approved_tasks.status_code == 200
    assert session.scalar(
        select(FhirResource).where(FhirResource.resource_type == "Task")
    )


def test_unapproved_drafts_not_in_record(ai_client: tuple) -> None:
    client, session, actors = ai_client
    tenant_id = actors["tenant_id"]
    patient: User = actors["patient"]
    _consent_and_obs(client, actors)
    current = actors["current"]
    current["user"] = actors["clinician"]
    client.post(
        f"/api/v1/tenants/{tenant_id}/summaries",
        json={"patient_id": patient.id},
    )
    client.post(
        f"/api/v1/tenants/{tenant_id}/notes",
        json={"patient_id": patient.id},
    )
    assert (
        session.scalars(
            select(FhirResource).where(
                FhirResource.resource_type.in_(("Composition", "Task"))
            )
        ).all()
        == []
    )
