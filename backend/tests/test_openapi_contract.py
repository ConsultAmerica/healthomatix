from app.main import app


def test_openapi_includes_mounted_health_and_platform_contracts() -> None:
    paths = app.openapi()["paths"]

    assert "/api/v1/health" in paths
    assert "/api/v1/health/live" in paths
    assert "/api/v1/health/ready" in paths
    assert "/api/v1/me" in paths
    assert "/api/v1/platform/tenants" in paths
    assert "/api/v1/platform/support-access-requests" in paths
    assert "/api/v1/tenants/{tenant_id}/appointments" in paths
    assert "/api/v1/tenants/{tenant_id}/patients/{clinic_patient_id}" in paths
    assert "/api/v1/tenants/{tenant_id}/documents" in paths
    assert "/api/v1/tenants/{tenant_id}/documents/{document_id}/content" in paths
    assert "/api/v1/tenants/{tenant_id}/patients/{clinic_patient_id}/documents" in paths
    assert "/api/v1/tenants/{tenant_id}/threads" in paths
    assert "/api/v1/tenants/{tenant_id}/threads/{thread_id}/messages" in paths


def test_openapi_does_not_advertise_unimplemented_platform_grants() -> None:
    paths = app.openapi()["paths"]

    assert "/api/v1/platform/support-access-grants" not in paths
