"""Waiting room, clinical notes, and follow-up plans (V1.4).

Revision ID: 0008_telehealth_waiting_notes_followup
Revises: 0007_document_processing_jobs
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008_telehealth_waiting_notes_followup"
down_revision: str | None = "0007_document_processing_jobs"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "waiting_room_entries",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(36), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("appointment_id", sa.String(36), sa.ForeignKey("appointments.id", ondelete="CASCADE"), nullable=False),
        sa.Column("session_id", sa.String(36), nullable=True),
        sa.Column("patient_user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("provider_user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("clinic_patient_id", sa.String(36), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="not_checked_in"),
        sa.Column("checked_in_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("admitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("admitted_by_user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("left_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_waiting_room_tenant_appt", "waiting_room_entries", ["tenant_id", "appointment_id"])
    op.create_index("ix_waiting_room_tenant_status", "waiting_room_entries", ["tenant_id", "status"])

    op.create_table(
        "clinical_notes",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(36), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("patient_id", sa.String(36), nullable=False),
        sa.Column("author_user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("session_id", sa.String(36), nullable=True),
        sa.Column("encounter_id", sa.String(36), nullable=True),
        sa.Column("appointment_id", sa.String(36), nullable=True),
        sa.Column("note_type", sa.String(32), nullable=False, server_default="soap"),
        sa.Column("subjective", sa.Text(), nullable=False, server_default=""),
        sa.Column("objective", sa.Text(), nullable=False, server_default=""),
        sa.Column("assessment", sa.Text(), nullable=False, server_default=""),
        sa.Column("plan", sa.Text(), nullable=False, server_default=""),
        sa.Column("status", sa.String(16), nullable=False, server_default="draft"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("ai_assisted", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("source_draft_id", sa.String(36), nullable=True),
        sa.Column("signed_by_user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("signed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_clinical_note_tenant_patient", "clinical_notes", ["tenant_id", "patient_id", "status"])
    op.create_index("ix_clinical_note_tenant_session", "clinical_notes", ["tenant_id", "session_id"])

    op.create_table(
        "clinical_note_versions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(36), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("note_id", sa.String(36), sa.ForeignKey("clinical_notes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("content_snapshot", sa.JSON(), nullable=False),
        sa.Column("editor_user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("change_reason", sa.String(200), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_note_version_note", "clinical_note_versions", ["tenant_id", "note_id", "version"])

    op.create_table(
        "follow_up_plans",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(36), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("patient_id", sa.String(36), nullable=False),
        sa.Column("provider_user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("session_id", sa.String(36), nullable=True),
        sa.Column("encounter_id", sa.String(36), nullable=True),
        sa.Column("appointment_id", sa.String(36), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="draft"),
        sa.Column("instructions", sa.Text(), nullable=False, server_default=""),
        sa.Column("tasks", sa.JSON(), nullable=False),
        sa.Column("approved_by_user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_follow_up_tenant_patient", "follow_up_plans", ["tenant_id", "patient_id", "status"])
    op.create_index("ix_follow_up_tenant_session", "follow_up_plans", ["tenant_id", "session_id"])


def downgrade() -> None:
    op.drop_index("ix_follow_up_tenant_session", table_name="follow_up_plans")
    op.drop_index("ix_follow_up_tenant_patient", table_name="follow_up_plans")
    op.drop_table("follow_up_plans")
    op.drop_index("ix_note_version_note", table_name="clinical_note_versions")
    op.drop_table("clinical_note_versions")
    op.drop_index("ix_clinical_note_tenant_session", table_name="clinical_notes")
    op.drop_index("ix_clinical_note_tenant_patient", table_name="clinical_notes")
    op.drop_table("clinical_notes")
    op.drop_index("ix_waiting_room_tenant_status", table_name="waiting_room_entries")
    op.drop_index("ix_waiting_room_tenant_appt", table_name="waiting_room_entries")
    op.drop_table("waiting_room_entries")
