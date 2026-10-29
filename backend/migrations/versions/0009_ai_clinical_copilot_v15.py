"""AI clinical copilot tables (V1.5).

Revision ID: 0009_ai_clinical_copilot_v15
Revises: 0008_telehealth_waiting_notes_followup
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009_ai_clinical_copilot_v15"
down_revision: str | None = "0008_telehealth_waiting_notes_followup"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ai_generations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(36), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("patient_id", sa.String(36), nullable=True),
        sa.Column("encounter_id", sa.String(36), nullable=True),
        sa.Column("session_id", sa.String(36), nullable=True),
        sa.Column("module", sa.String(32), nullable=False),
        sa.Column("model_identifier", sa.String(64), nullable=False),
        sa.Column("prompt_version", sa.String(32), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="generated"),
        sa.Column("source_references", sa.JSON(), nullable=False),
        sa.Column("output_reference", sa.String(64), nullable=True),
        sa.Column("usage_metadata", sa.JSON(), nullable=False),
        sa.Column("created_by_user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("reviewed_by_user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_ai_gen_tenant_module", "ai_generations", ["tenant_id", "module", "created_at"])
    op.create_index("ix_ai_gen_tenant_patient", "ai_generations", ["tenant_id", "patient_id"])

    op.create_table(
        "ai_scribe_sessions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(36), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("patient_id", sa.String(36), nullable=False),
        sa.Column("provider_user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("appointment_id", sa.String(36), nullable=True),
        sa.Column("session_id", sa.String(36), nullable=True),
        sa.Column("encounter_id", sa.String(36), nullable=True),
        sa.Column("consent_grant_id", sa.String(36), nullable=True),
        sa.Column("mode", sa.String(16), nullable=False, server_default="manual"),
        sa.Column("speech_provider", sa.String(32), nullable=False, server_default="fake"),
        sa.Column("status", sa.String(16), nullable=False, server_default="created"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("stopped_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_scribe_tenant_status", "ai_scribe_sessions", ["tenant_id", "status"])

    op.create_table(
        "transcript_segments",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(36), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "scribe_session_id",
            sa.String(36),
            sa.ForeignKey("ai_scribe_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("speaker_label", sa.String(32), nullable=False, server_default="unknown"),
        sa.Column("start_offset_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("end_offset_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("transcript_text", sa.Text(), nullable=False),
        sa.Column("confidence_metadata", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_transcript_scribe", "transcript_segments", ["tenant_id", "scribe_session_id"])

    op.create_table(
        "clinical_note_quality_findings",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(36), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "clinical_note_id",
            sa.String(36),
            sa.ForeignKey("clinical_notes.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("note_version", sa.Integer(), nullable=False),
        sa.Column("finding_type", sa.String(64), nullable=False),
        sa.Column("severity", sa.String(32), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("source_reference", sa.String(200), nullable=False, server_default=""),
        sa.Column("suggested_action", sa.Text(), nullable=False, server_default=""),
        sa.Column("review_status", sa.String(16), nullable=False, server_default="open"),
        sa.Column("reviewed_by_user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("dismiss_reason", sa.String(200), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_note_quality_note", "clinical_note_quality_findings", ["tenant_id", "clinical_note_id"]
    )

    op.create_table(
        "ai_message_drafts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(36), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "thread_id",
            sa.String(36),
            sa.ForeignKey("message_threads.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("source_message_id", sa.String(36), nullable=True),
        sa.Column("category", sa.String(64), nullable=False, server_default="other"),
        sa.Column("generated_content", sa.Text(), nullable=False),
        sa.Column("edited_content", sa.Text(), nullable=False, server_default=""),
        sa.Column("status", sa.String(16), nullable=False, server_default="generated"),
        sa.Column("ai_generation_id", sa.String(36), nullable=True),
        sa.Column("reviewer_user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sent_message_id", sa.String(36), nullable=True),
        sa.Column("idempotency_key", sa.String(128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_ai_msg_draft_thread", "ai_message_drafts", ["tenant_id", "thread_id", "status"])

    op.create_table(
        "patient_education_sessions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(36), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("patient_id", sa.String(36), nullable=False),
        sa.Column("topic", sa.String(200), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("answer", sa.Text(), nullable=False),
        sa.Column("source_references", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="answered"),
        sa.Column("escalated", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("ai_generation_id", sa.String(36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_edu_tenant_patient", "patient_education_sessions", ["tenant_id", "patient_id"])

    op.create_table(
        "care_coordination_tasks",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(36), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("patient_id", sa.String(36), nullable=False),
        sa.Column(
            "follow_up_plan_id",
            sa.String(36),
            sa.ForeignKey("follow_up_plans.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("encounter_id", sa.String(36), nullable=True),
        sa.Column("task_category", sa.String(64), nullable=False, server_default="follow_up"),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("assigned_role", sa.String(32), nullable=False, server_default="patient"),
        sa.Column("assigned_user_id", sa.String(36), nullable=True),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(24), nullable=False, server_default="open"),
        sa.Column("approval_reference", sa.String(64), nullable=False, server_default=""),
        sa.Column("idempotency_key", sa.String(128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_care_task_plan", "care_coordination_tasks", ["tenant_id", "follow_up_plan_id", "status"]
    )
    op.create_index(
        "ix_care_task_patient", "care_coordination_tasks", ["tenant_id", "patient_id", "status"]
    )

    op.create_table(
        "workflow_automation_executions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(36), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("automation_type", sa.String(64), nullable=False),
        sa.Column("trigger_event_id", sa.String(64), nullable=False, server_default=""),
        sa.Column("target_entity_type", sa.String(64), nullable=False),
        sa.Column("target_entity_id", sa.String(36), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="completed"),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("error_code", sa.String(64), nullable=False, server_default=""),
        sa.Column("executed_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_auto_exec_tenant",
        "workflow_automation_executions",
        ["tenant_id", "automation_type", "executed_at"],
    )


def downgrade() -> None:
    op.drop_table("workflow_automation_executions")
    op.drop_table("care_coordination_tasks")
    op.drop_table("patient_education_sessions")
    op.drop_table("ai_message_drafts")
    op.drop_table("clinical_note_quality_findings")
    op.drop_table("transcript_segments")
    op.drop_table("ai_scribe_sessions")
    op.drop_table("ai_generations")
