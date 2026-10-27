from __future__ import annotations

from types import SimpleNamespace

import pytest

from app import auth
from app.config import _platform_admin_identities
from app.auth import ApiError


def test_oidc_missing_configuration_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        auth,
        "settings",
        SimpleNamespace(oidc_configured=False),
    )

    with pytest.raises(ApiError) as error:
        auth.decode_access_token("synthetic-token")

    assert error.value.status_code == 503
    assert error.value.code == "OIDC_NOT_CONFIGURED"


@pytest.mark.parametrize(
    ("issuer", "jwks_url"),
    (
        ("http://identity.example", "https://identity.example/keys"),
        ("https://identity.example", "http://identity.example/keys"),
    ),
)
def test_oidc_rejects_non_https_provider_endpoints(
    monkeypatch: pytest.MonkeyPatch,
    issuer: str,
    jwks_url: str,
) -> None:
    monkeypatch.setattr(
        auth,
        "settings",
        SimpleNamespace(
            oidc_configured=True,
            oidc_issuer=issuer,
            oidc_jwks_url=jwks_url,
        ),
    )

    with pytest.raises(ApiError) as error:
        auth.decode_access_token("synthetic-token")

    assert error.value.status_code == 503
    assert error.value.code == "OIDC_CONFIGURATION_INVALID"


def test_platform_admin_identities_require_exact_https_pairs() -> None:
    assert _platform_admin_identities(
        "https://identity.example|admin-one;https://identity.example/|admin-two"
    ) == (
        ("https://identity.example", "admin-one"),
        ("https://identity.example", "admin-two"),
    )

    with pytest.raises(ValueError, match="HTTPS issuer\\|subject"):
        _platform_admin_identities("http://identity.example|admin")

    with pytest.raises(ValueError, match="HTTPS issuer\\|subject"):
        _platform_admin_identities("https://identity.example")
