"""Video sessions and clinical AI drafts.

Revision ID: 0006_consultation_clinical_ai
Revises: 0005_fhir_core_extractions
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006_consultation_clinical_ai"
down_revision: str | None = "0005_fhir_core_extractions"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "video_sessions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "tenant_id",
            sa.String(36),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "appointment_id",
            sa.String(36),
            sa.ForeignKey("appointments.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column(
            "patient_user_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "provider_user_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("clinic_patient_id", sa.String(36), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="scheduled"),
        sa.Column("video_provider", sa.String(32), nullable=False, server_default="fake"),
        sa.Column("room_id", sa.String(128), nullable=False),
        sa.Column("encounter_id", sa.String(36), nullable=True),
        sa.Column("follow_up_plan", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_video_session_tenant_appointment",
        "video_sessions",
        ["tenant_id", "appointment_id"],
    )
    op.create_index(
        "ix_video_session_tenant_status",
        "video_sessions",
        ["tenant_id", "status"],
    )

    op.create_table(
        "clinical_drafts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "tenant_id",
            sa.String(36),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("patient_id", sa.String(36), nullable=False),
        sa.Column("draft_type", sa.String(16), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="draft"),
        sa.Column("title", sa.String(200), nullable=False, server_default=""),
        sa.Column("content", sa.JSON(), nullable=False),
        sa.Column("source_links", sa.JSON(), nullable=False),
        sa.Column("session_id", sa.String(36), nullable=True),
        sa.Column("encounter_id", sa.String(36), nullable=True),
        sa.Column("approved_resource_id", sa.String(36), nullable=True),
        sa.Column(
            "created_by_user_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "approved_by_user_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_clinical_draft_tenant_patient",
        "clinical_drafts",
        ["tenant_id", "patient_id", "status"],
    )
    op.create_index(
        "ix_clinical_draft_tenant_type",
        "clinical_drafts",
        ["tenant_id", "draft_type"],
    )


def downgrade() -> None:
    op.drop_index("ix_clinical_draft_tenant_type", table_name="clinical_drafts")
    op.drop_index("ix_clinical_draft_tenant_patient", table_name="clinical_drafts")
    op.drop_table("clinical_drafts")
    op.drop_index("ix_video_session_tenant_status", table_name="video_sessions")
    op.drop_index("ix_video_session_tenant_appointment", table_name="video_sessions")
    op.drop_table("video_sessions")
