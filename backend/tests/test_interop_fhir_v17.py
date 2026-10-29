"""V1.7 FHIR R4 surface, integration hub, HL7 ORU sandbox, export/import."""

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
from app.models import ClinicPatient, Tenant, TenantMembership, User


ORU_MSG = (
    "MSH|^~\\&|LAB|SANDBOX|||20260110120000||ORU^R01|MSG001|P|2.5\r"
    "PID|1||EXT-PAT-99^^^SANDBOX||Demo^Patient||19900115\r"
    "OBR|1|ORD-1||4548-4^HbA1c\r"
    "OBX|1|NM|4548-4^HbA1c||5.6|%|4.0-5.6|N|||F|||20260110120000\r"
)

ORU_MSG_2 = (
    "MSH|^~\\&|LAB|SANDBOX|||20260111120000||ORU^R01|MSG002|P|2.5\r"
    "PID|1||EXT-PAT-99^^^SANDBOX||Demo^Patient||19900115\r"
    "OBR|1|ORD-2||4548-4^HbA1c\r"
    "OBX|1|NM|4548-4^HbA1c||5.7|%|4.0-5.6|H|||F|||20260111120000\r"
)


@pytest.fixture
def v17_client() -> Generator[tuple[TestClient, Session, dict], None, None]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    session = session_factory()

    patient = User(issuer="https://identity.example", subject="p-v17")
    admin = User(issuer="https://identity.example", subject="a-v17")
    staff = User(issuer="https://identity.example", subject="s-v17")
    other_admin = User(issuer="https://identity.example", subject="a-other-v17")
    session.add_all([patient, admin, staff, other_admin])
    session.flush()
    tenant = Tenant(slug="v17-clinic", display_name="V17 Clinic")
    other = Tenant(slug="v17-other", display_name="Other Clinic")
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
                tenant_id=tenant.id, user_id=staff.id, role="staff", status="active"
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
        "staff": staff,
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


def _grant_consent(client: TestClient, actors: dict) -> None:
    actors["current"]["user"] = actors["patient"]
    grant = client.post(
        f"/api/v1/tenants/{actors['tenant_id']}/patients/me/consents",
        json={"purpose": "treatment", "scope": "chart.read", "policy_version": "v1"},
    )
    assert grant.status_code == 201, grant.text
    actors["current"]["user"] = actors["admin"]


def test_capability_statement_truthful(v17_client) -> None:
    client, _session, _actors = v17_client
    meta = client.get("/api/v1/fhir/r4/metadata")
    assert meta.status_code == 200, meta.text
    body = meta.json()
    assert body["resourceType"] == "CapabilityStatement"
    assert body["fhirVersion"] == "4.0.1"
    types = {r["type"]: r for r in body["rest"][0]["resource"]}
    assert "Patient" in types
    assert "Observation" in types
    assert "Organization" in types
    patient_interactions = {i["code"] for i in types["Patient"]["interaction"]}
    assert "read" in patient_interactions
    assert "search-type" in patient_interactions
    assert "create" not in patient_interactions
    org_interactions = {i["code"] for i in types["Organization"]["interaction"]}
    assert "search-type" not in org_interactions


def test_organization_read_and_unsupported_search(v17_client) -> None:
    client, _session, actors = v17_client
    tenant_id = actors["tenant_id"]
    org = client.get(f"/api/v1/fhir/r4/tenants/{tenant_id}/Organization/{tenant_id}")
    assert org.status_code == 200, org.text
    assert org.json()["resourceType"] == "Organization"
    assert org.json()["name"] == "V17 Clinic"

    bad = client.get(
        f"/api/v1/fhir/r4/tenants/{tenant_id}/Observation",
        params={"patient": actors["patient"].id, "code": "4548-4"},
    )
    assert bad.status_code == 400
    assert bad.json()["error"]["code"] == "FHIR_SEARCH_PARAM_UNSUPPORTED"

    unsupported = client.get(f"/api/v1/fhir/r4/tenants/{tenant_id}/MedicationRequest")
    assert unsupported.status_code == 400
    assert unsupported.json()["error"]["code"] == "FHIR_SEARCH_UNSUPPORTED"


def test_cross_tenant_fhir_denied(v17_client) -> None:
    client, _session, actors = v17_client
    actors["current"]["user"] = actors["other_admin"]
    denied = client.get(
        f"/api/v1/fhir/r4/tenants/{actors['tenant_id']}/Organization/{actors['tenant_id']}"
    )
    assert denied.status_code == 404


def test_connection_test_hides_secrets(v17_client) -> None:
    client, _session, actors = v17_client
    tenant_id = actors["tenant_id"]
    created = client.post(
        f"/api/v1/tenants/{tenant_id}/integrations/connections",
        json={
            "connection_name": "Sandbox EHR",
            "integration_type": "fhir_ehr",
            "external_system": "FakeEHR",
            "base_url": "https://sandbox.example/fhir",
            "authorized_scopes": ["system/Patient.read"],
        },
    )
    assert created.status_code == 201, created.text
    assert "secret" not in created.text.lower() or "secret_reference" not in created.json()
    conn_id = created.json()["connection_id"]
    tested = client.post(f"/api/v1/tenants/{tenant_id}/integrations/connections/{conn_id}/test")
    assert tested.status_code == 200, tested.text
    assert tested.json()["token_reference_present"] is True
    assert "access_token" not in tested.json()
    assert "secret://" not in tested.text


