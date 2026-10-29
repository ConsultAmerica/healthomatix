"""Hypercare, onboarding, customer success, compliance, automation (V1.9).

Revision ID: 0013_hypercare_ops_v19
Revises: 0012_ops_security_v18
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0013_hypercare_ops_v19"
down_revision: str | None = "0012_ops_security_v18"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "support_tickets",
        sa.Column("ticket_number", sa.String(32), nullable=False, server_default=""),
    )
    op.add_column(
        "support_tickets",
        sa.Column("assigned_team", sa.String(64), nullable=False, server_default=""),
    )

    op.create_table(
        "operational_incidents",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("environment", sa.String(32), nullable=False),
        sa.Column("organization_id", sa.String(36), nullable=True),
        sa.Column("incident_number", sa.String(32), nullable=False, unique=True),
        sa.Column("category", sa.String(64), nullable=False),
        sa.Column("severity", sa.String(16), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="open"),
        sa.Column("affected_service", sa.String(64), nullable=False),
        sa.Column("assigned_owner_id", sa.String(36), nullable=True),
        sa.Column("impact_summary", sa.Text(), nullable=False, server_default=""),
        sa.Column("mitigation", sa.Text(), nullable=False, server_default=""),
        sa.Column("resolution", sa.Text(), nullable=False, server_default=""),
        sa.Column("root_cause", sa.Text(), nullable=False, server_default=""),
        sa.Column("corrective_actions", sa.Text(), nullable=False, server_default=""),
        sa.Column("detected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_ops_incident_status",
        "operational_incidents",
        ["status", "severity", "detected_at"],
    )

    op.create_table(
        "operational_incident_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "incident_id",
            sa.String(36),
            sa.ForeignKey("operational_incidents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("actor_id", sa.String(36), nullable=True),
        sa.Column("event_summary", sa.Text(), nullable=False, server_default=""),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_ops_incident_event", "operational_incident_events", ["incident_id", "occurred_at"]
    )

    op.create_table(
        "customer_onboarding_workflows",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("workflow_version", sa.String(16), nullable=False, server_default="1.0"),
        sa.Column("status", sa.String(32), nullable=False, server_default="not_started"),
        sa.Column("assigned_owner_id", sa.String(36), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("organization_id", name="uq_onboarding_org"),
    )
    op.create_index("ix_onboarding_status", "customer_onboarding_workflows", ["status", "started_at"])

    op.create_table(
        "customer_onboarding_tasks",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "workflow_id",
            sa.String(36),
            sa.ForeignKey("customer_onboarding_workflows.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("task_code", sa.String(64), nullable=False),
        sa.Column("task_name", sa.String(200), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="pending"),
        sa.Column("assigned_to", sa.String(36), nullable=True),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("workflow_id", "task_code", name="uq_onboarding_task"),
    )
    op.create_index(
        "ix_onboarding_task_status", "customer_onboarding_tasks", ["organization_id", "status"]
    )

    op.create_table(
        "customer_success_profiles",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("assigned_owner_id", sa.String(36), nullable=True),
        sa.Column("lifecycle_stage", sa.String(32), nullable=False, server_default="onboarding"),
        sa.Column("health_score", sa.Integer(), nullable=False, server_default="50"),
        sa.Column("health_score_version", sa.String(16), nullable=False, server_default="v1"),
        sa.Column("health_factors", sa.JSON(), nullable=False),
        sa.Column("last_reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("organization_id", name="uq_cs_profile_org"),
    )

    op.create_table(
        "customer_success_tasks",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("task_type", sa.String(64), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="open"),
        sa.Column("assigned_to", sa.String(36), nullable=True),
        sa.Column("notes", sa.Text(), nullable=False, server_default=""),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_cs_task_org", "customer_success_tasks", ["organization_id", "status", "due_at"]
    )

    op.create_table(
        "support_ticket_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "ticket_id",
            sa.String(36),
            sa.ForeignKey("support_tickets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("actor_id", sa.String(36), nullable=True),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_ticket_event", "support_ticket_events", ["ticket_id", "created_at"])

    op.create_table(
        "knowledge_articles",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("slug", sa.String(120), nullable=False, unique=True),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("category", sa.String(64), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("visibility", sa.String(24), nullable=False, server_default="clinic"),
        sa.Column("status", sa.String(16), nullable=False, server_default="published"),
        sa.Column("version", sa.String(16), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_kb_visibility", "knowledge_articles", ["visibility", "status"])

    op.create_table(
        "product_usage_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("actor_reference", sa.String(64), nullable=False, server_default=""),
        sa.Column("feature_code", sa.String(64), nullable=False),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("event_timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("event_id", sa.String(128), nullable=False),
        sa.UniqueConstraint("organization_id", "event_id", name="uq_product_usage_event"),
    )
    op.create_index(
        "ix_product_usage",
        "product_usage_events",
        ["organization_id", "feature_code", "event_timestamp"],
    )

    op.create_table(
        "ai_operational_metrics",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), nullable=True),
        sa.Column("capability", sa.String(64), nullable=False),
        sa.Column("model_identifier", sa.String(120), nullable=False, server_default="fake"),
        sa.Column("request_reference", sa.String(128), nullable=False, server_default=""),
        sa.Column("processing_status", sa.String(24), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("usage_quantity", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("estimated_cost_cents", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_ai_ops_org",
        "ai_operational_metrics",
        ["organization_id", "capability", "occurred_at"],
    )

    op.create_table(
        "ai_evaluation_runs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("capability", sa.String(64), nullable=False),
        sa.Column("model_identifier", sa.String(120), nullable=False),
        sa.Column("prompt_version", sa.String(32), nullable=False),
        sa.Column("dataset_version", sa.String(32), nullable=False),
        sa.Column("evaluation_status", sa.String(24), nullable=False, server_default="draft"),
        sa.Column("results", sa.JSON(), nullable=False),
        sa.Column("reviewed_by", sa.String(36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_ai_eval_cap", "ai_evaluation_runs", ["capability", "created_at"])

    op.create_table(
        "compliance_control_reviews",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("control_code", sa.String(64), nullable=False),
        sa.Column("organization_scope", sa.String(64), nullable=False, server_default="platform"),
        sa.Column("assigned_owner_id", sa.String(36), nullable=True),
        sa.Column("review_status", sa.String(24), nullable=False, server_default="open"),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_compliance_review",
        "compliance_control_reviews",
        ["control_code", "review_status", "due_at"],
    )

    op.create_table(
        "compliance_evidence_registry",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "control_review_id",
            sa.String(36),
            sa.ForeignKey("compliance_control_reviews.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("evidence_type", sa.String(64), nullable=False),
        sa.Column("secure_artifact_reference", sa.String(256), nullable=False),
        sa.Column("review_status", sa.String(24), nullable=False, server_default="recorded"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "operational_automation_rules",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), nullable=True),
        sa.Column("rule_code", sa.String(64), nullable=False),
        sa.Column("trigger_type", sa.String(64), nullable=False),
        sa.Column("action_type", sa.String(64), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("approval_required", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("rule_code", name="uq_automation_rule_code"),
    )

    op.create_table(
        "operational_automation_runs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "rule_id",
            sa.String(36),
            sa.ForeignKey("operational_automation_rules.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("source_event_id", sa.String(128), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="queued"),
        sa.Column("executed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_summary", sa.Text(), nullable=False, server_default=""),
        sa.Column("result_summary", sa.JSON(), nullable=False),
        sa.UniqueConstraint("rule_id", "source_event_id", name="uq_automation_run_source"),
    )
    op.create_index(
        "ix_automation_run_status", "operational_automation_runs", ["status", "executed_at"]
    )

    op.create_table(
        "continuous_improvement_items",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("source_type", sa.String(64), nullable=False),
        sa.Column("source_reference", sa.String(128), nullable=False, server_default=""),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("priority", sa.String(16), nullable=False, server_default="normal"),
        sa.Column("status", sa.String(24), nullable=False, server_default="identified"),
        sa.Column("owner_id", sa.String(36), nullable=True),
        sa.Column("release_assignment", sa.String(32), nullable=False, server_default=""),
        sa.Column("baseline_metric", sa.String(128), nullable=False, server_default=""),
        sa.Column("outcome_metric", sa.String(128), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_ci_status", "continuous_improvement_items", ["status", "priority"])


def downgrade() -> None:
    op.drop_index("ix_ci_status", table_name="continuous_improvement_items")
    op.drop_table("continuous_improvement_items")
    op.drop_index("ix_automation_run_status", table_name="operational_automation_runs")
    op.drop_table("operational_automation_runs")
    op.drop_table("operational_automation_rules")
    op.drop_table("compliance_evidence_registry")
    op.drop_index("ix_compliance_review", table_name="compliance_control_reviews")
    op.drop_table("compliance_control_reviews")
    op.drop_index("ix_ai_eval_cap", table_name="ai_evaluation_runs")
    op.drop_table("ai_evaluation_runs")
    op.drop_index("ix_ai_ops_org", table_name="ai_operational_metrics")
    op.drop_table("ai_operational_metrics")
    op.drop_index("ix_product_usage", table_name="product_usage_events")
    op.drop_table("product_usage_events")
    op.drop_index("ix_kb_visibility", table_name="knowledge_articles")
    op.drop_table("knowledge_articles")
    op.drop_index("ix_ticket_event", table_name="support_ticket_events")
    op.drop_table("support_ticket_events")
    op.drop_index("ix_cs_task_org", table_name="customer_success_tasks")
    op.drop_table("customer_success_tasks")
    op.drop_table("customer_success_profiles")
    op.drop_index("ix_onboarding_task_status", table_name="customer_onboarding_tasks")
    op.drop_table("customer_onboarding_tasks")
    op.drop_index("ix_onboarding_status", table_name="customer_onboarding_workflows")
    op.drop_table("customer_onboarding_workflows")
    op.drop_index("ix_ops_incident_event", table_name="operational_incident_events")
    op.drop_table("operational_incident_events")
    op.drop_index("ix_ops_incident_status", table_name="operational_incidents")
    op.drop_table("operational_incidents")
    op.drop_column("support_tickets", "assigned_team")
    op.drop_column("support_tickets", "ticket_number")
