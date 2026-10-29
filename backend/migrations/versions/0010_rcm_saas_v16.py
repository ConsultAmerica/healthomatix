"""Insurance, RCM, and SaaS subscription tables (V1.6).

Revision ID: 0010_rcm_saas_v16
Revises: 0009_ai_clinical_copilot_v15
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010_rcm_saas_v16"
down_revision: str | None = "0009_ai_clinical_copilot_v15"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "insurance_payers",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("payer_identifier", sa.String(64), nullable=False, unique=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "patient_insurance_policies",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(36), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("patient_id", sa.String(36), nullable=False),
        sa.Column("payer_id", sa.String(36), sa.ForeignKey("insurance_payers.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("plan_name", sa.String(200), nullable=False, server_default=""),
        sa.Column("member_identifier", sa.String(64), nullable=False),
        sa.Column("group_identifier", sa.String(64), nullable=False, server_default=""),
        sa.Column("subscriber_name", sa.String(200), nullable=False, server_default=""),
        sa.Column("subscriber_relationship", sa.String(32), nullable=False, server_default="self"),
        sa.Column("coverage_order", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("effective_date", sa.Date(), nullable=True),
        sa.Column("termination_date", sa.Date(), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_ins_policy_tenant_patient",
        "patient_insurance_policies",
        ["tenant_id", "patient_id", "coverage_order"],
    )
    op.create_table(
        "eligibility_checks",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(36), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("patient_id", sa.String(36), nullable=False),
        sa.Column(
            "insurance_policy_id",
            sa.String(36),
            sa.ForeignKey("patient_insurance_policies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("appointment_id", sa.String(36), nullable=True),
        sa.Column("request_reference", sa.String(128), nullable=False, server_default=""),
        sa.Column("response_reference", sa.String(128), nullable=False, server_default=""),
        sa.Column("coverage_status", sa.String(32), nullable=False, server_default="unknown"),
        sa.Column("financial_readiness", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("benefits_summary", sa.JSON(), nullable=False),
        sa.Column("disclaimer", sa.Text(), nullable=False, server_default=""),
        sa.Column("status", sa.String(16), nullable=False, server_default="completed"),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_elig_tenant_patient", "eligibility_checks", ["tenant_id", "patient_id", "checked_at"])

    op.create_table(
        "encounter_charges",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(36), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("encounter_id", sa.String(36), nullable=False),
        sa.Column("patient_id", sa.String(36), nullable=False),
        sa.Column("provider_user_id", sa.String(36), nullable=False),
        sa.Column("service_date", sa.Date(), nullable=False),
        sa.Column("service_code", sa.String(32), nullable=False),
        sa.Column("service_code_system", sa.String(16), nullable=False, server_default="CPT"),
        sa.Column("diagnosis_codes", sa.JSON(), nullable=False),
        sa.Column("units", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("charge_amount_cents", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="draft"),
        sa.Column("ai_suggested", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("ai_rationale", sa.Text(), nullable=False, server_default=""),
        sa.Column("documentation_references", sa.JSON(), nullable=False),
        sa.Column("approved_by_user_id", sa.String(36), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_charge_tenant_encounter", "encounter_charges", ["tenant_id", "encounter_id", "status"])

    op.create_table(
        "claims",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(36), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("patient_id", sa.String(36), nullable=False),
        sa.Column("encounter_id", sa.String(36), nullable=False),
        sa.Column("payer_id", sa.String(36), sa.ForeignKey("insurance_payers.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("insurance_policy_id", sa.String(36), nullable=True),
        sa.Column("billing_provider_user_id", sa.String(36), nullable=False),
        sa.Column("rendering_provider_user_id", sa.String(36), nullable=False),
        sa.Column("claim_type", sa.String(32), nullable=False, server_default="professional"),
        sa.Column("claim_number", sa.String(64), nullable=False),
        sa.Column("diagnosis_codes", sa.JSON(), nullable=False),
        sa.Column("total_charge_cents", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(24), nullable=False, server_default="draft"),
        sa.Column("payer_claim_reference", sa.String(128), nullable=False, server_default=""),
        sa.Column("clearinghouse_reference", sa.String(128), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_claim_tenant_status", "claims", ["tenant_id", "status", "created_at"])

    op.create_table(
        "claim_lines",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(36), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("claim_id", sa.String(36), sa.ForeignKey("claims.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "charge_id",
            sa.String(36),
            sa.ForeignKey("encounter_charges.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("service_code", sa.String(32), nullable=False),
        sa.Column("units", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("billed_amount_cents", sa.Integer(), nullable=False),
    )
    op.create_index("ix_claim_line_claim", "claim_lines", ["tenant_id", "claim_id"])

    op.create_table(
        "claim_submissions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(36), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("claim_id", sa.String(36), sa.ForeignKey("claims.id", ondelete="CASCADE"), nullable=False),
        sa.Column("clearinghouse_reference", sa.String(128), nullable=False),
        sa.Column("submission_status", sa.String(24), nullable=False),
        sa.Column("acknowledgment_code", sa.String(32), nullable=False, server_default=""),
        sa.Column("response_payload", sa.JSON(), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "idempotency_key", name="uq_claim_submission_idem"),
    )
    op.create_index("ix_claim_sub_claim", "claim_submissions", ["tenant_id", "claim_id"])

    op.create_table(
        "claim_denials",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(36), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("claim_id", sa.String(36), sa.ForeignKey("claims.id", ondelete="CASCADE"), nullable=False),
        sa.Column("denial_code", sa.String(32), nullable=False),
        sa.Column("denial_category", sa.String(64), nullable=False),
        sa.Column("denial_reason", sa.Text(), nullable=False, server_default=""),
        sa.Column("denied_amount_cents", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(16), nullable=False, server_default="open"),
        sa.Column("assigned_to_user_id", sa.String(36), nullable=True),
        sa.Column("resolution_notes", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_denial_tenant_status", "claim_denials", ["tenant_id", "status"])

    op.create_table(
        "payer_remittances",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(36), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("payer_id", sa.String(36), sa.ForeignKey("insurance_payers.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("remittance_reference", sa.String(128), nullable=False),
        sa.Column("payment_date", sa.Date(), nullable=False),
        sa.Column("total_amount_cents", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="posted"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_remit_tenant", "payer_remittances", ["tenant_id", "payment_date"])

    op.create_table(
        "payment_allocations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(36), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "remittance_id",
            sa.String(36),
            sa.ForeignKey("payer_remittances.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("claim_id", sa.String(36), sa.ForeignKey("claims.id", ondelete="CASCADE"), nullable=False),
        sa.Column("claim_line_id", sa.String(36), nullable=True),
        sa.Column("amount_cents", sa.Integer(), nullable=False),
        sa.Column("adjustment_type", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_alloc_claim", "payment_allocations", ["tenant_id", "claim_id"])

    op.create_table(
        "patient_financial_transactions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(36), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("patient_id", sa.String(36), nullable=False),
        sa.Column("claim_id", sa.String(36), nullable=True),
        sa.Column("transaction_type", sa.String(32), nullable=False),
        sa.Column("amount_cents", sa.Integer(), nullable=False),
        sa.Column("reference", sa.String(128), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_pft_tenant_patient",
        "patient_financial_transactions",
        ["tenant_id", "patient_id", "created_at"],
    )

    op.create_table(
        "subscription_plans",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("plan_code", sa.String(64), nullable=False, unique=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("billing_model", sa.String(32), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        sa.Column("feature_codes", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "organization_subscriptions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(36), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "plan_id",
            sa.String(36),
            sa.ForeignKey("subscription_plans.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("payment_provider_reference", sa.String(128), nullable=False, server_default=""),
        sa.Column("status", sa.String(24), nullable=False, server_default="active"),
        sa.Column("billing_period_start", sa.Date(), nullable=True),
        sa.Column("billing_period_end", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_org_sub_tenant", "organization_subscriptions", ["tenant_id", "status"])

    op.create_table(
        "feature_entitlements",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(36), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("feature_code", sa.String(64), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("limit_value", sa.Integer(), nullable=True),
        sa.Column("effective_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "feature_code", name="uq_entitlement_tenant_feature"),
    )
    op.create_table(
        "usage_meter_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(36), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("subscription_id", sa.String(36), nullable=True),
        sa.Column("meter_type", sa.String(64), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("source_event_id", sa.String(128), nullable=False),
        sa.Column("billing_period_reference", sa.String(64), nullable=False, server_default=""),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "source_event_id", name="uq_usage_source_event"),
    )
    op.create_index(
        "ix_usage_tenant_meter", "usage_meter_events", ["tenant_id", "meter_type", "occurred_at"]
    )
    op.create_table(
        "platform_billing_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(36), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("provider_reference", sa.String(128), nullable=False, server_default=""),
        sa.Column("status", sa.String(24), nullable=False, server_default="recorded"),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_platform_bill_tenant", "platform_billing_events", ["tenant_id", "created_at"])


def downgrade() -> None:
    for table in (
        "platform_billing_events",
        "usage_meter_events",
        "feature_entitlements",
        "organization_subscriptions",
        "subscription_plans",
        "patient_financial_transactions",
        "payment_allocations",
        "payer_remittances",
        "claim_denials",
        "claim_submissions",
        "claim_lines",
        "claims",
        "encounter_charges",
        "eligibility_checks",
        "patient_insurance_policies",
        "insurance_payers",
    ):
        op.drop_table(table)
