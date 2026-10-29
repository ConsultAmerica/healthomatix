"""Document processing jobs for V1.3 lab intelligence.

Revision ID: 0007_document_processing_jobs
Revises: 0006_consultation_clinical_ai
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007_document_processing_jobs"
down_revision: str | None = "0006_consultation_clinical_ai"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "document_processing_jobs",
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
        sa.Column("job_type", sa.String(32), nullable=False, server_default="lab_extract"),
        sa.Column("status", sa.String(32), nullable=False, server_default="queued"),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("processor_version", sa.String(64), nullable=False, server_default="v1.3-lab"),
        sa.Column("model_identifier", sa.String(128), nullable=False, server_default="fake-extraction-v1"),
        sa.Column("prompt_version", sa.String(64), nullable=False, server_default="lab_parser_v1"),
        sa.Column("classification", sa.JSON(), nullable=False),
        sa.Column("extraction_id", sa.String(36), nullable=True),
        sa.Column("error_code", sa.String(64), nullable=True),
        sa.Column("error_summary", sa.String(500), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_doc_job_tenant_document",
        "document_processing_jobs",
        ["tenant_id", "document_id", "created_at"],
    )
    op.create_index(
        "ix_doc_job_tenant_status",
        "document_processing_jobs",
        ["tenant_id", "status"],
    )
    op.add_column(
        "extractions",
        sa.Column("processing_job_id", sa.String(36), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("extractions", "processing_job_id")
    op.drop_index("ix_doc_job_tenant_status", table_name="document_processing_jobs")
    op.drop_index("ix_doc_job_tenant_document", table_name="document_processing_jobs")
    op.drop_table("document_processing_jobs")
