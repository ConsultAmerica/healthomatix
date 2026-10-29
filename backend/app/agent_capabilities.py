"""V2.1.1 versioned agent capability contracts — extends V2.0 registry, not a second one."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agent_models import AiAgentCapability, AiAgentTool, AiCapabilityToolPermission
from app.agent_orchestrator import ensure_agent_catalog
from app.auth import ApiError
from app.models import User, utcnow

CAPABILITY_TRANSITIONS: dict[str, frozenset[str]] = {
    "draft": frozenset({"registered", "retired"}),
    "registered": frozenset({"security_review", "retired"}),
    "security_review": frozenset({"evaluation", "suspended", "retired"}),
    "evaluation": frozenset({"approved", "suspended", "retired"}),
    "approved": frozenset({"enabled", "suspended", "retired"}),
    "enabled": frozenset({"monitored", "suspended", "retired"}),
    "monitored": frozenset({"suspended", "retired", "enabled"}),
    "suspended": frozenset({"approved", "retired", "enabled"}),
    "retired": frozenset(),
}

Domain = Literal["clinical", "financial", "operations", "integration", "knowledge", "support"]
Risk = Literal["low", "medium", "high", "restricted"]


class AgentCapabilityContract(BaseModel):
    capability_code: str = Field(min_length=2, max_length=96)
    capability_version: str = Field(default="1.0.0", max_length=32)
    description: str = ""
    domain: Domain
    required_permissions: list[str] = Field(default_factory=list)
    allowed_tools: list[str] = Field(default_factory=list)
    risk_level: Risk = "medium"
    requires_human_approval: bool = True
    enabled: bool = False


DEFAULT_CAPABILITIES: tuple[AgentCapabilityContract, ...] = (
    AgentCapabilityContract(
        capability_code="clinical.patient_summary",
        domain="clinical",
        description="Source-grounded patient summaries for authorized clinicians.",
        required_permissions=["clinical_read"],
        allowed_tools=["patient.get_authorized_summary", "patient.get_verified_observations"],
        risk_level="high",
        requires_human_approval=True,
    ),
    AgentCapabilityContract(
        capability_code="clinical.lab_trend_review",
        domain="clinical",
        description="Summarize verified laboratory trends only.",
        required_permissions=["clinical_read"],
        allowed_tools=["patient.get_verified_observations"],
        risk_level="high",
        requires_human_approval=True,
    ),
    AgentCapabilityContract(
        capability_code="clinical.encounter_context",
        domain="clinical",
        description="Prepare authorized encounter context.",
        required_permissions=["clinical_read"],
        allowed_tools=["patient.get_authorized_summary", "patient.get_verified_observations"],
        risk_level="high",
        requires_human_approval=False,
    ),
    AgentCapabilityContract(
        capability_code="clinical.documentation_review",
        domain="clinical",
        description="Identify documentation inconsistencies (suggestions only).",
        required_permissions=["clinical_read"],
        allowed_tools=["clinical.propose_note_draft"],
        risk_level="high",
        requires_human_approval=True,
    ),
    AgentCapabilityContract(
        capability_code="clinical.followup_proposal",
        domain="clinical",
        description="Draft clinician-reviewable follow-up actions.",
        required_permissions=["clinical_write_propose"],
        allowed_tools=["clinical.propose_note_draft", "messaging.propose_patient_message"],
        risk_level="high",
        requires_human_approval=True,
    ),
    AgentCapabilityContract(
        capability_code="financial.claim_analysis",
        domain="financial",
        description="Analyze authorized claims; no autonomous submit/refund.",
        required_permissions=["billing_propose"],
        allowed_tools=["billing.propose_claim_correction"],
        risk_level="high",
        requires_human_approval=True,
    ),
    AgentCapabilityContract(
        capability_code="operations.schedule_analysis",
        domain="operations",
        description="Summarize scheduling and capacity.",
        required_permissions=["scheduling_propose"],
        allowed_tools=["scheduling.propose_appointment_change"],
        risk_level="medium",
        requires_human_approval=True,
    ),
    AgentCapabilityContract(
        capability_code="integration.failure_analysis",
        domain="integration",
        description="Explain interface failures from metadata.",
        required_permissions=["integration_read"],
        allowed_tools=["integration.get_transaction_status", "integration.propose_retry"],
        risk_level="medium",
        requires_human_approval=True,
    ),
    AgentCapabilityContract(
        capability_code="knowledge.policy_retrieval",
        domain="knowledge",
        description="Retrieve authorized organizational policies.",
        required_permissions=["knowledge_read"],
        allowed_tools=[],
        risk_level="low",
        requires_human_approval=False,
    ),
    AgentCapabilityContract(
        capability_code="support.ticket_analysis",
        domain="support",
        description="Summarize authorized support tickets.",
        required_permissions=["support_read"],
        allowed_tools=["support.get_ticket_summary", "support.propose_response"],
        risk_level="medium",
        requires_human_approval=True,
    ),
)


def ensure_capability_catalog(session: Session) -> None:
    ensure_agent_catalog(session)
    for spec in DEFAULT_CAPABILITIES:
        existing = session.execute(
            select(AiAgentCapability).where(
                AiAgentCapability.capability_code == spec.capability_code,
                AiAgentCapability.capability_version == spec.capability_version,
            )
        ).scalar_one_or_none()
        if existing is not None:
            continue
        # Seed enabled only when no human approval required and controls already exist
        status = "enabled" if not spec.requires_human_approval else "registered"
        row = AiAgentCapability(
            capability_code=spec.capability_code,
            capability_version=spec.capability_version,
            description=spec.description,
            domain=spec.domain,
            risk_level=spec.risk_level,
            status=status,
            configuration={
                "required_permissions": list(spec.required_permissions),
                "allowed_tools": list(spec.allowed_tools),
            },
            requires_human_approval=spec.requires_human_approval,
        )
        session.add(row)
        session.flush()
        for tool_code in spec.allowed_tools:
            tool = session.execute(
                select(AiAgentTool).where(AiAgentTool.tool_code == tool_code)
            ).scalar_one_or_none()
            if tool is None:
                continue
            session.add(
                AiCapabilityToolPermission(
                    capability_id=row.id,
                    tool_id=tool.id,
                    permission_scope="default",
                    approval_required=spec.requires_human_approval,
                )
            )
    session.flush()


def transition_capability(cap: AiAgentCapability, new_status: str) -> None:
    allowed = CAPABILITY_TRANSITIONS.get(cap.status, frozenset())
    if new_status not in allowed:
        raise ApiError(
            "INVALID_CAPABILITY_TRANSITION",
            f"Cannot transition capability from {cap.status} to {new_status}.",
            422,
        )
    cap.status = new_status


def get_enabled_capability(
    session: Session, *, capability_code: str, version: str | None = None
) -> AiAgentCapability:
    ensure_capability_catalog(session)
    stmt = select(AiAgentCapability).where(
        AiAgentCapability.capability_code == capability_code,
        AiAgentCapability.status.in_(("enabled", "monitored")),
    )
    if version:
        stmt = stmt.where(AiAgentCapability.capability_version == version)
    row = session.execute(stmt.order_by(AiAgentCapability.created_at.desc())).scalars().first()
    if row is None:
        raise ApiError(
            "CAPABILITY_NOT_ENABLED",
            "Capability is not registered or not enabled.",
            404,
        )
    return row


def capability_allowed_tools(session: Session, capability: AiAgentCapability) -> list[str]:
    configured = list((capability.configuration or {}).get("allowed_tools") or [])
    rows = session.execute(
        select(AiAgentTool.tool_code)
        .join(AiCapabilityToolPermission, AiCapabilityToolPermission.tool_id == AiAgentTool.id)
        .where(AiCapabilityToolPermission.capability_id == capability.id)
    ).scalars().all()
    joined = list(rows)
    # Intersection: configuration and join table when join exists
    if joined:
        return [t for t in configured if t in set(joined)] or joined
    return configured


def capability_dict(row: AiAgentCapability, tools: list[str] | None = None) -> dict[str, Any]:
    return {
        "capability_id": row.id,
        "capability_code": row.capability_code,
        "capability_version": row.capability_version,
        "description": row.description,
        "domain": row.domain,
        "risk_level": row.risk_level,
        "status": row.status,
        "requires_human_approval": row.requires_human_approval,
        "allowed_tools": tools
        if tools is not None
        else list((row.configuration or {}).get("allowed_tools") or []),
        "approved_by": row.approved_by,
        "approved_at": row.approved_at.isoformat() if row.approved_at else None,
    }


def approve_capability(session: Session, *, cap: AiAgentCapability, approver: User) -> AiAgentCapability:
    if cap.status == "approved":
        return cap
    if cap.status not in {"evaluation", "security_review", "registered"}:
        raise ApiError(
            "CAPABILITY_NOT_REVIEWABLE",
            "Capability cannot be approved from current status.",
            422,
        )
    if cap.status == "registered":
        transition_capability(cap, "security_review")
        transition_capability(cap, "evaluation")
    elif cap.status == "security_review":
        transition_capability(cap, "evaluation")
    if cap.status == "evaluation":
        transition_capability(cap, "approved")
    cap.approved_by = approver.id
    cap.approved_at = utcnow()
    session.flush()
    return cap