def test_hl7_oru_identity_gate_and_idempotent_import(v17_client) -> None:
    client, _session, actors = v17_client
    tenant_id = actors["tenant_id"]
    patient_id = actors["patient"].id
    _grant_consent(client, actors)

    lab = client.post(
        f"/api/v1/tenants/{tenant_id}/integrations/connections",
        json={
            "connection_name": "Sandbox Lab",
            "integration_type": "hl7_lab",
            "external_system": "FakeLab",
        },
    )
    assert lab.status_code == 201, lab.text
    conn_id = lab.json()["connection_id"]

    pending = client.post(
        f"/api/v1/tenants/{tenant_id}/integrations/hl7/oru",
        json={"connection_id": conn_id, "message": ORU_MSG, "local_patient_id": patient_id},
    )
    assert pending.status_code == 201, pending.text
    assert pending.json()["status"] == "awaiting_review"
    link_id = pending.json()["identity_link_id"]

    resolve = client.post(
        f"/api/v1/tenants/{tenant_id}/integrations/patient-matches/{link_id}/resolve",
        json={"patient_id": patient_id, "verification_status": "confirmed"},
    )
    assert resolve.status_code == 200, resolve.text
    assert resolve.json()["verification_status"] == "confirmed"

    # Same message id — idempotent, no duplicate observation
    dup = client.post(
        f"/api/v1/tenants/{tenant_id}/integrations/hl7/oru",
        json={"connection_id": conn_id, "message": ORU_MSG},
    )
    assert dup.status_code == 201
    assert dup.json()["duplicate"] is True

    imported = client.post(
        f"/api/v1/tenants/{tenant_id}/integrations/hl7/oru",
        json={"connection_id": conn_id, "message": ORU_MSG_2},
    )
    assert imported.status_code == 201, imported.text
    assert imported.json()["status"] == "processed"
    assert imported.json()["verification"] == "imported_unverified"
    obs_id = imported.json()["observation_id"]

    obs = client.get(f"/api/v1/fhir/r4/tenants/{tenant_id}/Observation/{obs_id}")
    assert obs.status_code == 200, obs.text
    extensions = obs.json().get("extension") or []
    assert any(e.get("valueString") == "imported_unverified" for e in extensions)

    monitoring = client.get(f"/api/v1/tenants/{tenant_id}/integrations/monitoring")
    assert monitoring.status_code == 200
    assert monitoring.json()["processed"] >= 1
    assert monitoring.json()["connections"] >= 1


def test_terminology_governance_and_ehr_import_export(v17_client) -> None:
    client, _session, actors = v17_client
    tenant_id = actors["tenant_id"]
    patient_id = actors["patient"].id
    _grant_consent(client, actors)

    mapping = client.post(
        f"/api/v1/tenants/{tenant_id}/integrations/terminology/mappings",
        json={
            "source_system": "FakeLab",
            "source_code": "4548-4",
            "source_display": "HbA1c",
            "target_system": "http://loinc.org",
            "target_code": "4548-4",
        },
    )
    assert mapping.status_code == 201
    assert mapping.json()["status"] == "pending_review"
    approved = client.post(
        f"/api/v1/tenants/{tenant_id}/integrations/terminology/mappings/"
        f"{mapping.json()['mapping_id']}/approve"
    )
    assert approved.status_code == 200
    assert approved.json()["status"] == "approved"

    ehr = client.post(
        f"/api/v1/tenants/{tenant_id}/integrations/connections",
        json={
            "connection_name": "Fake EHR",
            "integration_type": "fhir_ehr",
            "external_system": "FakeEHR",
            "base_url": "https://sandbox.example/fhir",
        },
    )
    assert ehr.status_code == 201
    preview = client.post(
        f"/api/v1/tenants/{tenant_id}/integrations/imports",
        json={
            "connection_id": ehr.json()["connection_id"],
            "patient_family": "Demo",
            "local_patient_id": patient_id,
        },
    )
    assert preview.status_code == 201, preview.text
    assert preview.json()["status"] == "preview"
    batch_id = preview.json()["batch_id"]

    detail = client.get(f"/api/v1/tenants/{tenant_id}/integrations/imports/{batch_id}")
    assert detail.status_code == 200
    assert len(detail.json()["items"]) >= 1

    approve = client.post(f"/api/v1/tenants/{tenant_id}/integrations/imports/{batch_id}/approve")
    assert approve.status_code == 200, approve.text
    assert approve.json()["imported_count"] >= 1

    # Re-approve is idempotent
    again = client.post(f"/api/v1/tenants/{tenant_id}/integrations/imports/{batch_id}/approve")
    assert again.status_code == 200
    assert again.json().get("duplicate") is True

    actors["current"]["user"] = actors["patient"]
    client.post(f"/api/v1/fhir/R4/tenants/{tenant_id}/Patient/$ensure")
    export = client.post(f"/api/v1/tenants/{tenant_id}/patients/{patient_id}/export")
    assert export.status_code == 201, export.text
    assert export.json()["format"] == "fhir_r4_bundle"
    assert "Bulk Data" not in export.json()["note"] or "Not FHIR Bulk" in export.json()["note"]

    download = client.get(
        f"/api/v1/tenants/{tenant_id}/patients/{patient_id}/exports/{export.json()['export_id']}"
    )
    assert download.status_code == 200
    assert download.json()["resourceType"] == "Bundle"
    assert download.json()["type"] == "collection"


def test_patient_cannot_manage_connections(v17_client) -> None:
    client, _session, actors = v17_client
    actors["current"]["user"] = actors["patient"]
    denied = client.post(
        f"/api/v1/tenants/{actors['tenant_id']}/integrations/connections",
        json={
            "connection_name": "Nope",
            "integration_type": "fhir_ehr",
            "external_system": "X",
        },
    )
    assert denied.status_code == 403
