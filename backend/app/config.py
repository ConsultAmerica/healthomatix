from __future__ import annotations

import os
from dataclasses import dataclass


def _csv(value: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in value.split(",") if item.strip())


def _platform_admin_identities(value: str) -> tuple[tuple[str, str], ...]:
    identities: list[tuple[str, str]] = []
    for entry in value.split(";"):
        if not entry.strip():
            continue
        issuer, separator, subject = entry.partition("|")
        issuer = issuer.strip().rstrip("/")
        subject = subject.strip()
        if not separator or not issuer.startswith("https://") or not subject:
            raise ValueError(
                "PLATFORM_ADMIN_IDENTITIES entries must be HTTPS issuer|subject pairs."
            )
        identities.append((issuer, subject))
    return tuple(dict.fromkeys(identities))


def _database_url() -> str:
    # Vercel's Neon integration provides DATABASE_URL (and POSTGRES_URL) with the
    # generic postgres scheme; use the installed psycopg 3 driver explicitly.
    value = (os.getenv("DATABASE_URL") or os.getenv("POSTGRES_URL") or "").strip()
    if not value:
        return "sqlite:///./healthomatix-dev.db"
    for prefix in ("postgres://", "postgresql://"):
        if value.startswith(prefix):
            return "postgresql+psycopg://" + value[len(prefix) :]
    return value


def _demo_auth_secret(environment: str) -> str:
    # Demo sign-in is for synthetic testing only and must never reach production.
    secret = os.getenv("DEMO_AUTH_SECRET", "").strip()
    if not secret:
        return ""
    if environment == "production":
        raise ValueError("DEMO_AUTH_SECRET must not be set when HEALTHOMATIX_ENV=production.")
    if len(secret) < 32:
        raise ValueError("DEMO_AUTH_SECRET must be at least 32 characters.")
    return secret


@dataclass(frozen=True)
class Settings:
    database_url: str
    environment: str
    scheduling_enabled: bool
    document_storage_path: str
    oidc_issuer: str
    oidc_audience: str
    oidc_jwks_url: str
    cors_origins: tuple[str, ...]
    platform_admin_identities: tuple[tuple[str, str], ...]
    demo_auth_secret: str = ""

    @property
    def demo_auth_enabled(self) -> bool:
        return bool(self.demo_auth_secret)

    @property
    def oidc_configured(self) -> bool:
        return bool(self.oidc_issuer and self.oidc_audience and self.oidc_jwks_url)

    @property
    def document_storage_configured(self) -> bool:
        return bool(self.document_storage_path)


def load_settings() -> Settings:
    environment = os.getenv("HEALTHOMATIX_ENV", "development").strip().lower()
    scheduling_default = "true" if environment == "development" else "false"
    scheduling_value = os.getenv("SCHEDULING_ENABLED", scheduling_default).strip().lower()
    if scheduling_value not in {"true", "false", "1", "0", "yes", "no"}:
        raise ValueError("SCHEDULING_ENABLED must be a boolean value.")
    document_storage_path = os.getenv("DOCUMENT_STORAGE_PATH", "").strip()
    if not document_storage_path and environment == "development":
        document_storage_path = "./.document-storage"
    return Settings(
        database_url=_database_url(),
        environment=environment,
        scheduling_enabled=scheduling_value in {"true", "1", "yes"},
        document_storage_path=document_storage_path,
        oidc_issuer=os.getenv("OIDC_ISSUER", "").strip().rstrip("/"),
        oidc_audience=os.getenv("OIDC_AUDIENCE", "").strip(),
        oidc_jwks_url=os.getenv("OIDC_JWKS_URL", "").strip(),
        cors_origins=_csv(
            os.getenv(
                "CORS_ORIGINS",
                "http://localhost:3000,http://localhost:8081",
            )
        ),
        platform_admin_identities=_platform_admin_identities(
            os.getenv("PLATFORM_ADMIN_IDENTITIES", "")
        ),
        demo_auth_secret=_demo_auth_secret(environment),
    )


settings = load_settings()
