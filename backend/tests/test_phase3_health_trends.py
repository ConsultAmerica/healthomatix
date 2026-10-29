from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import get_current_user
from app.db import Base, get_session
from app.main import app
from app.models import AuditEvent, ClinicPatient, Tenant, TenantMembership, User


@pytest.fixture
def trends_client() -> Generator[tuple[TestClient, Session, dict], None, None]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    session = session_factory()

    patient = User(issuer="https://identity.example", subject="p-trend")
    clinician = User(issuer="https://identity.example", subject="c-trend")
    session.add_all([patient, clinician])
    session.flush()
    tenant = Tenant(slug="trend-clinic", display_name="Trend Clinic")
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


def _seed_glucose_series(client: TestClient, actors: dict) -> None:
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
    samples = [
        ("2025-06-01T10:00:00Z", 95, "70-99"),
        ("2025-09-01T10:00:00Z", 110, "70-99"),
        ("2026-01-15T10:00:00Z", 128, "70-99"),
    ]
    for effective, value, ref in samples:
        created = client.post(
            f"/api/v1/fhir/R4/tenants/{tenant_id}/Observation",
            json={
                "resourceType": "Observation",
                "status": "final",
                "code": {"text": "Glucose"},
                "subject": {"reference": f"Patient/{patient.id}"},
                "effectiveDateTime": effective,
                "valueQuantity": {"value": value, "unit": "mg/dL"},
                "referenceRange": [{"text": ref}],
                "derivedFrom": [{"reference": "DocumentReference/doc-seed-1"}],
            },
        )
        assert created.status_code == 201, created.text


def test_trends_series_consent_and_source_links(trends_client: tuple) -> None:
    client, session, actors = trends_client
    tenant_id = actors["tenant_id"]
    patient: User = actors["patient"]
    _seed_glucose_series(client, actors)

    current = actors["current"]
    current["user"] = actors["clinician"]
    series = client.get(
        f"/api/v1/tenants/{tenant_id}/trends",
        params={"code": "glucose", "patient_id": patient.id},
    )
    assert series.status_code == 200, series.text
    body = series.json()
    assert body["test_code"] == "glucose"
    assert body["test_label"] == "Blood glucose"
    assert len(body["points"]) == 3
    assert body["points"][0]["value"] == 95
    assert body["points"][-1]["value"] == 128
    assert body["reference_low"] == 70
    assert body["reference_high"] == 99
    assert all(p.get("document_reference_id") == "doc-seed-1" for p in body["points"])
    assert session.scalar(select(AuditEvent).where(AuditEvent.action == "trends.read"))


def test_insights_flag_significant_change(trends_client: tuple) -> None:
    client, _session, actors = trends_client
    tenant_id = actors["tenant_id"]
    patient: User = actors["patient"]
    _seed_glucose_series(client, actors)

    current = actors["current"]
    current["user"] = actors["clinician"]
    insights = client.get(
        f"/api/v1/tenants/{tenant_id}/insights",
        params={"code": "glucose", "patient_id": patient.id},
    )
    assert insights.status_code == 200, insights.text
    body = insights.json()
    assert body["disclaimer"]
    assert "not a diagnosis" in body["disclaimer"].lower()
    assert body["flags"]
    assert all(
        f["framing"] == "educational_support_for_clinician_discussion" for f in body["flags"]
    )
    assert any("reference range" in f["title"].lower() or "%" in f["title"] for f in body["flags"])


def test_clinician_trends_denied_without_consent(trends_client: tuple) -> None:
    client, _session, actors = trends_client
    tenant_id = actors["tenant_id"]
    patient: User = actors["patient"]
    current = actors["current"]
    current["user"] = patient
    client.post(f"/api/v1/fhir/R4/tenants/{tenant_id}/Patient/$ensure")

    current["user"] = actors["clinician"]
    denied = client.get(
        f"/api/v1/tenants/{tenant_id}/trends",
        params={"code": "glucose", "patient_id": patient.id},
    )
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "CONSENT_DENIED"


def test_patient_can_read_own_trends(trends_client: tuple) -> None:
    client, _session, actors = trends_client
    tenant_id = actors["tenant_id"]
    _seed_glucose_series(client, actors)
    current = actors["current"]
    current["user"] = actors["patient"]
    series = client.get(
        f"/api/v1/tenants/{tenant_id}/trends",
        params={"code": "glucose"},
    )
    assert series.status_code == 200, series.text
    assert len(series.json()["points"]) == 3


def test_unknown_test_rejected(trends_client: tuple) -> None:
    client, _session, actors = trends_client
    tenant_id = actors["tenant_id"]
    current = actors["current"]
    current["user"] = actors["patient"]
    response = client.get(
        f"/api/v1/tenants/{tenant_id}/trends",
        params={"code": "vibes"},
    )
    assert response.status_code == 422


