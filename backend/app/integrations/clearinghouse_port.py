"""Claims clearinghouse adapter (837/999/277CA conceptually). Sandbox Fake only."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol
from uuid import uuid4


@dataclass(frozen=True)
class SubmissionResult:
    clearinghouse_reference: str
    submission_status: str  # transmitted | accepted | rejected
    acknowledgment_code: str
    payer_claim_reference: str
    response_payload: dict[str, Any]


@dataclass(frozen=True)
class RemittanceLine:
    claim_number: str
    paid_cents: int
    contractual_cents: int
    patient_responsibility_cents: int
    denial_code: str | None = None
    denial_category: str | None = None


@dataclass(frozen=True)
class RemittanceBatch:
    remittance_reference: str
    total_amount_cents: int
    lines: list[RemittanceLine]


class ClearinghousePort(Protocol):
    def submit_professional_claim(
        self,
        *,
        claim_number: str,
        total_charge_cents: int,
        force_reject: bool = False,
    ) -> SubmissionResult: ...

    def build_sandbox_remittance(
        self,
        *,
        claim_number: str,
        total_charge_cents: int,
        deny: bool = False,
    ) -> RemittanceBatch: ...


class FakeClearinghouseAdapter:
    """Sandbox claim submission and remittance — never transmits real claims."""

    provider = "fake-clearinghouse"

    def submit_professional_claim(
        self,
        *,
        claim_number: str,
        total_charge_cents: int,
        force_reject: bool = False,
    ) -> SubmissionResult:
        ch_ref = f"CH-{uuid4().hex[:10]}"
        if force_reject or claim_number.upper().endswith("REJECT"):
            return SubmissionResult(
                clearinghouse_reference=ch_ref,
                submission_status="rejected",
                acknowledgment_code="A3",
                payer_claim_reference="",
                response_payload={
                    "type": "999",
                    "note": "Sandbox clearinghouse rejection — not a payer denial.",
                    "claim_number": claim_number,
                },
            )
        return SubmissionResult(
            clearinghouse_reference=ch_ref,
            submission_status="accepted",
            acknowledgment_code="A1",
            payer_claim_reference=f"PAYER-{uuid4().hex[:8]}",
            response_payload={
                "type": "277CA",
                "note": "Sandbox acceptance of transmission — not proof of payment.",
                "claim_number": claim_number,
                "billed_cents": total_charge_cents,
            },
        )

    def build_sandbox_remittance(
        self,
        *,
        claim_number: str,
        total_charge_cents: int,
        deny: bool = False,
    ) -> RemittanceBatch:
        ref = f"835-{uuid4().hex[:10]}"
        if deny:
            return RemittanceBatch(
                remittance_reference=ref,
                total_amount_cents=0,
                lines=[
                    RemittanceLine(
                        claim_number=claim_number,
                        paid_cents=0,
                        contractual_cents=0,
                        patient_responsibility_cents=0,
                        denial_code="CO-50",
                        denial_category="medical_necessity_review",
                    )
                ],
            )
        paid = int(total_charge_cents * 0.7)
        contractual = int(total_charge_cents * 0.2)
        patient = total_charge_cents - paid - contractual
        return RemittanceBatch(
            remittance_reference=ref,
            total_amount_cents=paid,
            lines=[
                RemittanceLine(
                    claim_number=claim_number,
                    paid_cents=paid,
                    contractual_cents=contractual,
                    patient_responsibility_cents=patient,
                )
            ],
        )


def build_clearinghouse_adapter() -> ClearinghousePort:
    return FakeClearinghouseAdapter()
