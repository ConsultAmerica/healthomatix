from __future__ import annotations

import pytest

from app.config import _database_url


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (
            "postgresql://user:pw@ep-x-pooler.neon.tech/db?sslmode=require",
            "postgresql+psycopg://user:pw@ep-x-pooler.neon.tech/db?sslmode=require",
        ),
        ("postgres://user:pw@host/db", "postgresql+psycopg://user:pw@host/db"),
        ("postgresql+psycopg://user:pw@host/db", "postgresql+psycopg://user:pw@host/db"),
        ("sqlite:///./local.db", "sqlite:///./local.db"),
    ],
)
def test_database_url_uses_psycopg_driver(
    monkeypatch: pytest.MonkeyPatch, raw: str, expected: str
) -> None:
    monkeypatch.setenv("DATABASE_URL", raw)
    assert _database_url() == expected


def test_database_url_falls_back_to_vercel_postgres_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("POSTGRES_URL", "postgres://user:pw@host/db")
    assert _database_url() == "postgresql+psycopg://user:pw@host/db"


def test_database_url_defaults_to_local_sqlite(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("POSTGRES_URL", raising=False)
    assert _database_url().startswith("sqlite:///")
