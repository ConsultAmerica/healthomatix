"""FHIR R4 resource persistence helpers (facade over fhir_resources)."""

from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.fhir_models import FhirResource
from app.models import new_id, utcnow

CLINICAL_TYPES = frozenset(
    {
        "Patient",
        "Practitioner",
        "Organization",
        "Location",
        "Observation",
        "DiagnosticReport",
        "Condition",
        "MedicationStatement",
        "AllergyIntolerance",
        "Encounter",
        "Appointment",
        "Slot",
        "Composition",
        "Task",
        "Consent",
        "Provenance",
        "AuditEvent",
        "DocumentReference",
    }
)

# Interactions advertised on CapabilityStatement (must stay truthful).
FHIR_R4_READ_TYPES = frozenset(
    {
        "Patient",
        "Practitioner",
        "Organization",
        "Location",
        "Appointment",
        "Encounter",
        "Observation",
        "DiagnosticReport",
        "DocumentReference",
        "Provenance",
    }
)
FHIR_R4_SEARCH_TYPES = frozenset(
    {
        "Patient",
        "Appointment",
        "Encounter",
        "Observation",
        "DocumentReference",
    }
)


def _iso_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def patient_id_from_resource(resource_type: str, body: dict[str, Any]) -> str | None:
    if resource_type == "Patient":
        return body.get("id")
    subject = body.get("subject") or body.get("patient")
    if isinstance(subject, dict):
        ref = subject.get("reference") or ""
        if ref.startswith("Patient/"):
            return ref.split("/", 1)[1]
    for key in ("patient",):
        node = body.get(key)
        if isinstance(node, dict):
            ref = node.get("reference") or ""
            if ref.startswith("Patient/"):
                return ref.split("/", 1)[1]
    for item in body.get("supportingInformation") or []:
        if isinstance(item, dict):
            ref = str(item.get("reference") or "")
            if ref.startswith("Patient/"):
                return ref.split("/", 1)[1]
    for participant in body.get("participant") or []:
        if not isinstance(participant, dict):
            continue
        actor = participant.get("actor") or participant.get("individual") or {}
        if isinstance(actor, dict):
            ref = str(actor.get("reference") or "")
            if ref.startswith("Patient/"):
                return ref.split("/", 1)[1]
    return None


def create_resource(
    session: Session,
    *,
    tenant_id: str,
    resource_type: str,
    body: dict[str, Any],
    resource_id: str | None = None,
) -> dict[str, Any]:
    if resource_type not in CLINICAL_TYPES:
        raise ValueError(f"Unsupported resource type: {resource_type}")
    rid = resource_id or body.get("id") or new_id()
    resource = deepcopy(body)
    resource["resourceType"] = resource_type
    resource["id"] = rid
    meta = dict(resource.get("meta") or {})
    meta["versionId"] = "1"
    meta["lastUpdated"] = _iso_now()
    resource["meta"] = meta
    row = FhirResource(
        id=rid,
        resource_type=resource_type,
        tenant_id=tenant_id,
        patient_id=patient_id_from_resource(resource_type, resource),
        resource=resource,
        version_id=1,
        last_updated=utcnow(),
    )
    session.add(row)
    session.flush()
    return resource


def get_resource(
    session: Session,
    *,
    tenant_id: str,
    resource_type: str,
    resource_id: str,
) -> dict[str, Any] | None:
    row = session.execute(
        select(FhirResource).where(
            FhirResource.tenant_id == tenant_id,
            FhirResource.resource_type == resource_type,
            FhirResource.id == resource_id,
        )
    ).scalar_one_or_none()
    return deepcopy(row.resource) if row else None


def update_resource(
    session: Session,
    *,
    tenant_id: str,
    resource_type: str,
    resource_id: str,
    body: dict[str, Any],
) -> dict[str, Any] | None:
    row = session.execute(
        select(FhirResource).where(
            FhirResource.tenant_id == tenant_id,
            FhirResource.resource_type == resource_type,
            FhirResource.id == resource_id,
        )
    ).scalar_one_or_none()
    if row is None:
        return None
    resource = deepcopy(body)
    resource["resourceType"] = resource_type
    resource["id"] = resource_id
    row.version_id += 1
    meta = dict(resource.get("meta") or {})
    meta["versionId"] = str(row.version_id)
    meta["lastUpdated"] = _iso_now()
    resource["meta"] = meta
    row.resource = resource
    row.patient_id = patient_id_from_resource(resource_type, resource)
    row.last_updated = utcnow()
    session.flush()
    return resource


def search_resources(
    session: Session,
    *,
    tenant_id: str,
    resource_type: str,
    patient_id: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    stmt = select(FhirResource).where(
        FhirResource.tenant_id == tenant_id,
        FhirResource.resource_type == resource_type,
    )
    if patient_id is not None:
        stmt = stmt.where(FhirResource.patient_id == patient_id)
    stmt = stmt.order_by(FhirResource.last_updated.desc()).limit(limit)
    return [deepcopy(row.resource) for row in session.execute(stmt).scalars()]


def bundle_search(resources: list[dict[str, Any]], *, total: int | None = None) -> dict[str, Any]:
    return {
        "resourceType": "Bundle",
        "type": "searchset",
        "total": total if total is not None else len(resources),
        "entry": [{"resource": r} for r in resources],
    }


def write_provenance(
    session: Session,
    *,
    tenant_id: str,
    target_type: str,
    target_id: str,
    patient_id: str | None,
    agent_user_id: str,
    activity_code: str = "CREATE",
    entity_refs: list[tuple[str, str]] | None = None,
) -> dict[str, Any]:
    entities = [
        {"what": {"reference": f"{etype}/{eid}"}}
        for etype, eid in (entity_refs or [])
    ]
    body: dict[str, Any] = {
        "resourceType": "Provenance",
        "target": [{"reference": f"{target_type}/{target_id}"}],
        "recorded": _iso_now(),
        "activity": {"coding": [{"system": "http://terminology.hl7.org/CodeSystem/v3-DataOperation", "code": activity_code}]},
        "agent": [
            {
                "who": {"reference": f"Practitioner/{agent_user_id}"},
            }
        ],
    }
    if patient_id:
        body["patient"] = {"reference": f"Patient/{patient_id}"}
    if entities:
        body["entity"] = entities
    return create_resource(session, tenant_id=tenant_id, resource_type="Provenance", body=body)


def ensure_patient_for_user(
    session: Session,
    *,
    tenant_id: str,
    user_id: str,
    display_name: str = "",
) -> dict[str, Any]:
    """Idempotent Patient resource keyed by user id for portal linkage."""
    existing = get_resource(
        session, tenant_id=tenant_id, resource_type="Patient", resource_id=user_id
    )
    if existing:
        return existing
    name = display_name or "Patient"
    return create_resource(
        session,
        tenant_id=tenant_id,
        resource_type="Patient",
        resource_id=user_id,
        body={
            "resourceType": "Patient",
            "active": True,
            "name": [{"text": name, "use": "usual"}],
            "identifier": [
                {
                    "system": "urn:healthomatix:user",
                    "value": user_id,
                }
            ],
        },
    )
