from app.main import app


def test_openapi_includes_mounted_health_and_platform_contracts() -> None:
    paths = app.openapi()["paths"]

    assert "/api/v1/health" in paths
    assert "/api/v1/me" in paths
    assert "/api/v1/platform/tenants" in paths
    assert "/api/v1/platform/support-access-requests" in paths
    assert "/api/v1/tenants/{tenant_id}/appointments" in paths


def test_openapi_does_not_advertise_unimplemented_document_transfer_routes() -> None:
    paths = app.openapi()["paths"]

    assert "/api/v1/tenants/{tenant_id}/patients/{clinic_patient_id}/documents" not in paths
    assert "/api/v1/platform/support-access-grants" not in paths
