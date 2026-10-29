from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import get_current_user
from app.db import Base, get_session
from app.document_routes import get_private_storage
from app.fhir_models import Extraction, FhirResource
from app.intelligence_routes import get_private_storage as get_intel_storage
from app.main import app
from app.models import ClinicPatient, Tenant, TenantMembership, User
from app.storage import LocalDirectoryPrivateStorage


@pytest.fixture
def intel_client(
    tmp_path,
) -> Generator[tuple[TestClient, Session, dict], None, None]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    session = session_factory()

    patient = User(issuer="https://identity.example", subject="p-doc")
    clinician = User(issuer="https://identity.example", subject="c-doc")
    session.add_all([patient, clinician])
    session.flush()
    tenant = Tenant(slug="doc-clinic", display_name="Doc Clinic")
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
            ClinicPatient(
                tenant_id=tenant.id, patient_user_id=patient.id, status="active"
            ),
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


def test_upload_extract_verify_promotes_observation(intel_client: tuple) -> None:
    client, session, actors = intel_client
    tenant_id = actors["tenant_id"]
    patient: User = actors["patient"]
    current = actors["current"]

    current["user"] = patient
    lab = (
        b"Lab Report\nGlucose 118 mg/dL (70-99)\nCollected 2026-01-15\n"
    )
    uploaded = client.post(
        f"/api/v1/tenants/{tenant_id}/documents",
        files={"file": ("labs.txt", lab, "text/plain")},
    )
    assert uploaded.status_code == 201, uploaded.text
    document_id = uploaded.json()["document_id"]
    assert uploaded.json().get("document_reference_id")

    grant = client.post(
        f"/api/v1/tenants/{tenant_id}/patients/me/consents",
        json={"purpose": "treatment", "scope": "chart.read", "policy_version": "v1"},
    )
    assert grant.status_code == 201, grant.text

    current["user"] = actors["clinician"]
    extraction = client.post(
        f"/api/v1/tenants/{tenant_id}/documents/{document_id}/extractions",
    )
    assert extraction.status_code == 201, extraction.text
    body = extraction.json()
    assert body["status"] == "draft"
    assert body["fields"]
    extraction_id = body["extraction_id"]

    verified = client.post(
        f"/api/v1/tenants/{tenant_id}/verify",
        json={"extraction_id": extraction_id, "fields": body["fields"]},
    )
    assert verified.status_code == 200, verified.text
    assert verified.json()["extraction"]["status"] == "verified"
    observations = verified.json()["observations"]
    assert observations
    obs_id = observations[0]["id"]

    stored = session.get(Extraction, extraction_id)
    assert stored is not None and stored.status == "verified"

    obs = session.execute(
        select(FhirResource).where(
            FhirResource.id == obs_id,
            FhirResource.resource_type == "Observation",
        )
    ).scalar_one()
    assert obs.patient_id == patient.id

    provenances = session.execute(
        select(FhirResource).where(
            FhirResource.resource_type == "Provenance",
            FhirResource.tenant_id == tenant_id,
        )
    ).scalars().all()
    assert any(
        any(
            (e.get("what") or {}).get("reference", "").startswith("Extraction/")
            for e in (p.resource.get("entity") or [])
        )
        for p in provenances
    )


def test_clinician_download_requires_consent(intel_client: tuple) -> None:
    client, _session, actors = intel_client
    tenant_id = actors["tenant_id"]
    current = actors["current"]
    current["user"] = actors["patient"]
    uploaded = client.post(
        f"/api/v1/tenants/{tenant_id}/documents",
        files={"file": ("labs.txt", b"Glucose 100 mg/dL", "text/plain")},
    )
    document_id = uploaded.json()["document_id"]

    current["user"] = actors["clinician"]
    denied = client.get(f"/api/v1/tenants/{tenant_id}/documents/{document_id}/content")
    assert denied.status_code == 403

    current["user"] = actors["patient"]
    assert (
        client.post(
            f"/api/v1/tenants/{tenant_id}/patients/me/consents",
            json={"purpose": "treatment", "scope": "chart.read", "policy_version": "v1"},
        ).status_code
        == 201
    )

    current["user"] = actors["clinician"]
    allowed = client.get(f"/api/v1/tenants/{tenant_id}/documents/{document_id}/content")
    assert allowed.status_code == 200
    assert b"Glucose" in allowed.content


def test_list_extractions_requires_patient_id_and_consent(intel_client: tuple) -> None:
    client, _session, actors = intel_client
    tenant_id = actors["tenant_id"]
    patient: User = actors["patient"]
    current = actors["current"]

    current["user"] = patient
    uploaded = client.post(
        f"/api/v1/tenants/{tenant_id}/documents",
        files={"file": ("labs.txt", b"Glucose 100 mg/dL", "text/plain")},
    )
    document_id = uploaded.json()["document_id"]
    assert (
        client.post(
            f"/api/v1/tenants/{tenant_id}/patients/me/consents",
            json={"purpose": "treatment", "scope": "chart.read", "policy_version": "v1"},
        ).status_code
        == 201
    )

    current["user"] = actors["clinician"]
    missing = client.get(f"/api/v1/tenants/{tenant_id}/extractions")
    assert missing.status_code == 422

    created = client.post(
        f"/api/v1/tenants/{tenant_id}/documents/{document_id}/extractions",
    )
    assert created.status_code == 201, created.text

    listed = client.get(
        f"/api/v1/tenants/{tenant_id}/extractions",
        params={"patient_id": patient.id},
    )
    assert listed.status_code == 200, listed.text
    assert len(listed.json()) >= 1
    assert listed.json()[0]["patient_id"] == patient.id


def test_multi_analyte_extraction(intel_client: tuple) -> None:
    client, _session, actors = intel_client
    tenant_id = actors["tenant_id"]
    current = actors["current"]
    current["user"] = actors["patient"]
    lab = b"Panel\nGlucose 118 mg/dL (70-99)\nHbA1c 6.2 % (4.0-5.6)\nCollected 2026-01-15\n"
    uploaded = client.post(
        f"/api/v1/tenants/{tenant_id}/documents",
        files={"file": ("panel.txt", lab, "text/plain")},
    )
    document_id = uploaded.json()["document_id"]
    client.post(
        f"/api/v1/tenants/{tenant_id}/patients/me/consents",
        json={"purpose": "treatment", "scope": "chart.read", "policy_version": "v1"},
    )
    current["user"] = actors["clinician"]
    extraction = client.post(
        f"/api/v1/tenants/{tenant_id}/documents/{document_id}/extractions",
    )
    assert extraction.status_code == 201, extraction.text
    names = {f["name"].lower() for f in extraction.json()["fields"]}
    assert "glucose" in names
    assert any("hba1c" in n for n in names)


def test_cross_tenant_extraction_denied(intel_client: tuple) -> None:
    client, session, actors = intel_client
    tenant_id = actors["tenant_id"]
    current = actors["current"]
    current["user"] = actors["patient"]
    uploaded = client.post(
        f"/api/v1/tenants/{tenant_id}/documents",
        files={"file": ("labs.txt", b"Glucose 100 mg/dL", "text/plain")},
    )
    document_id = uploaded.json()["document_id"]

    stranger = User(issuer="https://identity.example", subject="stranger")
    session.add(stranger)
    session.commit()
    current["user"] = stranger
    response = client.post(
        f"/api/v1/tenants/{tenant_id}/documents/{document_id}/extractions",
    )
    assert response.status_code in (403, 404)
