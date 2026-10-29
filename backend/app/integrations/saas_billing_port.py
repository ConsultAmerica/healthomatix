"""Healthomatix SaaS subscription billing adapter. Separate from patient RCM. Sandbox Fake."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from uuid import uuid4


@dataclass(frozen=True)
class CheckoutResult:
    provider_reference: str
    status: str
    invoice_reference: str


class SaasBillingPort(Protocol):
    def create_checkout(
        self,
        *,
        tenant_id: str,
        plan_code: str,
    ) -> CheckoutResult: ...


class FakeSaasBillingAdapter:
    """Sandbox subscription checkout — no card data, no real processor."""

    provider = "fake-saas-billing"

    def create_checkout(self, *, tenant_id: str, plan_code: str) -> CheckoutResult:
        return CheckoutResult(
            provider_reference=f"sub_{uuid4().hex[:16]}",
            status="active",
            invoice_reference=f"inv_{uuid4().hex[:12]}",
        )


def build_saas_billing_adapter() -> SaasBillingPort:
    return FakeSaasBillingAdapter()
