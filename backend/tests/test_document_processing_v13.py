"""V1.3 document processing job pipeline tests."""

from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import get_current_user
from app.db import Base, get_session
from app.document_routes import get_private_storage
from app.intelligence_routes import get_private_storage as get_intel_storage
from app.main import app
from app.models import ClinicPatient, Tenant, TenantMembership, User
from app.storage import LocalDirectoryPrivateStorage


@pytest.fixture
def process_client(tmp_path) -> Generator[tuple[TestClient, Session, dict], None, None]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    session = session_factory()

    patient = User(issuer="https://identity.example", subject="p-v13")
    clinician = User(issuer="https://identity.example", subject="c-v13")
    session.add_all([patient, clinician])
    session.flush()
    tenant = Tenant(slug="v13-clinic", display_name="V13 Clinic")
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

    storage = LocalDirectoryPrivateStorage(tmp_path)
    current = {"user": patient}

    def override_session() -> Generator[Session, None, None]:
        yield session

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_current_user] = lambda: current["user"]
    app.dependency_overrides[get_private_storage] = lambda: storage
    app.dependency_overrides[get_intel_storage] = lambda: storage

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


def test_process_endpoint_classifies_and_extracts_wrapped_glucose(process_client) -> None:
    client, _session, actors = process_client
    tenant_id = actors["tenant_id"]
    current = actors["current"]
    current["user"] = actors["patient"]

    lab = b"Lab Report\nGlucose 112 H 70 -\n99\nCollected 2026-03-01\n"
    uploaded = client.post(
        f"/api/v1/tenants/{tenant_id}/documents",
        files={"file": ("cmp.txt", lab, "text/plain")},
    )
    assert uploaded.status_code == 201, uploaded.text
    document_id = uploaded.json()["document_id"]

    processed = client.post(f"/api/v1/tenants/{tenant_id}/documents/{document_id}/process")
    assert processed.status_code == 202, processed.text
    body = processed.json()
    assert body["status"] == "awaiting_review"
    assert body["classification"]["category"] == "laboratory_report"
    assert body["extraction_id"]

    status = client.get(f"/api/v1/tenants/{tenant_id}/documents/{document_id}/processing-status")
    assert status.status_code == 200
    assert status.json()["job_id"] == body["job_id"]

    current["user"] = actors["clinician"]
    grant = client.post(
        f"/api/v1/tenants/{tenant_id}/patients/me/consents",
        json={"purpose": "treatment", "scope": "chart.read", "policy_version": "v1"},
    )
    # Clinician cannot grant patient consent as patient — grant as patient first
    current["user"] = actors["patient"]
    grant = client.post(
        f"/api/v1/tenants/{tenant_id}/patients/me/consents",
        json={"purpose": "treatment", "scope": "chart.read", "policy_version": "v1"},
    )
    assert grant.status_code == 201, grant.text

    current["user"] = actors["clinician"]
    extraction = client.get(
        f"/api/v1/tenants/{tenant_id}/extractions/{body['extraction_id']}"
    )
    assert extraction.status_code == 200, extraction.text
    fields = extraction.json()["fields"]
    glucose = next(f for f in fields if f["name"].lower() == "glucose")
    assert glucose["value"] == "112"
    assert "70" in (glucose.get("reference_range") or "")
