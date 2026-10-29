"""V2.1.1 advanced agent capabilities, delegation, clinical context evidence.

Revision ID: 0015_ai_advanced_agents_v211
Revises: 0014_ai_orchestration_v20
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0015_ai_advanced_agents_v211"
down_revision: str | None = "0014_ai_orchestration_v20"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ai_agent_capabilities",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("capability_code", sa.String(96), nullable=False),
        sa.Column("capability_version", sa.String(32), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("domain", sa.String(32), nullable=False),
        sa.Column("risk_level", sa.String(16), nullable=False, server_default="medium"),
        sa.Column("status", sa.String(24), nullable=False, server_default="draft"),
        sa.Column("configuration", sa.JSON(), nullable=False),
        sa.Column("requires_human_approval", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("approved_by", sa.String(36), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("capability_code", "capability_version", name="uq_ai_capability_ver"),
    )
    op.create_index("ix_ai_capability_status", "ai_agent_capabilities", ["status", "domain"])

    op.create_table(
        "ai_capability_tool_permissions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "capability_id",
            sa.String(36),
            sa.ForeignKey("ai_agent_capabilities.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "tool_id",
            sa.String(36),
            sa.ForeignKey("ai_agent_tools.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("permission_scope", sa.String(64), nullable=False, server_default="default"),
        sa.Column("approval_required", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("capability_id", "tool_id", name="uq_capability_tool"),
    )

    op.create_table(
        "ai_agent_delegations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "organization_id",
            sa.String(36),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "parent_run_id",
            sa.String(36),
            sa.ForeignKey("ai_agent_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "child_run_id",
            sa.String(36),
            sa.ForeignKey("ai_agent_runs.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "target_capability_id",
            sa.String(36),
            sa.ForeignKey("ai_agent_capabilities.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("requested_by", sa.String(36), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="created"),
        sa.Column("depth", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("permitted_tools", sa.JSON(), nullable=False),
        sa.Column("denial_reason", sa.String(128), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_ai_delegation_parent",
        "ai_agent_delegations",
        ["organization_id", "parent_run_id", "status"],
    )

    op.create_table(
        "ai_clinical_context_access_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("actor_id", sa.String(36), nullable=False),
        sa.Column("patient_id", sa.String(36), nullable=True),
        sa.Column("encounter_id", sa.String(36), nullable=True),
        sa.Column("agent_run_id", sa.String(36), nullable=True),
        sa.Column("resource_category", sa.String(64), nullable=False),
        sa.Column("access_outcome", sa.String(24), nullable=False),
        sa.Column("policy_reference", sa.String(64), nullable=False, server_default="2.1.1"),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_ai_ctx_access",
        "ai_clinical_context_access_events",
        ["organization_id", "patient_id", "occurred_at"],
    )

    op.create_table(
        "ai_evidence_references",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("agent_run_id", sa.String(36), nullable=True),
        sa.Column("patient_id", sa.String(36), nullable=True),
        sa.Column("source_type", sa.String(64), nullable=False),
        sa.Column("source_resource_id", sa.String(64), nullable=False),
        sa.Column("source_version", sa.String(32), nullable=False, server_default="1"),
        sa.Column("source_location", sa.String(256), nullable=False, server_default=""),
        sa.Column("verification_status", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_ai_evidence_run",
        "ai_evidence_references",
        ["organization_id", "agent_run_id"],
    )

    op.create_table(
        "ai_execution_context_records",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("agent_run_id", sa.String(36), nullable=True),
        sa.Column("actor_id", sa.String(36), nullable=False),
        sa.Column("patient_id", sa.String(36), nullable=True),
        sa.Column("encounter_id", sa.String(36), nullable=True),
        sa.Column("capability_code", sa.String(96), nullable=False, server_default=""),
        sa.Column("capability_version", sa.String(32), nullable=False, server_default=""),
        sa.Column("authorization_reference", sa.String(64), nullable=False),
        sa.Column("policy_version", sa.String(16), nullable=False, server_default="2.1.1"),
        sa.Column("correlation_id", sa.String(64), nullable=False, server_default=""),
        sa.Column("context_reference", sa.String(128), nullable=False, server_default=""),
        sa.Column("status", sa.String(24), nullable=False, server_default="active"),
        sa.Column("permitted_tools", sa.JSON(), nullable=False),
        sa.Column("expiration_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_ai_exec_ctx",
        "ai_execution_context_records",
        ["organization_id", "agent_run_id", "status"],
    )


def downgrade() -> None:
    op.drop_table("ai_execution_context_records")
    op.drop_table("ai_evidence_references")
    op.drop_table("ai_clinical_context_access_events")
    op.drop_table("ai_agent_delegations")
    op.drop_table("ai_capability_tool_permissions")
    op.drop_table("ai_agent_capabilities")
