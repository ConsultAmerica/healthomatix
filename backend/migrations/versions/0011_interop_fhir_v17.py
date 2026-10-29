"""Integration hub, identity links, terminology, import/export (V1.7).

Revision ID: 0011_interop_fhir_v17
Revises: 0010_rcm_saas_v16
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011_interop_fhir_v17"
down_revision: str | None = "0010_rcm_saas_v16"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "integration_connections",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(36), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("connection_name", sa.String(120), nullable=False),
        sa.Column("integration_type", sa.String(32), nullable=False),
        sa.Column("external_system", sa.String(120), nullable=False),
        sa.Column("base_url", sa.String(512), nullable=False, server_default=""),
        sa.Column("fhir_version", sa.String(16), nullable=False, server_default="4.0.1"),
        sa.Column("authentication_type", sa.String(32), nullable=False, server_default="sandbox"),
        sa.Column("secret_reference", sa.String(128), nullable=False, server_default=""),
        sa.Column("authorized_scopes", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="configured"),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_int_conn_tenant", "integration_connections", ["tenant_id", "status"])

    op.create_table(
        "integration_transactions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(36), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "connection_id",
            sa.String(36),
            sa.ForeignKey("integration_connections.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("direction", sa.String(16), nullable=False),
        sa.Column("message_type", sa.String(64), nullable=False),
        sa.Column("external_message_id", sa.String(128), nullable=False),
        sa.Column("correlation_id", sa.String(128), nullable=False, server_default=""),
        sa.Column("status", sa.String(24), nullable=False, server_default="received"),
        sa.Column("payload_reference", sa.String(256), nullable=False, server_default=""),
        sa.Column("payload_summary", sa.JSON(), nullable=False),
        sa.Column("error_code", sa.String(64), nullable=False, server_default=""),
        sa.Column("error_summary", sa.Text(), nullable=False, server_default=""),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint(
            "tenant_id", "connection_id", "external_message_id", name="uq_int_txn_external"
        ),
    )
    op.create_index(
        "ix_int_txn_tenant_status",
        "integration_transactions",
        ["tenant_id", "status", "received_at"],
    )

    op.create_table(
        "integration_jobs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(36), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "transaction_id",
            sa.String(36),
            sa.ForeignKey("integration_transactions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("job_type", sa.String(64), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="queued"),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_int_job_status", "integration_jobs", ["tenant_id", "status", "next_retry_at"])

    op.create_table(
        "external_resource_references",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(36), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "connection_id",
            sa.String(36),
            sa.ForeignKey("integration_connections.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("resource_type", sa.String(64), nullable=False),
        sa.Column("external_resource_id", sa.String(128), nullable=False),
        sa.Column("local_entity_type", sa.String(64), nullable=False),
        sa.Column("local_entity_id", sa.String(36), nullable=False),
        sa.Column("version_reference", sa.String(64), nullable=False, server_default=""),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "tenant_id",
            "connection_id",
            "resource_type",
            "external_resource_id",
            name="uq_ext_resource",
        ),
    )

    op.create_table(
        "patient_identity_links",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(36), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("patient_id", sa.String(36), nullable=True),
        sa.Column("external_system", sa.String(120), nullable=False),
        sa.Column("external_identifier", sa.String(128), nullable=False),
        sa.Column("assigning_authority", sa.String(128), nullable=False, server_default=""),
        sa.Column("verification_status", sa.String(32), nullable=False, server_default="manual_review"),
        sa.Column("match_evidence", sa.JSON(), nullable=False),
        sa.Column("verified_by_user_id", sa.String(36), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "tenant_id",
            "external_system",
            "external_identifier",
            "assigning_authority",
            name="uq_pil_external",
        ),
    )
    op.create_index("ix_pil_tenant_patient", "patient_identity_links", ["tenant_id", "patient_id"])

    op.create_table(
        "terminology_mappings",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("source_system", sa.String(120), nullable=False),
        sa.Column("source_code", sa.String(64), nullable=False),
        sa.Column("source_display", sa.String(200), nullable=False, server_default=""),
        sa.Column("target_system", sa.String(120), nullable=False),
        sa.Column("target_code", sa.String(64), nullable=False),
        sa.Column("mapping_version", sa.String(32), nullable=False, server_default="1"),
        sa.Column("status", sa.String(24), nullable=False, server_default="proposed"),
        sa.Column("reviewed_by_user_id", sa.String(36), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "source_system",
            "source_code",
            "target_system",
            "mapping_version",
            name="uq_term_map",
        ),
    )

    op.create_table(
        "clinical_import_batches",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(36), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_connection_id", sa.String(36), nullable=True),
        sa.Column("import_type", sa.String(32), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="preview"),
        sa.Column("requested_by_user_id", sa.String(36), nullable=False),
        sa.Column("approved_by_user_id", sa.String(36), nullable=True),
        sa.Column("summary", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_import_batch_tenant", "clinical_import_batches", ["tenant_id", "status"])

    op.create_table(
        "clinical_import_items",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(36), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "batch_id",
            sa.String(36),
            sa.ForeignKey("clinical_import_batches.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("resource_type", sa.String(64), nullable=False),
        sa.Column("external_identifier", sa.String(128), nullable=False),
        sa.Column("mapping_status", sa.String(24), nullable=False, server_default="pending"),
        sa.Column("validation_status", sa.String(24), nullable=False, server_default="pending"),
        sa.Column("import_status", sa.String(24), nullable=False, server_default="pending"),
        sa.Column("local_entity_reference", sa.String(128), nullable=False, server_default=""),
        sa.Column("resource_preview", sa.JSON(), nullable=False),
        sa.Column("error_summary", sa.Text(), nullable=False, server_default=""),
    )
    op.create_index(
        "ix_import_item_batch",
        "clinical_import_items",
        ["tenant_id", "batch_id", "import_status"],
    )

    op.create_table(
        "patient_data_exports",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(36), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("patient_id", sa.String(36), nullable=False),
        sa.Column("requested_by_user_id", sa.String(36), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="ready"),
        sa.Column("format", sa.String(32), nullable=False, server_default="fhir_r4_bundle"),
        sa.Column("bundle_json", sa.JSON(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_export_tenant_patient",
        "patient_data_exports",
        ["tenant_id", "patient_id", "created_at"],
    )

    op.create_table(
        "data_exchange_audit_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(36), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("actor_user_id", sa.String(36), nullable=True),
        sa.Column("patient_id", sa.String(36), nullable=True),
        sa.Column("connection_id", sa.String(36), nullable=True),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("resource_type", sa.String(64), nullable=False, server_default=""),
        sa.Column("resource_reference", sa.String(128), nullable=False, server_default=""),
        sa.Column("outcome", sa.String(24), nullable=False, server_default="success"),
        sa.Column("purpose_reference", sa.String(128), nullable=False, server_default=""),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_dea_tenant_time", "data_exchange_audit_events", ["tenant_id", "occurred_at"])


def downgrade() -> None:
    op.drop_index("ix_dea_tenant_time", table_name="data_exchange_audit_events")
    op.drop_table("data_exchange_audit_events")
    op.drop_index("ix_export_tenant_patient", table_name="patient_data_exports")
    op.drop_table("patient_data_exports")
    op.drop_index("ix_import_item_batch", table_name="clinical_import_items")
    op.drop_table("clinical_import_items")
    op.drop_index("ix_import_batch_tenant", table_name="clinical_import_batches")
    op.drop_table("clinical_import_batches")
    op.drop_table("terminology_mappings")
    op.drop_index("ix_pil_tenant_patient", table_name="patient_identity_links")
    op.drop_table("patient_identity_links")
    op.drop_table("external_resource_references")
    op.drop_index("ix_int_job_status", table_name="integration_jobs")
    op.drop_table("integration_jobs")
    op.drop_index("ix_int_txn_tenant_status", table_name="integration_transactions")
    op.drop_table("integration_transactions")
    op.drop_index("ix_int_conn_tenant", table_name="integration_connections")
    op.drop_table("integration_connections")
