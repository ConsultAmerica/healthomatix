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
from app.models import (
    ClinicPatient,
    MedicalDocument,
    PatientProfile,
    Tenant,
    TenantMembership,
    User,
)


@pytest.fixture
def patient_client() -> Generator[tuple[TestClient, Session, User, Tenant, Tenant], None, None]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    session = session_factory()

    user = User(issuer="https://identity.example", subject="patient-1")
    clinic_a = Tenant(slug="clinic-a", display_name="Clinic A")
    clinic_b = Tenant(slug="clinic-b", display_name="Clinic B")
    session.add_all((user, clinic_a, clinic_b))
    session.flush()
    session.add_all(
        (
            TenantMembership(tenant_id=clinic_a.id, user_id=user.id, role="patient"),
            TenantMembership(tenant_id=clinic_b.id, user_id=user.id, role="patient"),
            ClinicPatient(
                tenant_id=clinic_a.id,
                patient_user_id=user.id,
                chart_number="A-100",
            ),
            PatientProfile(
                user_id=user.id,
                preferred_name="Synthetic Patient",
                legal_name="Synthetic Patient",
                phone="",
                preferred_language="en",
            ),
        )
    )
    session.commit()

    def override_session() -> Generator[Session, None, None]:
        yield session

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_current_user] = lambda: user
    try:
        with TestClient(app) as client:
            yield client, session, user, clinic_a, clinic_b
    finally:
        app.dependency_overrides.clear()
        session.close()
        Base.metadata.drop_all(engine)
        engine.dispose()


def test_patient_can_read_profile_in_linked_clinic(
    patient_client: tuple[TestClient, Session, User, Tenant, Tenant],
) -> None:
    client, _, _, clinic_a, _ = patient_client

    response = client.get(f"/api/v1/tenants/{clinic_a.id}/patients/me")

    assert response.status_code == 200
    assert response.json()["preferred_name"] == "Synthetic Patient"


def test_patient_membership_without_clinic_link_cannot_read_profile(
    patient_client: tuple[TestClient, Session, User, Tenant, Tenant],
) -> None:
    client, _, _, _, clinic_b = patient_client

    response = client.get(f"/api/v1/tenants/{clinic_b.id}/patients/me")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "PATIENT_NOT_FOUND"


def test_profile_update_audits_clinic_patient_not_global_identity(
    patient_client: tuple[TestClient, Session, User, Tenant, Tenant],
) -> None:
    client, session, _, clinic_a, _ = patient_client

    response = client.put(
        f"/api/v1/tenants/{clinic_a.id}/patients/me",
        json={"preferred_name": "Synthetic Updated"},
    )

    assert response.status_code == 200
    assert response.json()["preferred_name"] == "Synthetic Updated"
    events = session.query(Base.metadata.tables["audit_events"]).all()
    assert len(events) == 1
    assert events[0].subject_type == "clinic_patient"


def test_document_metadata_is_owner_and_tenant_scoped(
    patient_client: tuple[TestClient, Session, User, Tenant, Tenant],
) -> None:
    client, session, user, clinic_a, clinic_b = patient_client
    session.add_all(
        (
            MedicalDocument(
                tenant_id=clinic_a.id,
                patient_user_id=user.id,
                uploaded_by_user_id=user.id,
                storage_key="synthetic-clinic-a-document",
                original_filename="synthetic-record-a.pdf",
                content_type="application/pdf",
                size_bytes=32,
                sha256="a" * 64,
                lifecycle_state="stored",
            ),
            MedicalDocument(
                tenant_id=clinic_b.id,
                patient_user_id=user.id,
                uploaded_by_user_id=user.id,
                storage_key="synthetic-clinic-b-document",
                original_filename="synthetic-record-b.pdf",
                content_type="application/pdf",
                size_bytes=32,
                sha256="b" * 64,
                lifecycle_state="stored",
            ),
        )
    )
    session.commit()

    visible = client.get(f"/api/v1/tenants/{clinic_a.id}/documents")
    unlinked_clinic = client.get(f"/api/v1/tenants/{clinic_b.id}/documents")

    assert visible.status_code == 200
    assert len(visible.json()) == 1
    assert visible.json()[0]["original_filename"] == "synthetic-record-a.pdf"
    assert "storage_key" not in visible.text
    assert "sha256" not in visible.text
    assert unlinked_clinic.status_code == 404
    assert unlinked_clinic.json()["error"]["code"] == "PATIENT_NOT_FOUND"
