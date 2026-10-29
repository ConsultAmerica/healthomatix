"""Insurance eligibility adapter (X12 270/271 conceptually). Sandbox Fake only."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol
from uuid import uuid4


ELIGIBILITY_DISCLAIMER = (
    "Coverage verification does not guarantee claim payment. Benefits shown are "
    "sandbox/synthetic responses for demonstration only."
)


@dataclass(frozen=True)
class EligibilityResult:
    request_reference: str
    response_reference: str
    coverage_status: str
    financial_readiness: str
    benefits_summary: dict[str, Any]
    disclaimer: str


class EligibilityPort(Protocol):
    def verify(
        self,
        *,
        payer_identifier: str,
        member_identifier: str,
        service_type: str = "30",
    ) -> EligibilityResult: ...


class FakeEligibilityAdapter:
    """Deterministic sandbox eligibility — no real payer network."""

    provider = "fake-eligibility"

    def verify(
        self,
        *,
        payer_identifier: str,
        member_identifier: str,
        service_type: str = "30",
    ) -> EligibilityResult:
        req = f"270-{uuid4().hex[:12]}"
        resp = f"271-{uuid4().hex[:12]}"
        inactive = member_identifier.upper().endswith("INACTIVE") or member_identifier.endswith("0000")
        if inactive:
            return EligibilityResult(
                request_reference=req,
                response_reference=resp,
                coverage_status="inactive",
                financial_readiness="inactive_coverage",
                benefits_summary={
                    "payer_identifier": payer_identifier,
                    "service_type": service_type,
                    "plan_status": "inactive",
                },
                disclaimer=ELIGIBILITY_DISCLAIMER,
            )
        return EligibilityResult(
            request_reference=req,
            response_reference=resp,
            coverage_status="active",
            financial_readiness="active_coverage",
            benefits_summary={
                "payer_identifier": payer_identifier,
                "service_type": service_type,
                "plan_status": "active",
                "copay_office_cents": 2500,
                "deductible_remaining_cents": 15000,
                "coinsurance_percent": 20,
                "prior_auth_indicated": False,
            },
            disclaimer=ELIGIBILITY_DISCLAIMER,
        )


def build_eligibility_adapter() -> EligibilityPort:
    return FakeEligibilityAdapter()
