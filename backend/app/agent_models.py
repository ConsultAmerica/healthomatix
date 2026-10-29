"""V2.0 AI agent registry, runs, tools, approvals, and safety events."""

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


class AiAgentDefinition(Base):
    __tablename__ = "ai_agent_definitions"
    __table_args__ = (UniqueConstraint("agent_code", name="uq_ai_agent_code"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    agent_code: Mapped[str] = mapped_column(String(64), nullable=False)
    agent_name: Mapped[str] = mapped_column(String(120), nullable=False)
    domain: Mapped[str] = mapped_column(String(32), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    risk_level: Mapped[str] = mapped_column(String(16), default="medium", nullable=False)
    current_version: Mapped[str] = mapped_column(String(32), default="1.0.0", nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )


class AiAgentVersion(Base):
    __tablename__ = "ai_agent_versions"
    __table_args__ = (
        UniqueConstraint("agent_id", "version", name="uq_ai_agent_version"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    agent_id: Mapped[str] = mapped_column(
        ForeignKey("ai_agent_definitions.id", ondelete="CASCADE"), nullable=False
    )
    version: Mapped[str] = mapped_column(String(32), nullable=False)
    model_identifier: Mapped[str] = mapped_column(String(120), default="fake", nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(32), nullable=False)
    configuration: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    evaluation_status: Mapped[str] = mapped_column(String(24), default="draft", nullable=False)
    approved_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )


class AiAgentTool(Base):
    __tablename__ = "ai_agent_tools"
    __table_args__ = (UniqueConstraint("tool_code", name="uq_ai_tool_code"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    tool_code: Mapped[str] = mapped_column(String(96), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    risk_level: Mapped[str] = mapped_column(String(16), default="medium", nullable=False)
    required_permission: Mapped[str] = mapped_column(String(64), nullable=False)
    approval_required: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class AiAgentRun(Base):
    __tablename__ = "ai_agent_runs"
    __table_args__ = (
        Index("ix_agent_run_tenant_status", "organization_id", "status", "started_at"),
        UniqueConstraint("organization_id", "idempotency_key", name="uq_agent_run_idem"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    agent_id: Mapped[str] = mapped_column(
        ForeignKey("ai_agent_definitions.id", ondelete="RESTRICT"), nullable=False
    )
    agent_version_id: Mapped[str] = mapped_column(
        ForeignKey("ai_agent_versions.id", ondelete="RESTRICT"), nullable=False
    )
    requested_by: Mapped[str] = mapped_column(String(36), nullable=False)
    workflow_type: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    # created | queued | running | waiting_approval | waiting_external | completed | failed | cancelled | timed_out | rejected
    status: Mapped[str] = mapped_column(String(24), default="created", nullable=False)
    correlation_id: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    patient_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    input_summary: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    output_summary: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    error_code: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )


class AiAgentRunStep(Base):
    __tablename__ = "ai_agent_run_steps"
    __table_args__ = (Index("ix_agent_step_run", "agent_run_id", "step_number"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    agent_run_id: Mapped[str] = mapped_column(
        ForeignKey("ai_agent_runs.id", ondelete="CASCADE"), nullable=False
    )
    step_number: Mapped[int] = mapped_column(Integer, nullable=False)
    step_type: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="created", nullable=False)
    output_reference: Mapped[str] = mapped_column(String(256), default="", nullable=False)
    detail: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AiAgentToolExecution(Base):
    __tablename__ = "ai_agent_tool_executions"
    __table_args__ = (Index("ix_tool_exec_run", "agent_run_id", "executed_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(String(36), nullable=False)
    agent_run_id: Mapped[str] = mapped_column(
        ForeignKey("ai_agent_runs.id", ondelete="CASCADE"), nullable=False
    )
    tool_id: Mapped[str] = mapped_column(
        ForeignKey("ai_agent_tools.id", ondelete="RESTRICT"), nullable=False
    )
    actor_id: Mapped[str] = mapped_column(String(36), nullable=False)
    target_resource_reference: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="proposed", nullable=False)
    approval_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    result_summary: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    executed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AiAgentApproval(Base):
    __tablename__ = "ai_agent_approvals"
    __table_args__ = (Index("ix_agent_approval_status", "organization_id", "status", "created_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(String(36), nullable=False)
    agent_run_id: Mapped[str] = mapped_column(
        ForeignKey("ai_agent_runs.id", ondelete="CASCADE"), nullable=False
    )
    proposal_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    proposal_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    proposal_payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    required_role: Mapped[str] = mapped_column(String(32), nullable=False)
    approver_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    # pending | approved | rejected | expired | executed | failed
    status: Mapped[str] = mapped_column(String(24), default="pending", nullable=False)
    decision_reason: Mapped[str] = mapped_column(Text, default="", nullable=False)
    execution_token: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )


class AiAgentEvaluation(Base):
    __tablename__ = "ai_agent_evaluations"
    __table_args__ = (Index("ix_agent_eval_version", "agent_version_id", "created_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    agent_version_id: Mapped[str] = mapped_column(
        ForeignKey("ai_agent_versions.id", ondelete="CASCADE"), nullable=False
    )
    dataset_version: Mapped[str] = mapped_column(String(32), nullable=False)
    evaluation_type: Mapped[str] = mapped_column(String(64), nullable=False)
    results: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(24), default="pending_review", nullable=False)
    reviewed_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )


class AiAgentUsage(Base):
    __tablename__ = "ai_agent_usage"
    __table_args__ = (Index("ix_agent_usage_org", "organization_id", "occurred_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(String(36), nullable=False)
    agent_id: Mapped[str] = mapped_column(String(36), nullable=False)
    agent_run_id: Mapped[str] = mapped_column(String(36), nullable=False)
    model_identifier: Mapped[str] = mapped_column(String(120), default="fake", nullable=False)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    estimated_cost_cents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )


class AiAgentSafetyEvent(Base):
    __tablename__ = "ai_agent_safety_events"
    __table_args__ = (Index("ix_agent_safety", "organization_id", "status", "created_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    agent_run_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), default="medium", nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="open", nullable=False)
    summary: Mapped[str] = mapped_column(Text, default="", nullable=False)
    assigned_owner_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AiWorkflowDefinition(Base):
    __tablename__ = "ai_workflow_definitions"
    __table_args__ = (UniqueConstraint("workflow_code", "version", name="uq_ai_workflow_ver"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    workflow_code: Mapped[str] = mapped_column(String(64), nullable=False)
    version: Mapped[str] = mapped_column(String(32), nullable=False)
    risk_level: Mapped[str] = mapped_column(String(16), default="medium", nullable=False)
    configuration: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class AiWorkflowExecution(Base):
    __tablename__ = "ai_workflow_executions"
    __table_args__ = (Index("ix_ai_workflow_exec", "organization_id", "status", "created_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(String(36), nullable=False)
    workflow_definition_id: Mapped[str] = mapped_column(
        ForeignKey("ai_workflow_definitions.id", ondelete="RESTRICT"), nullable=False
    )
    requested_by: Mapped[str] = mapped_column(String(36), nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="created", nullable=False)
    correlation_id: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    agent_run_ids: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


# --- V2.1.1 advanced agent foundation (extends V2.0; no second orchestrator) ---


class AiAgentCapability(Base):
    __tablename__ = "ai_agent_capabilities"
    __table_args__ = (
        UniqueConstraint("capability_code", "capability_version", name="uq_ai_capability_ver"),
        Index("ix_ai_capability_status", "status", "domain"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    capability_code: Mapped[str] = mapped_column(String(96), nullable=False)
    capability_version: Mapped[str] = mapped_column(String(32), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    domain: Mapped[str] = mapped_column(String(32), nullable=False)
    risk_level: Mapped[str] = mapped_column(String(16), default="medium", nullable=False)
    # draft | registered | security_review | evaluation | approved | enabled | monitored | suspended | retired
    status: Mapped[str] = mapped_column(String(24), default="draft", nullable=False)
    configuration: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    requires_human_approval: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    approved_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )


class AiCapabilityToolPermission(Base):
    __tablename__ = "ai_capability_tool_permissions"
    __table_args__ = (
        UniqueConstraint("capability_id", "tool_id", name="uq_capability_tool"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    capability_id: Mapped[str] = mapped_column(
        ForeignKey("ai_agent_capabilities.id", ondelete="CASCADE"), nullable=False
    )
    tool_id: Mapped[str] = mapped_column(
        ForeignKey("ai_agent_tools.id", ondelete="RESTRICT"), nullable=False
    )
    permission_scope: Mapped[str] = mapped_column(String(64), default="default", nullable=False)
    approval_required: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )


class AiAgentDelegation(Base):
    __tablename__ = "ai_agent_delegations"
    __table_args__ = (
        Index("ix_ai_delegation_parent", "organization_id", "parent_run_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    parent_run_id: Mapped[str] = mapped_column(
        ForeignKey("ai_agent_runs.id", ondelete="CASCADE"), nullable=False
    )
    child_run_id: Mapped[str | None] = mapped_column(
        ForeignKey("ai_agent_runs.id", ondelete="SET NULL"), nullable=True
    )
    target_capability_id: Mapped[str] = mapped_column(
        ForeignKey("ai_agent_capabilities.id", ondelete="RESTRICT"), nullable=False
    )
    requested_by: Mapped[str] = mapped_column(String(36), nullable=False)
    # created | running | completed | failed | cancelled | denied
    status: Mapped[str] = mapped_column(String(24), default="created", nullable=False)
    depth: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    permitted_tools: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    denial_reason: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AiClinicalContextAccessEvent(Base):
    __tablename__ = "ai_clinical_context_access_events"
    __table_args__ = (
        Index("ix_ai_ctx_access", "organization_id", "patient_id", "occurred_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(String(36), nullable=False)
    actor_id: Mapped[str] = mapped_column(String(36), nullable=False)
    patient_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    encounter_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    agent_run_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    resource_category: Mapped[str] = mapped_column(String(64), nullable=False)
    access_outcome: Mapped[str] = mapped_column(String(24), nullable=False)
    policy_reference: Mapped[str] = mapped_column(String(64), default="2.1.1", nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )


class AiEvidenceReference(Base):
    __tablename__ = "ai_evidence_references"
    __table_args__ = (Index("ix_ai_evidence_run", "organization_id", "agent_run_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(String(36), nullable=False)
    agent_run_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    patient_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    source_type: Mapped[str] = mapped_column(String(64), nullable=False)
    source_resource_id: Mapped[str] = mapped_column(String(64), nullable=False)
    source_version: Mapped[str] = mapped_column(String(32), default="1", nullable=False)
    source_location: Mapped[str] = mapped_column(String(256), default="", nullable=False)
    verification_status: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )


class AiExecutionContextRecord(Base):
    __tablename__ = "ai_execution_context_records"
    __table_args__ = (
        Index("ix_ai_exec_ctx", "organization_id", "agent_run_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(String(36), nullable=False)
    agent_run_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    actor_id: Mapped[str] = mapped_column(String(36), nullable=False)
    patient_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    encounter_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    capability_code: Mapped[str] = mapped_column(String(96), default="", nullable=False)
    capability_version: Mapped[str] = mapped_column(String(32), default="", nullable=False)
    authorization_reference: Mapped[str] = mapped_column(String(64), nullable=False)
    policy_version: Mapped[str] = mapped_column(String(16), default="2.1.1", nullable=False)
    correlation_id: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    context_reference: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    # active | expired | revoked
    status: Mapped[str] = mapped_column(String(24), default="active", nullable=False)
    permitted_tools: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    expiration_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
