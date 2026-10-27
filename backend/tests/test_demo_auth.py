from __future__ import annotations

from collections.abc import Generator
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app import auth, routes
from app.config import _demo_auth_secret, settings
from app.db import Base, get_session
from app.main import app
from app.models import User

SECRET = "synthetic-demo-secret-0123456789abcdef"


@pytest.fixture
def demo_client(
    monkeypatch: pytest.MonkeyPatch,
) -> Generator[tuple[TestClient, Session], None, None]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    demo_settings = replace(settings, demo_auth_secret=SECRET)
    monkeypatch.setattr(auth, "settings", demo_settings)
    monkeypatch.setattr(routes, "settings", demo_settings)

    def override_session() -> Generator[Session, None, None]:
        yield session

    app.dependency_overrides[get_session] = override_session
    try:
        with TestClient(app) as client:
            yield client, session
    finally:
        app.dependency_overrides.clear()
        session.close()
        Base.metadata.drop_all(engine)
        engine.dispose()


def test_demo_identity_with_shared_secret_is_provisioned(
    demo_client: tuple[TestClient, Session],
) -> None:
    client, session = demo_client

    response = client.get(
        "/api/v1/me", headers={"X-Demo-User": "demo-provider", "X-Demo-Secret": SECRET}
    )

    assert response.status_code == 200, response.text
    user = session.scalar(select(User).where(User.subject == "demo-provider"))
    assert user is not None
    assert user.issuer == auth.DEMO_ISSUER
    assert client.get("/api/v1/auth/config").json()["demo_auth_enabled"] is True


@pytest.mark.parametrize(
    "headers",
    (
        {"X-Demo-User": "demo-provider", "X-Demo-Secret": "wrong-secret"},
        {"X-Demo-User": "demo-provider"},
        {"X-Demo-User": "someone-else", "X-Demo-Secret": SECRET},
        {"X-Demo-User": "demo-UPPER", "X-Demo-Secret": SECRET},
    ),
)
def test_demo_identity_rejects_bad_secret_or_subject(
    demo_client: tuple[TestClient, Session], headers: dict[str, str]
) -> None:
    client, _ = demo_client
    response = client.get("/api/v1/me", headers=headers)
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTH_INVALID_TOKEN"


def test_demo_headers_are_ignored_when_demo_mode_is_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(auth, "settings", replace(settings, demo_auth_secret=""))
    with TestClient(app) as client:
        response = client.get(
            "/api/v1/me", headers={"X-Demo-User": "demo-provider", "X-Demo-Secret": SECRET}
        )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTH_REQUIRED"


def test_demo_secret_is_refused_in_production(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEMO_AUTH_SECRET", SECRET)
    with pytest.raises(ValueError):
        _demo_auth_secret("production")
    assert _demo_auth_secret("development") == SECRET


def test_short_demo_secret_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEMO_AUTH_SECRET", "too-short")
    with pytest.raises(ValueError):
        _demo_auth_secret("development")
