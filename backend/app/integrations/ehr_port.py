"""External EHR FHIR client port. Fake sandbox only — no real SMART tokens stored."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol
from uuid import uuid4


@dataclass(frozen=True)
class EhrCapability:
    fhir_version: str
    resources: list[str]
    smart_modes: list[str]


@dataclass(frozen=True)
class EhrAuthResult:
    status: str
    scopes: list[str]
    expires_in_seconds: int
    token_reference: str  # opaque secret reference, never a raw token in logs


class EhrClientPort(Protocol):
    def discover_capabilities(self, *, base_url: str) -> EhrCapability: ...

    def authorize_sandbox(self, *, scopes: list[str]) -> EhrAuthResult: ...

    def search_patients(self, *, family: str) -> list[dict[str, Any]]: ...

    def read_observations(self, *, patient_id: str) -> list[dict[str, Any]]: ...


class FakeEhrClientAdapter:
    """Deterministic sandbox EHR — no network, no browser token storage."""

    provider = "fake-ehr"

    def discover_capabilities(self, *, base_url: str) -> EhrCapability:
        return EhrCapability(
            fhir_version="4.0.1",
            resources=["Patient", "Observation", "DiagnosticReport", "Encounter", "DocumentReference"],
            smart_modes=["backend_service_sandbox"],
        )

    def authorize_sandbox(self, *, scopes: list[str]) -> EhrAuthResult:
        return EhrAuthResult(
            status="authorized",
            scopes=scopes or ["system/Patient.read", "system/Observation.read"],
            expires_in_seconds=3600,
            token_reference=f"secret://sandbox/{uuid4().hex[:12]}",
        )

    def search_patients(self, *, family: str) -> list[dict[str, Any]]:
        return [
            {
                "resourceType": "Patient",
                "id": f"ext-patient-{family.lower() or 'demo'}",
                "name": [{"family": family or "Demo", "given": ["Synthetic"]}],
                "birthDate": "1990-01-15",
                "identifier": [
                    {
                        "system": "urn:sandbox:mrn",
                        "value": f"MRN-{family.upper() or 'DEMO'}",
                    }
                ],
            }
        ]

    def read_observations(self, *, patient_id: str) -> list[dict[str, Any]]:
        return [
            {
                "resourceType": "Observation",
                "id": f"ext-obs-{patient_id[-8:]}",
                "status": "final",
                "code": {
                    "coding": [
                        {
                            "system": "http://loinc.org",
                            "code": "4548-4",
                            "display": "Hemoglobin A1c",
                        }
                    ],
                    "text": "Hemoglobin A1c",
                },
                "subject": {"reference": f"Patient/{patient_id}"},
                "valueQuantity": {"value": 5.6, "unit": "%", "system": "http://unitsofmeasure.org", "code": "%"},
                "effectiveDateTime": "2026-01-10T12:00:00Z",
            }
        ]


def build_ehr_client() -> EhrClientPort:
    return FakeEhrClientAdapter()
