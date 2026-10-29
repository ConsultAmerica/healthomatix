from __future__ import annotations

from collections.abc import Generator
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app import demo_seed
from app.auth import DEMO_ISSUER, get_current_user
from app.config import settings
from app.db import Base, get_session
from app.main import app
from app.models import TenantMembership, User

SECRET = "x" * 32


@pytest.fixture
def demo_client(monkeypatch: pytest.MonkeyPatch, tmp_path) -> Generator[tuple[TestClient, Session, dict], None, None]:
    demo_settings = replace(
        settings,
        demo_auth_secret=SECRET,
        document_storage_path=str(tmp_path / "docs"),
        scheduling_enabled=True,
    )
    monkeypatch.setattr(demo_seed, "settings", demo_settings)

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    session = session_factory()

    admin = User(issuer=DEMO_ISSUER, subject="demo-admin")
    session.add(admin)
    session.commit()

    current = {"user": admin}

    def override_session() -> Generator[Session, None, None]:
        yield session

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_current_user] = lambda: current["user"]

    actors = {"admin": admin, "current": current, "session": session}
    try:
        with TestClient(app) as client:
            yield client, session, actors
    finally:
        app.dependency_overrides.clear()
        session.close()
        Base.metadata.drop_all(engine)
        engine.dispose()


def test_seed_links_personas_and_timeline(demo_client: tuple) -> None:
    client, session, actors = demo_client
    first = client.post("/api/v1/demo/seed")
    assert first.status_code == 200, first.text
    body = first.json()
    assert body["slug"] == "demo-sandbox"
    assert body["created"] is True
    tenant_id = body["tenant_id"]
    clinic_patient_id = body["clinic_patient_id"]

    second = client.post("/api/v1/demo/seed")
    assert second.status_code == 200
    assert second.json()["created"] is False
    assert second.json()["tenant_id"] == tenant_id

    memberships = session.execute(
        select(TenantMembership).where(TenantMembership.tenant_id == tenant_id)
    ).scalars().all()
    roles = {m.role for m in memberships}
    assert roles == {"tenant_admin", "provider", "staff", "patient"}

    timeline = client.get(
        f"/api/v1/tenants/{tenant_id}/patients/{clinic_patient_id}/timeline"
    )
    assert timeline.status_code == 200, timeline.text
    events = timeline.json()["events"]
    kinds = {event["kind"] for event in events}
    assert "observation" in kinds
    assert "document" in kinds
    assert any(event["title"] == "Glucose" for event in events)

    patient = session.execute(
        select(User).where(User.issuer == DEMO_ISSUER, User.subject == "demo-patient")
    ).scalar_one()
    actors["current"]["user"] = patient
    mine = client.get(f"/api/v1/tenants/{tenant_id}/patients/me/timeline")
    assert mine.status_code == 200, mine.text
    assert len(mine.json()["events"]) >= 3


def test_seed_requires_demo_secret(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    demo_settings = replace(settings, demo_auth_secret="", document_storage_path=str(tmp_path))
    monkeypatch.setattr(demo_seed, "settings", demo_settings)

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    session = session_factory()
    user = User(issuer=DEMO_ISSUER, subject="demo-admin")
    session.add(user)
    session.commit()

    def override_session() -> Generator[Session, None, None]:
        yield session

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_current_user] = lambda: user
    try:
        with TestClient(app) as client:
            response = client.post("/api/v1/demo/seed")
            assert response.status_code == 404
    finally:
        app.dependency_overrides.clear()
        session.close()
        Base.metadata.drop_all(engine)
        engine.dispose()
