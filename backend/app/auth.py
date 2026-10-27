from __future__ import annotations

from typing import Any

import jwt
from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import InvalidTokenError, PyJWKClient
from jwt.exceptions import PyJWKClientError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_session
from app.models import AuditEvent, User

_bearer = HTTPBearer(auto_error=False)
_jwks_client: PyJWKClient | None = None


class ApiError(Exception):
    def __init__(self, code: str, message: str, status_code: int) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


def decode_access_token(token: str) -> dict[str, Any]:
    global _jwks_client
    if not settings.oidc_configured:
        raise ApiError(
            "OIDC_NOT_CONFIGURED",
            "Enterprise sign-in is not configured for this environment.",
            503,
        )
    if not settings.oidc_issuer.startswith("https://"):
        raise ApiError("OIDC_CONFIGURATION_INVALID", "OIDC issuer must use HTTPS.", 503)
    if not settings.oidc_jwks_url.startswith("https://"):
        raise ApiError("OIDC_CONFIGURATION_INVALID", "OIDC signing keys must use HTTPS.", 503)

    try:
        if _jwks_client is None:
            _jwks_client = PyJWKClient(settings.oidc_jwks_url, cache_keys=True)
        signing_key = _jwks_client.get_signing_key_from_jwt(token)
        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256", "ES256"],
            audience=settings.oidc_audience,
            issuer=settings.oidc_issuer,
            options={"require": ["exp", "iat", "iss", "sub", "aud"]},
        )
    except InvalidTokenError as error:
        raise ApiError("AUTH_INVALID_TOKEN", "The access token is invalid or expired.", 401) from error
    except (PyJWKClientError, OSError) as error:
        raise ApiError("AUTH_KEY_LOOKUP_FAILED", "The identity provider could not be verified.", 503) from error

    if not isinstance(claims.get("sub"), str) or not claims["sub"]:
        raise ApiError("AUTH_INVALID_TOKEN", "The access token has no subject.", 401)
    return claims


def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    session: Session = Depends(get_session),
) -> User:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise ApiError("AUTH_REQUIRED", "Sign in to continue.", 401)
    claims = decode_access_token(credentials.credentials)
    issuer = str(claims["iss"])
    subject = str(claims["sub"])
    user = session.execute(
        select(User).where(User.issuer == issuer, User.subject == subject)
    ).scalar_one_or_none()
    if user is None:
        try:
            with session.begin_nested():
                user = User(issuer=issuer, subject=subject)
                session.add(user)
                session.flush()
                session.add(
                    AuditEvent(
                        actor_user_id=None,
                        action="identity.user_provisioned",
                        subject_type="user",
                        subject_id=user.id,
                        request_id=getattr(request.state, "request_id", ""),
                    )
                )
        except IntegrityError:
            user = session.execute(
                select(User).where(User.issuer == issuer, User.subject == subject)
            ).scalar_one_or_none()
            if user is None:
                raise
    return user
