"""V1.6 insurance, revenue cycle, and SaaS subscription entities.

Separate from clinical FHIR tables. Monetary amounts stored as integer cents.
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.db import Base
from app.models import new_id, utcnow


class InsurancePayer(Base):
    __tablename__ = "insurance_payers"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    payer_identifier: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    status: Mapped[str] = mapped_column(String(16), default="active", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )


class PatientInsurancePolicy(Base):
    __tablename__ = "patient_insurance_policies"
    __table_args__ = (
        Index("ix_ins_policy_tenant_patient", "tenant_id", "patient_id", "coverage_order"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    patient_id: Mapped[str] = mapped_column(String(36), nullable=False)
    payer_id: Mapped[str] = mapped_column(
        ForeignKey("insurance_payers.id", ondelete="RESTRICT"), nullable=False
    )
    plan_name: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    member_identifier: Mapped[str] = mapped_column(String(64), nullable=False)
    group_identifier: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    subscriber_name: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    subscriber_relationship: Mapped[str] = mapped_column(String(32), default="self", nullable=False)
    coverage_order: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    effective_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    termination_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="active", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )


class EligibilityCheck(Base):
    __tablename__ = "eligibility_checks"
    __table_args__ = (Index("ix_elig_tenant_patient", "tenant_id", "patient_id", "checked_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    patient_id: Mapped[str] = mapped_column(String(36), nullable=False)
    insurance_policy_id: Mapped[str] = mapped_column(
        ForeignKey("patient_insurance_policies.id", ondelete="CASCADE"), nullable=False
    )
    appointment_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    request_reference: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    response_reference: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    # active | inactive | unknown | error
    coverage_status: Mapped[str] = mapped_column(String(32), default="unknown", nullable=False)
    # not_checked | pending | active_coverage | inactive_coverage | failed | manual_review
    financial_readiness: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)
    benefits_summary: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    disclaimer: Mapped[str] = mapped_column(Text, default="", nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="completed", nullable=False)
    checked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )


class EncounterCharge(Base):
    __tablename__ = "encounter_charges"
    __table_args__ = (Index("ix_charge_tenant_encounter", "tenant_id", "encounter_id", "status"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    encounter_id: Mapped[str] = mapped_column(String(36), nullable=False)
    patient_id: Mapped[str] = mapped_column(String(36), nullable=False)
    provider_user_id: Mapped[str] = mapped_column(String(36), nullable=False)
    service_date: Mapped[date] = mapped_column(Date, nullable=False)
    service_code: Mapped[str] = mapped_column(String(32), nullable=False)
    service_code_system: Mapped[str] = mapped_column(String(16), default="CPT", nullable=False)
    diagnosis_codes: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    units: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    charge_amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    # draft | pending_review | approved | rejected | returned
    status: Mapped[str] = mapped_column(String(24), default="draft", nullable=False)
    ai_suggested: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    ai_rationale: Mapped[str] = mapped_column(Text, default="", nullable=False)
    documentation_references: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    approved_by_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )


class Claim(Base):
    __tablename__ = "claims"
    __table_args__ = (Index("ix_claim_tenant_status", "tenant_id", "status", "created_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    patient_id: Mapped[str] = mapped_column(String(36), nullable=False)
    encounter_id: Mapped[str] = mapped_column(String(36), nullable=False)
    payer_id: Mapped[str] = mapped_column(
        ForeignKey("insurance_payers.id", ondelete="RESTRICT"), nullable=False
    )
    insurance_policy_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    billing_provider_user_id: Mapped[str] = mapped_column(String(36), nullable=False)
    rendering_provider_user_id: Mapped[str] = mapped_column(String(36), nullable=False)
    claim_type: Mapped[str] = mapped_column(String(32), default="professional", nullable=False)
    claim_number: Mapped[str] = mapped_column(String(64), nullable=False)
    diagnosis_codes: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    total_charge_cents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # draft | validated | approved | submitted | accepted | rejected | denied | paid | partial
    status: Mapped[str] = mapped_column(String(24), default="draft", nullable=False)
    payer_claim_reference: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    clearinghouse_reference: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )


class ClaimLine(Base):
    __tablename__ = "claim_lines"
    __table_args__ = (Index("ix_claim_line_claim", "tenant_id", "claim_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    claim_id: Mapped[str] = mapped_column(
        ForeignKey("claims.id", ondelete="CASCADE"), nullable=False
    )
    charge_id: Mapped[str] = mapped_column(
        ForeignKey("encounter_charges.id", ondelete="RESTRICT"), nullable=False
    )
    service_code: Mapped[str] = mapped_column(String(32), nullable=False)
    units: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    billed_amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)


class ClaimSubmission(Base):
    __tablename__ = "claim_submissions"
    __table_args__ = (
        UniqueConstraint("tenant_id", "idempotency_key", name="uq_claim_submission_idem"),
        Index("ix_claim_sub_claim", "tenant_id", "claim_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    claim_id: Mapped[str] = mapped_column(
        ForeignKey("claims.id", ondelete="CASCADE"), nullable=False
    )
    clearinghouse_reference: Mapped[str] = mapped_column(String(128), nullable=False)
    # transmitted | accepted | rejected
    submission_status: Mapped[str] = mapped_column(String(24), nullable=False)
    acknowledgment_code: Mapped[str] = mapped_column(String(32), default="", nullable=False)
    response_payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )


class ClaimDenial(Base):
    __tablename__ = "claim_denials"
    __table_args__ = (Index("ix_denial_tenant_status", "tenant_id", "status"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    claim_id: Mapped[str] = mapped_column(
        ForeignKey("claims.id", ondelete="CASCADE"), nullable=False
    )
    denial_code: Mapped[str] = mapped_column(String(32), nullable=False)
    denial_category: Mapped[str] = mapped_column(String(64), nullable=False)
    denial_reason: Mapped[str] = mapped_column(Text, default="", nullable=False)
    denied_amount_cents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # open | assigned | resolved | appealed
    status: Mapped[str] = mapped_column(String(16), default="open", nullable=False)
    assigned_to_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    resolution_notes: Mapped[str] = mapped_column(Text, default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PayerRemittance(Base):
    __tablename__ = "payer_remittances"
    __table_args__ = (Index("ix_remit_tenant", "tenant_id", "payment_date"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    payer_id: Mapped[str] = mapped_column(
        ForeignKey("insurance_payers.id", ondelete="RESTRICT"), nullable=False
    )
    remittance_reference: Mapped[str] = mapped_column(String(128), nullable=False)
    payment_date: Mapped[date] = mapped_column(Date, nullable=False)
    total_amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="posted", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )


class PaymentAllocation(Base):
    __tablename__ = "payment_allocations"
    __table_args__ = (Index("ix_alloc_claim", "tenant_id", "claim_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    remittance_id: Mapped[str] = mapped_column(
        ForeignKey("payer_remittances.id", ondelete="CASCADE"), nullable=False
    )
    claim_id: Mapped[str] = mapped_column(
        ForeignKey("claims.id", ondelete="CASCADE"), nullable=False
    )
    claim_line_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    # payment | contractual | patient_responsibility | denial_adjustment
    adjustment_type: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )


class PatientFinancialTransaction(Base):
    """Append-only patient ledger. Reversals are new rows."""

    __tablename__ = "patient_financial_transactions"
    __table_args__ = (Index("ix_pft_tenant_patient", "tenant_id", "patient_id", "created_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    patient_id: Mapped[str] = mapped_column(String(36), nullable=False)
    claim_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    # charge | insurance_payment | adjustment | patient_payment | refund | responsibility
    transaction_type: Mapped[str] = mapped_column(String(32), nullable=False)
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    reference: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )


class SubscriptionPlan(Base):
    __tablename__ = "subscription_plans"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    plan_code: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    billing_model: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="active", nullable=False)
    feature_codes: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )


class OrganizationSubscription(Base):
    __tablename__ = "organization_subscriptions"
    __table_args__ = (Index("ix_org_sub_tenant", "tenant_id", "status"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    plan_id: Mapped[str] = mapped_column(
        ForeignKey("subscription_plans.id", ondelete="RESTRICT"), nullable=False
    )
    payment_provider_reference: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    # trial | active | past_due | suspended | cancelled
    status: Mapped[str] = mapped_column(String(24), default="active", nullable=False)
    billing_period_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    billing_period_end: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )


class FeatureEntitlement(Base):
    __tablename__ = "feature_entitlements"
    __table_args__ = (
        UniqueConstraint("tenant_id", "feature_code", name="uq_entitlement_tenant_feature"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    feature_code: Mapped[str] = mapped_column(String(64), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    limit_value: Mapped[int | None] = mapped_column(Integer, nullable=True)
    effective_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )


class UsageMeterEvent(Base):
    __tablename__ = "usage_meter_events"
    __table_args__ = (
        UniqueConstraint("tenant_id", "source_event_id", name="uq_usage_source_event"),
        Index("ix_usage_tenant_meter", "tenant_id", "meter_type", "occurred_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    subscription_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    meter_type: Mapped[str] = mapped_column(String(64), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    source_event_id: Mapped[str] = mapped_column(String(128), nullable=False)
    billing_period_reference: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )


class PlatformBillingEvent(Base):
    __tablename__ = "platform_billing_events"
    __table_args__ = (Index("ix_platform_bill_tenant", "tenant_id", "created_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    provider_reference: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="recorded", nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
