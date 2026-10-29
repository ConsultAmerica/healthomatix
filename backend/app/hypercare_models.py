"""V1.9 hypercare, onboarding, customer success, compliance, and automation models."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.db import Base
from app.models import new_id, utcnow


class OperationalIncident(Base):
    __tablename__ = "operational_incidents"
    __table_args__ = (Index("ix_ops_incident_status", "status", "severity", "detected_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    environment: Mapped[str] = mapped_column(String(32), nullable=False)
    organization_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    incident_number: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    category: Mapped[str] = mapped_column(String(64), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="open", nullable=False)
    affected_service: Mapped[str] = mapped_column(String(64), nullable=False)
    assigned_owner_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    impact_summary: Mapped[str] = mapped_column(Text, default="", nullable=False)
    mitigation: Mapped[str] = mapped_column(Text, default="", nullable=False)
    resolution: Mapped[str] = mapped_column(Text, default="", nullable=False)
    root_cause: Mapped[str] = mapped_column(Text, default="", nullable=False)
    corrective_actions: Mapped[str] = mapped_column(Text, default="", nullable=False)
    detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )


class OperationalIncidentEvent(Base):
    __tablename__ = "operational_incident_events"
    __table_args__ = (Index("ix_ops_incident_event", "incident_id", "occurred_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    incident_id: Mapped[str] = mapped_column(
        ForeignKey("operational_incidents.id", ondelete="CASCADE"), nullable=False
    )
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    actor_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    event_summary: Mapped[str] = mapped_column(Text, default="", nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )


class CustomerOnboardingWorkflow(Base):
    __tablename__ = "customer_onboarding_workflows"
    __table_args__ = (
        UniqueConstraint("organization_id", name="uq_onboarding_org"),
        Index("ix_onboarding_status", "status", "started_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    workflow_version: Mapped[str] = mapped_column(String(16), default="1.0", nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="not_started", nullable=False)
    assigned_owner_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )


class CustomerOnboardingTask(Base):
    __tablename__ = "customer_onboarding_tasks"
    __table_args__ = (
        UniqueConstraint("workflow_id", "task_code", name="uq_onboarding_task"),
        Index("ix_onboarding_task_status", "organization_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    workflow_id: Mapped[str] = mapped_column(
        ForeignKey("customer_onboarding_workflows.id", ondelete="CASCADE"), nullable=False
    )
    task_code: Mapped[str] = mapped_column(String(64), nullable=False)
    task_name: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="pending", nullable=False)
    assigned_to: Mapped[str | None] = mapped_column(String(36), nullable=True)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class CustomerSuccessProfile(Base):
    __tablename__ = "customer_success_profiles"
    __table_args__ = (UniqueConstraint("organization_id", name="uq_cs_profile_org"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    assigned_owner_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    lifecycle_stage: Mapped[str] = mapped_column(String(32), default="onboarding", nullable=False)
    health_score: Mapped[int] = mapped_column(Integer, default=50, nullable=False)
    health_score_version: Mapped[str] = mapped_column(String(16), default="v1", nullable=False)
    health_factors: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    last_reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )


class CustomerSuccessTask(Base):
    __tablename__ = "customer_success_tasks"
    __table_args__ = (Index("ix_cs_task_org", "organization_id", "status", "due_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    task_type: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="open", nullable=False)
    assigned_to: Mapped[str | None] = mapped_column(String(36), nullable=True)
    notes: Mapped[str] = mapped_column(Text, default="", nullable=False)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )


class SupportTicketEvent(Base):
    __tablename__ = "support_ticket_events"
    __table_args__ = (Index("ix_ticket_event", "ticket_id", "created_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    ticket_id: Mapped[str] = mapped_column(
        ForeignKey("support_tickets.id", ondelete="CASCADE"), nullable=False
    )
    actor_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    summary: Mapped[str] = mapped_column(Text, default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )


class KnowledgeArticle(Base):
    __tablename__ = "knowledge_articles"
    __table_args__ = (Index("ix_kb_visibility", "visibility", "status"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    slug: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    category: Mapped[str] = mapped_column(String(64), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    # clinic | platform | public
    visibility: Mapped[str] = mapped_column(String(24), default="clinic", nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="published", nullable=False)
    version: Mapped[str] = mapped_column(String(16), default="1", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )


class ProductUsageEvent(Base):
    __tablename__ = "product_usage_events"
    __table_args__ = (
        UniqueConstraint("organization_id", "event_id", name="uq_product_usage_event"),
        Index("ix_product_usage", "organization_id", "feature_code", "event_timestamp"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    actor_reference: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    feature_code: Mapped[str] = mapped_column(String(64), nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    event_timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    event_id: Mapped[str] = mapped_column(String(128), nullable=False)


class AiOperationalMetric(Base):
    __tablename__ = "ai_operational_metrics"
    __table_args__ = (Index("ix_ai_ops_org", "organization_id", "capability", "occurred_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    capability: Mapped[str] = mapped_column(String(64), nullable=False)
    model_identifier: Mapped[str] = mapped_column(String(120), default="fake", nullable=False)
    request_reference: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    processing_status: Mapped[str] = mapped_column(String(24), nullable=False)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    usage_quantity: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    estimated_cost_cents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )


class AiEvaluationRun(Base):
    __tablename__ = "ai_evaluation_runs"
    __table_args__ = (Index("ix_ai_eval_cap", "capability", "created_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    capability: Mapped[str] = mapped_column(String(64), nullable=False)
    model_identifier: Mapped[str] = mapped_column(String(120), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(32), nullable=False)
    dataset_version: Mapped[str] = mapped_column(String(32), nullable=False)
    evaluation_status: Mapped[str] = mapped_column(String(24), default="draft", nullable=False)
    results: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    reviewed_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )


class ComplianceControlReview(Base):
    __tablename__ = "compliance_control_reviews"
    __table_args__ = (Index("ix_compliance_review", "control_code", "review_status", "due_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    control_code: Mapped[str] = mapped_column(String(64), nullable=False)
    organization_scope: Mapped[str] = mapped_column(String(64), default="platform", nullable=False)
    assigned_owner_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    review_status: Mapped[str] = mapped_column(String(24), default="open", nullable=False)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    notes: Mapped[str] = mapped_column(Text, default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )


class ComplianceEvidenceRegistry(Base):
    __tablename__ = "compliance_evidence_registry"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    control_review_id: Mapped[str] = mapped_column(
        ForeignKey("compliance_control_reviews.id", ondelete="CASCADE"), nullable=False
    )
    evidence_type: Mapped[str] = mapped_column(String(64), nullable=False)
    secure_artifact_reference: Mapped[str] = mapped_column(String(256), nullable=False)
    review_status: Mapped[str] = mapped_column(String(24), default="recorded", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )


class OperationalAutomationRule(Base):
    __tablename__ = "operational_automation_rules"
    __table_args__ = (UniqueConstraint("rule_code", name="uq_automation_rule_code"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    rule_code: Mapped[str] = mapped_column(String(64), nullable=False)
    trigger_type: Mapped[str] = mapped_column(String(64), nullable=False)
    action_type: Mapped[str] = mapped_column(String(64), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    approval_required: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )


class OperationalAutomationRun(Base):
    __tablename__ = "operational_automation_runs"
    __table_args__ = (
        UniqueConstraint("rule_id", "source_event_id", name="uq_automation_run_source"),
        Index("ix_automation_run_status", "status", "executed_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    rule_id: Mapped[str] = mapped_column(
        ForeignKey("operational_automation_rules.id", ondelete="CASCADE"), nullable=False
    )
    source_event_id: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="queued", nullable=False)
    executed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_summary: Mapped[str] = mapped_column(Text, default="", nullable=False)
    result_summary: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)


class ContinuousImprovementItem(Base):
    __tablename__ = "continuous_improvement_items"
    __table_args__ = (Index("ix_ci_status", "status", "priority"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    source_type: Mapped[str] = mapped_column(String(64), nullable=False)
    source_reference: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    priority: Mapped[str] = mapped_column(String(16), default="normal", nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="identified", nullable=False)
    owner_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    release_assignment: Mapped[str] = mapped_column(String(32), default="", nullable=False)
    baseline_metric: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    outcome_metric: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