def test_patient_trend_tests_annotated_with_counts(trends_client: tuple) -> None:
    client, _session, actors = trends_client
    tenant_id = actors["tenant_id"]
    _seed_glucose_series(client, actors)
    current = actors["current"]
    current["user"] = actors["patient"]
    tests = client.get(f"/api/v1/tenants/{tenant_id}/trend-tests")
    assert tests.status_code == 200, tests.text
    rows = tests.json()
    glucose = next(t for t in rows if t["code"] == "glucose")
    assert glucose["has_data"] is True
    assert glucose["point_count"] == 3
    assert glucose["latest_value"] == 128
    assert rows[0]["has_data"] is True


def test_hba1c_does_not_match_hemoglobin(trends_client: tuple) -> None:
    client, _session, actors = trends_client
    tenant_id = actors["tenant_id"]
    patient: User = actors["patient"]
    current = actors["current"]
    current["user"] = patient
    client.post(f"/api/v1/fhir/R4/tenants/{tenant_id}/Patient/$ensure")
    client.post(
        f"/api/v1/tenants/{tenant_id}/patients/me/consents",
        json={"purpose": "treatment", "scope": "chart.read", "policy_version": "v1"},
    )
    current["user"] = actors["clinician"]
    assert (
        client.post(
            f"/api/v1/fhir/R4/tenants/{tenant_id}/Observation",
            json={
                "resourceType": "Observation",
                "status": "final",
                "code": {"text": "HbA1c"},
                "subject": {"reference": f"Patient/{patient.id}"},
                "effectiveDateTime": "2026-01-01T00:00:00Z",
                "valueQuantity": {"value": 6.2, "unit": "%"},
                "referenceRange": [{"text": "4.0-5.6"}],
            },
        ).status_code
        == 201
    )
    hba1c = client.get(
        f"/api/v1/tenants/{tenant_id}/trends",
        params={"code": "hba1c", "patient_id": patient.id},
    )
    hemoglobin = client.get(
        f"/api/v1/tenants/{tenant_id}/trends",
        params={"code": "hemoglobin", "patient_id": patient.id},
    )
    assert hba1c.status_code == 200
    assert len(hba1c.json()["points"]) == 1
    assert hemoglobin.status_code == 200
    assert hemoglobin.json()["points"] == []


def test_date_filter_and_in_range_summary(trends_client: tuple) -> None:
    client, _session, actors = trends_client
    tenant_id = actors["tenant_id"]
    patient: User = actors["patient"]
    _seed_glucose_series(client, actors)
    current = actors["current"]
    current["user"] = actors["clinician"]
    filtered = client.get(
        f"/api/v1/tenants/{tenant_id}/trends",
        params={
            "code": "glucose",
            "patient_id": patient.id,
            "date_from": "2025-09-01T00:00:00Z",
        },
    )
    assert filtered.status_code == 200, filtered.text
    body = filtered.json()
    assert len(body["points"]) == 2
    assert body["point_count"] == 2
    assert body["latest_value"] == 128
    assert body["delta"] == 18
    assert body["points"][-1]["in_range"] is False
    assert body["points"][0]["in_range"] is False


def test_rising_streak_insight(trends_client: tuple) -> None:
    client, _session, actors = trends_client
    tenant_id = actors["tenant_id"]
    patient: User = actors["patient"]
    current = actors["current"]
    current["user"] = patient
    client.post(f"/api/v1/fhir/R4/tenants/{tenant_id}/Patient/$ensure")
    client.post(
        f"/api/v1/tenants/{tenant_id}/patients/me/consents",
        json={"purpose": "treatment", "scope": "chart.read", "policy_version": "v1"},
    )
    current["user"] = actors["clinician"]
    for effective, value in [
        ("2025-01-01T00:00:00Z", 80),
        ("2025-04-01T00:00:00Z", 88),
        ("2025-07-01T00:00:00Z", 96),
    ]:
        assert (
            client.post(
                f"/api/v1/fhir/R4/tenants/{tenant_id}/Observation",
                json={
                    "resourceType": "Observation",
                    "status": "final",
                    "code": {"text": "Glucose"},
                    "subject": {"reference": f"Patient/{patient.id}"},
                    "effectiveDateTime": effective,
                    "valueQuantity": {"value": value, "unit": "mg/dL"},
                    "referenceRange": [{"text": "70-99"}],
                },
            ).status_code
            == 201
        )
    insights = client.get(
        f"/api/v1/tenants/{tenant_id}/insights",
        params={"code": "glucose", "patient_id": patient.id},
    )
    assert insights.status_code == 200
    codes = {f["code"] for f in insights.json()["flags"]}
    assert "glucose.rising_streak" in codes
