"""AI agent orchestration, tools, approvals (V2.0).

Revision ID: 0014_ai_orchestration_v20
Revises: 0013_hypercare_ops_v19
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0014_ai_orchestration_v20"
down_revision: str | None = "0013_hypercare_ops_v19"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ai_agent_definitions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("agent_code", sa.String(64), nullable=False),
        sa.Column("agent_name", sa.String(120), nullable=False),
        sa.Column("domain", sa.String(32), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("risk_level", sa.String(16), nullable=False, server_default="medium"),
        sa.Column("current_version", sa.String(32), nullable=False, server_default="1.0.0"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("agent_code", name="uq_ai_agent_code"),
    )
    op.create_table(
        "ai_agent_versions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("agent_id", sa.String(36), sa.ForeignKey("ai_agent_definitions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version", sa.String(32), nullable=False),
        sa.Column("model_identifier", sa.String(120), nullable=False, server_default="fake"),
        sa.Column("prompt_version", sa.String(32), nullable=False),
        sa.Column("configuration", sa.JSON(), nullable=False),
        sa.Column("evaluation_status", sa.String(24), nullable=False, server_default="draft"),
        sa.Column("approved_by", sa.String(36), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("agent_id", "version", name="uq_ai_agent_version"),
    )
    op.create_table(
        "ai_agent_tools",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tool_code", sa.String(96), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("risk_level", sa.String(16), nullable=False, server_default="medium"),
        sa.Column("required_permission", sa.String(64), nullable=False),
        sa.Column("approval_required", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.UniqueConstraint("tool_code", name="uq_ai_tool_code"),
    )
    op.create_table(
        "ai_agent_runs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("agent_id", sa.String(36), sa.ForeignKey("ai_agent_definitions.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("agent_version_id", sa.String(36), sa.ForeignKey("ai_agent_versions.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("requested_by", sa.String(36), nullable=False),
        sa.Column("workflow_type", sa.String(64), nullable=False, server_default=""),
        sa.Column("status", sa.String(24), nullable=False, server_default="created"),
        sa.Column("correlation_id", sa.String(64), nullable=False, server_default=""),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("patient_id", sa.String(36), nullable=True),
        sa.Column("input_summary", sa.JSON(), nullable=False),
        sa.Column("output_summary", sa.JSON(), nullable=False),
        sa.Column("error_code", sa.String(64), nullable=False, server_default=""),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("organization_id", "idempotency_key", name="uq_agent_run_idem"),
    )
    op.create_index("ix_agent_run_tenant_status", "ai_agent_runs", ["organization_id", "status", "started_at"])
    op.create_table(
        "ai_agent_run_steps",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("agent_run_id", sa.String(36), sa.ForeignKey("ai_agent_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("step_number", sa.Integer(), nullable=False),
        sa.Column("step_type", sa.String(64), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="created"),
        sa.Column("output_reference", sa.String(256), nullable=False, server_default=""),
        sa.Column("detail", sa.JSON(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_agent_step_run", "ai_agent_run_steps", ["agent_run_id", "step_number"])
    op.create_table(
        "ai_agent_tool_executions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("agent_run_id", sa.String(36), sa.ForeignKey("ai_agent_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("tool_id", sa.String(36), sa.ForeignKey("ai_agent_tools.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("actor_id", sa.String(36), nullable=False),
        sa.Column("target_resource_reference", sa.String(128), nullable=False, server_default=""),
        sa.Column("status", sa.String(24), nullable=False, server_default="proposed"),
        sa.Column("approval_id", sa.String(36), nullable=True),
        sa.Column("result_summary", sa.JSON(), nullable=False),
        sa.Column("executed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_tool_exec_run", "ai_agent_tool_executions", ["agent_run_id", "executed_at"])
    op.create_table(
        "ai_agent_approvals",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("agent_run_id", sa.String(36), sa.ForeignKey("ai_agent_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("proposal_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("proposal_hash", sa.String(64), nullable=False),
        sa.Column("proposal_payload", sa.JSON(), nullable=False),
        sa.Column("required_role", sa.String(32), nullable=False),
        sa.Column("approver_id", sa.String(36), nullable=True),
        sa.Column("status", sa.String(24), nullable=False, server_default="pending"),
        sa.Column("decision_reason", sa.Text(), nullable=False, server_default=""),
        sa.Column("execution_token", sa.String(64), nullable=False, server_default=""),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_agent_approval_status", "ai_agent_approvals", ["organization_id", "status", "created_at"])
    op.create_table(
        "ai_agent_evaluations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("agent_version_id", sa.String(36), sa.ForeignKey("ai_agent_versions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("dataset_version", sa.String(32), nullable=False),
        sa.Column("evaluation_type", sa.String(64), nullable=False),
        sa.Column("results", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="pending_review"),
        sa.Column("reviewed_by", sa.String(36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_agent_eval_version", "ai_agent_evaluations", ["agent_version_id", "created_at"])
    op.create_table(
        "ai_agent_usage",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("agent_id", sa.String(36), nullable=False),
        sa.Column("agent_run_id", sa.String(36), nullable=False),
        sa.Column("model_identifier", sa.String(120), nullable=False, server_default="fake"),
        sa.Column("input_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("output_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("estimated_cost_cents", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_agent_usage_org", "ai_agent_usage", ["organization_id", "occurred_at"])
    op.create_table(
        "ai_agent_safety_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), nullable=True),
        sa.Column("agent_run_id", sa.String(36), nullable=True),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("severity", sa.String(16), nullable=False, server_default="medium"),
        sa.Column("status", sa.String(24), nullable=False, server_default="open"),
        sa.Column("summary", sa.Text(), nullable=False, server_default=""),
        sa.Column("assigned_owner_id", sa.String(36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_agent_safety", "ai_agent_safety_events", ["organization_id", "status", "created_at"])
    op.create_table(
        "ai_workflow_definitions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("workflow_code", sa.String(64), nullable=False),
        sa.Column("version", sa.String(32), nullable=False),
        sa.Column("risk_level", sa.String(16), nullable=False, server_default="medium"),
        sa.Column("configuration", sa.JSON(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.UniqueConstraint("workflow_code", "version", name="uq_ai_workflow_ver"),
    )
    op.create_table(
        "ai_workflow_executions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("workflow_definition_id", sa.String(36), sa.ForeignKey("ai_workflow_definitions.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("requested_by", sa.String(36), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="created"),
        sa.Column("correlation_id", sa.String(64), nullable=False, server_default=""),
        sa.Column("agent_run_ids", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_ai_workflow_exec", "ai_workflow_executions", ["organization_id", "status", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_ai_workflow_exec", table_name="ai_workflow_executions")
    op.drop_table("ai_workflow_executions")
    op.drop_table("ai_workflow_definitions")
    op.drop_index("ix_agent_safety", table_name="ai_agent_safety_events")
    op.drop_table("ai_agent_safety_events")
    op.drop_index("ix_agent_usage_org", table_name="ai_agent_usage")
    op.drop_table("ai_agent_usage")
    op.drop_index("ix_agent_eval_version", table_name="ai_agent_evaluations")
    op.drop_table("ai_agent_evaluations")
    op.drop_index("ix_agent_approval_status", table_name="ai_agent_approvals")
    op.drop_table("ai_agent_approvals")
    op.drop_index("ix_tool_exec_run", table_name="ai_agent_tool_executions")
    op.drop_table("ai_agent_tool_executions")
    op.drop_index("ix_agent_step_run", table_name="ai_agent_run_steps")
    op.drop_table("ai_agent_run_steps")
    op.drop_index("ix_agent_run_tenant_status", table_name="ai_agent_runs")
    op.drop_table("ai_agent_runs")
    op.drop_table("ai_agent_tools")
    op.drop_table("ai_agent_versions")
    op.drop_table("ai_agent_definitions")
