"""Phase 1 identity, tenancy, profiles, consent, documents, and audit.

Revision ID: 0001_phase1_foundation
Revises:
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001_phase1_foundation"
down_revision: str | None = None
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def _install_audit_triggers() -> None:
    dialect = op.get_bind().dialect.name
    if dialect == "sqlite":
        op.execute(
            """
            CREATE TRIGGER audit_events_no_update BEFORE UPDATE ON audit_events
            BEGIN SELECT RAISE(ABORT, 'audit events are append-only'); END
            """
        )
        op.execute(
            """
            CREATE TRIGGER audit_events_no_delete BEFORE DELETE ON audit_events
            BEGIN SELECT RAISE(ABORT, 'audit events are append-only'); END
            """
        )
    elif dialect == "postgresql":
        op.execute(
            """
            CREATE FUNCTION healthomatix_reject_audit_mutation()
            RETURNS trigger AS $$
            BEGIN
                RAISE EXCEPTION 'audit events are append-only';
            END;
            $$ LANGUAGE plpgsql
            """
        )
        op.execute(
            """
            CREATE TRIGGER audit_events_no_update_or_delete
            BEFORE UPDATE OR DELETE ON audit_events
            FOR EACH ROW EXECUTE FUNCTION healthomatix_reject_audit_mutation()
            """
        )
    else:
        raise RuntimeError(f"Audit immutability is not configured for {dialect}.")


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("issuer", sa.String(512), nullable=False),
        sa.Column("subject", sa.String(512), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("issuer", "subject", name="uq_users_issuer_subject"),
    )
    op.create_table(
        "tenants",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("slug", sa.String(96), nullable=False, unique=True),
        sa.Column("display_name", sa.String(200), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "tenant_memberships",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(36), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", sa.String(24), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "user_id", name="uq_membership_tenant_user"),
        sa.CheckConstraint("role IN ('tenant_admin', 'patient', 'provider', 'auditor')", name="ck_membership_role"),
        sa.CheckConstraint("status IN ('active', 'inactive', 'revoked')", name="ck_membership_status"),
    )
    op.create_index("ix_membership_user_status", "tenant_memberships", ["user_id", "status"])
    op.create_table(
        "patient_profiles",
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("preferred_name", sa.String(120), nullable=False),
        sa.Column("legal_name", sa.String(200), nullable=False),
        sa.Column("phone", sa.String(40), nullable=False),
        sa.Column("preferred_language", sa.String(32), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "clinic_patients",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(36), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("patient_user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("chart_number", sa.String(96)),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "patient_user_id", name="uq_clinic_patient_identity"),
        sa.UniqueConstraint("tenant_id", "chart_number", name="uq_clinic_patient_chart_number"),
        sa.CheckConstraint("status IN ('active', 'inactive', 'merged')", name="ck_clinic_patient_status"),
    )
    op.create_index(
        "ix_clinic_patient_tenant_status",
        "clinic_patients",
        ["tenant_id", "status"],
    )
    op.create_table(
        "provider_profiles",
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("display_name", sa.String(200), nullable=False),
        sa.Column("specialty", sa.String(120), nullable=False),
        sa.Column("profile_status", sa.String(16), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "profile_status IN ('draft', 'pending', 'active', 'suspended')",
            name="ck_provider_profile_status",
        ),
    )
    op.create_table(
        "provider_credentials",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(36), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("provider_user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("jurisdiction", sa.String(32), nullable=False),
        sa.Column("credential_type", sa.String(96), nullable=False),
        sa.Column("regulator", sa.String(200), nullable=False),
        sa.Column("verification_reference", sa.String(512), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reviewed_by_user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)),
        sa.Column("review_source", sa.String(512), nullable=False),
        sa.CheckConstraint("status IN ('pending', 'verified', 'rejected', 'revoked')", name="ck_provider_credential_status"),
    )
    op.create_index(
        "ix_provider_credential_tenant_status",
        "provider_credentials",
        ["tenant_id", "status"],
    )
    op.create_table(
        "consent_grants",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(36), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("patient_user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("granted_by_user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("purpose", sa.String(96), nullable=False),
        sa.Column("scope", sa.String(128), nullable=False),
        sa.Column("policy_version", sa.String(64), nullable=False),
        sa.Column("granted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
    )
    op.create_index(
        "ix_consent_grant_patient_scope",
        "consent_grants",
        ["tenant_id", "patient_user_id", "purpose", "scope", "granted_at"],
    )
    op.create_table(
        "consent_withdrawals",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("grant_id", sa.String(36), sa.ForeignKey("consent_grants.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("actor_user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("reason_code", sa.String(64), nullable=False),
        sa.Column("withdrawn_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("grant_id", name="uq_consent_withdrawal_grant"),
    )
    op.create_table(
        "medical_documents",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(36), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("patient_user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("uploaded_by_user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("storage_key", sa.String(1024), nullable=False, unique=True),
        sa.Column("original_filename", sa.String(255), nullable=False),
        sa.Column("content_type", sa.String(128), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("lifecycle_state", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "lifecycle_state IN ('reserved', 'stored', 'quarantined', 'deleted')",
            name="ck_medical_document_lifecycle",
        ),
    )
    op.create_index(
        "ix_medical_document_patient_created",
        "medical_documents",
        ["tenant_id", "patient_user_id", "created_at"],
    )
    op.create_table(
        "audit_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(36), sa.ForeignKey("tenants.id", ondelete="SET NULL")),
        sa.Column("actor_user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("action", sa.String(128), nullable=False),
        sa.Column("subject_type", sa.String(64), nullable=False),
        sa.Column("subject_id", sa.String(128), nullable=False),
        sa.Column("request_id", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("length(action) BETWEEN 1 AND 128", name="ck_audit_event_action_length"),
    )
    op.create_index("ix_audit_events_tenant_time", "audit_events", ["tenant_id", "created_at"])
    _install_audit_triggers()


def downgrade() -> None:
    dialect = op.get_bind().dialect.name
    if dialect == "sqlite":
        op.execute("DROP TRIGGER IF EXISTS audit_events_no_delete")
        op.execute("DROP TRIGGER IF EXISTS audit_events_no_update")
    elif dialect == "postgresql":
        op.execute("DROP TRIGGER IF EXISTS audit_events_no_update_or_delete ON audit_events")
        op.execute("DROP FUNCTION IF EXISTS healthomatix_reject_audit_mutation()")
    op.drop_index("ix_audit_events_tenant_time", table_name="audit_events")
    op.drop_table("audit_events")
    op.drop_index("ix_medical_document_patient_created", table_name="medical_documents")
    op.drop_table("medical_documents")
    op.drop_table("consent_withdrawals")
    op.drop_index("ix_consent_grant_patient_scope", table_name="consent_grants")
    op.drop_table("consent_grants")
    op.drop_index("ix_provider_credential_tenant_status", table_name="provider_credentials")
    op.drop_table("provider_credentials")
    op.drop_table("provider_profiles")
    op.drop_index("ix_clinic_patient_tenant_status", table_name="clinic_patients")
    op.drop_table("clinic_patients")
    op.drop_table("patient_profiles")
    op.drop_index("ix_membership_user_status", table_name="tenant_memberships")
    op.drop_table("tenant_memberships")
    op.drop_table("tenants")
    op.drop_table("users")
