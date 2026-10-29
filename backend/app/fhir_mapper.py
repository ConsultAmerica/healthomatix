"""Map Healthomatix domain records to FHIR R4 JSON (read projections)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.fhir_store import get_resource
from app.models import ClinicLocation, ProviderProfile, Tenant


def _meta() -> dict[str, Any]:
    now = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    return {"versionId": "1", "lastUpdated": now}


def organization_from_tenant(tenant: Tenant) -> dict[str, Any]:
    return {
        "resourceType": "Organization",
        "id": tenant.id,
        "meta": _meta(),
        "active": tenant.status == "active",
        "name": tenant.display_name,
        "identifier": [{"system": "urn:healthomatix:tenant-slug", "value": tenant.slug}],
    }


def location_from_clinic(location: ClinicLocation, *, tenant_id: str) -> dict[str, Any]:
    return {
        "resourceType": "Location",
        "id": location.id,
        "meta": _meta(),
        "status": "active" if location.status == "active" else "inactive",
        "name": location.name,
        "managingOrganization": {"reference": f"Organization/{tenant_id}"},
        "extension": [
            {
                "url": "urn:healthomatix:timezone",
                "valueString": location.timezone,
            }
        ],
    }


def practitioner_from_profile(profile: ProviderProfile) -> dict[str, Any]:
    return {
        "resourceType": "Practitioner",
        "id": profile.user_id,
        "meta": _meta(),
        "active": profile.profile_status == "active",
        "name": [{"text": profile.display_name or "Provider"}],
        "qualification": (
            [{"code": {"text": profile.specialty}}] if profile.specialty else []
        ),
    }


def resolve_organization(session: Session, *, tenant_id: str) -> dict[str, Any] | None:
    stored = get_resource(
        session, tenant_id=tenant_id, resource_type="Organization", resource_id=tenant_id
    )
    if stored:
        return stored
    tenant = session.get(Tenant, tenant_id)
    return organization_from_tenant(tenant) if tenant else None


def resolve_location(
    session: Session, *, tenant_id: str, location_id: str
) -> dict[str, Any] | None:
    stored = get_resource(
        session, tenant_id=tenant_id, resource_type="Location", resource_id=location_id
    )
    if stored:
        return stored
    location = session.execute(
        select(ClinicLocation).where(
            ClinicLocation.tenant_id == tenant_id, ClinicLocation.id == location_id
        )
    ).scalar_one_or_none()
    return location_from_clinic(location, tenant_id=tenant_id) if location else None


def resolve_practitioner(
    session: Session, *, tenant_id: str, practitioner_id: str
) -> dict[str, Any] | None:
    stored = get_resource(
        session,
        tenant_id=tenant_id,
        resource_type="Practitioner",
        resource_id=practitioner_id,
    )
    if stored:
        return stored
    profile = session.get(ProviderProfile, practitioner_id)
    return practitioner_from_profile(profile) if profile else None
