"""FHIR resource store and document extractions.

Revision ID: 0005_fhir_core_extractions
Revises: 0004_documents_messaging_patient_link
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005_fhir_core_extractions"
down_revision: str | None = "0004_documents_messaging_patient_link"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "fhir_resources",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("resource_type", sa.String(64), nullable=False),
        sa.Column(
            "tenant_id",
            sa.String(36),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("patient_id", sa.String(36), nullable=True),
        sa.Column("resource", sa.JSON(), nullable=False),
        sa.Column("version_id", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("last_updated", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_fhir_type_tenant", "fhir_resources", ["resource_type", "tenant_id"])
    op.create_index(
        "ix_fhir_type_tenant_patient",
        "fhir_resources",
        ["resource_type", "tenant_id", "patient_id"],
    )

    op.create_table(
        "extractions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "tenant_id",
            sa.String(36),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "document_id",
            sa.String(36),
            sa.ForeignKey("medical_documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("patient_id", sa.String(36), nullable=False),
        sa.Column("document_reference_id", sa.String(36), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="draft"),
        sa.Column("fields", sa.JSON(), nullable=False),
        sa.Column("ocr_text", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "created_by_user_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "verified_by_user_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_extraction_tenant_document", "extractions", ["tenant_id", "document_id"]
    )
    op.create_index(
        "ix_extraction_tenant_status", "extractions", ["tenant_id", "status"]
    )


def downgrade() -> None:
    op.drop_index("ix_extraction_tenant_status", table_name="extractions")
    op.drop_index("ix_extraction_tenant_document", table_name="extractions")
    op.drop_table("extractions")
    op.drop_index("ix_fhir_type_tenant_patient", table_name="fhir_resources")
    op.drop_index("ix_fhir_type_tenant", table_name="fhir_resources")
    op.drop_table("fhir_resources")
