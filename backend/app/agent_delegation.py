"""V2.1.1 secure agent delegation — permission intersection, depth limits, parent cancel."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.agent_capabilities import capability_allowed_tools, get_enabled_capability
from app.agent_context import create_execution_context, revalidate_context
from app.agent_models import AiAgentDelegation, AiAgentRun, AiExecutionContextRecord
from app.agent_orchestrator import cancel_run, create_agent_run, execute_agent_run, transition
from app.agent_policy import evaluate_policy
from app.auth import ApiError
from app.models import TenantMembership, User, utcnow

MAX_DELEGATION_DEPTH = 2
MAX_CHILD_RUNS_PER_PARENT = 5
MAX_TOOL_CALLS_HINT = 20

# Map capabilities to existing V2.0 agent codes when executing child runs
CAPABILITY_AGENT_MAP: dict[str, str] = {
    "clinical.patient_summary": "clinical_copilot",
    "clinical.lab_trend_review": "clinical_copilot",
    "clinical.encounter_context": "clinical_copilot",
    "clinical.documentation_review": "medical_scribe",
    "clinical.followup_proposal": "patient_engagement",
    "financial.claim_analysis": "revenue_cycle",
    "operations.schedule_analysis": "clinic_operations",
    "integration.failure_analysis": "integration_ops",
    "support.ticket_analysis": "support_assist",
    "knowledge.policy_retrieval": "enterprise_knowledge",
}


def _parent_depth(session: Session, parent_run_id: str) -> int:
    # Depth of this run as a child; root = 0
    row = session.execute(
        select(AiAgentDelegation).where(AiAgentDelegation.child_run_id == parent_run_id)
    ).scalar_one_or_none()
    return int(row.depth) if row else 0


def _child_count(session: Session, parent_run_id: str) -> int:
    return int(
        session.execute(
            select(func.count())
            .select_from(AiAgentDelegation)
            .where(
                AiAgentDelegation.parent_run_id == parent_run_id,
                AiAgentDelegation.status.in_(("created", "running", "completed")),
            )
        ).scalar_one()
    )


def delegate_agent_run(
    session: Session,
    *,
    parent_run: AiAgentRun,
    target_capability: str,
    user: User,
    membership: TenantMembership,
    requested_tool_codes: list[str] | None = None,
    task_reference: str = "",
    request_id: str = "",
    parent_context: AiExecutionContextRecord | None = None,
) -> AiAgentDelegation:
    if membership.tenant_id != parent_run.organization_id:
        raise ApiError("TENANT_NOT_FOUND", "Tenant not found.", 404)
    if parent_run.status in {"cancelled", "rejected", "timed_out", "failed"}:
        raise ApiError("PARENT_NOT_DELEGATABLE", "Parent run cannot accept new delegations.", 422)

    depth = _parent_depth(session, parent_run.id) + 1
    if depth > MAX_DELEGATION_DEPTH:
        raise ApiError("DELEGATION_DEPTH_EXCEEDED", "Maximum delegation depth exceeded.", 422)
    if _child_count(session, parent_run.id) >= MAX_CHILD_RUNS_PER_PARENT:
        raise ApiError("DELEGATION_FANOUT_EXCEEDED", "Maximum concurrent child runs exceeded.", 422)

    capability = get_enabled_capability(session, capability_code=target_capability)
    policy = evaluate_policy(membership=membership, capability=capability)
    if policy["decision"] == "deny":
        raise ApiError("DELEGATION_DENIED", policy["reason_code"], 403)

    cap_tools = set(capability_allowed_tools(session, capability))
    parent_tools: set[str] = set()
    if parent_context is not None:
        revalidate_context(session, context=parent_context)
        parent_tools = set(parent_context.permitted_tools or [])
    else:
        # Fallback: parent agent version allowed tools
        from app.agent_models import AiAgentVersion

        version = session.get(AiAgentVersion, parent_run.agent_version_id)
        parent_tools = set((version.configuration or {}).get("allowed_tools") or []) if version else set()

    requested = set(requested_tool_codes or list(cap_tools))
    # Intersection: actor cannot expand via delegation
    permitted = sorted(requested & cap_tools & (parent_tools or cap_tools))
    # Knowledge may have empty tools — still allow child with empty tool set
    if cap_tools and not permitted and requested:
        raise ApiError(
            "DELEGATION_TOOLS_DENIED",
            "Requested tools are outside the permission intersection.",
            403,
        )

    agent_code = CAPABILITY_AGENT_MAP.get(target_capability)
    if not agent_code:
        raise ApiError("CAPABILITY_AGENT_UNMAPPED", "No agent mapped for capability.", 422)

    child = create_agent_run(
        session,
        organization_id=parent_run.organization_id,
        agent_code=agent_code,
        user=user,
        membership=membership,
        workflow_type=f"delegate:{target_capability}",
        patient_id=parent_run.patient_id,
        input_summary={
            "parent_run_id": parent_run.id,
            "task_reference": task_reference,
            "permitted_tools": permitted,
            "delegation": True,
        },
        idempotency_key=f"delegate-{parent_run.id}-{target_capability}-{uuid4().hex[:8]}",
    )

    create_execution_context(
        session,
        organization_id=parent_run.organization_id,
        user=user,
        membership=membership,
        capability_code=target_capability,
        patient_id=parent_run.patient_id,
        agent_run_id=child.id,
        request_id=request_id,
        correlation_id=parent_run.correlation_id,
    )

    delegation = AiAgentDelegation(
        organization_id=parent_run.organization_id,
        parent_run_id=parent_run.id,
        child_run_id=child.id,
        target_capability_id=capability.id,
        requested_by=user.id,
        status="running",
        depth=depth,
        permitted_tools=permitted,
    )
    session.add(delegation)
    session.flush()

    # Re-authorize child independently (no permission expansion)
    try:
        execute_agent_run(
            session, run=child, user=user, membership=membership, request_id=request_id
        )
        delegation.status = (
            "completed"
            if child.status in {"completed", "waiting_approval"}
            else "failed"
            if child.status == "failed"
            else "running"
        )
        if delegation.status in {"completed", "failed"}:
            delegation.completed_at = utcnow()
    except ApiError as exc:
        delegation.status = "failed"
        delegation.denial_reason = exc.code
        delegation.completed_at = utcnow()
        if child.status not in {"failed", "cancelled"}:
            try:
                transition(child, "failed")
            except ApiError:
                pass
    session.flush()
    return delegation


def cancel_parent_cascades(session: Session, *, parent_run: AiAgentRun) -> list[str]:
    """Cancel parent and eligible pending/running children."""
    cancel_run(session, run=parent_run)
    cancelled: list[str] = []
    children = session.execute(
        select(AiAgentDelegation).where(
            AiAgentDelegation.parent_run_id == parent_run.id,
            AiAgentDelegation.status.in_(("created", "running")),
        )
    ).scalars().all()
    for d in children:
        d.status = "cancelled"
        d.completed_at = utcnow()
        if d.child_run_id:
            child = session.get(AiAgentRun, d.child_run_id)
            if child and child.status not in {"completed", "cancelled", "rejected"}:
                try:
                    cancel_run(session, run=child)
                    cancelled.append(child.id)
                except ApiError:
                    pass
    session.flush()
    return cancelled


def delegation_dict(row: AiAgentDelegation) -> dict[str, Any]:
    return {
        "delegation_id": row.id,
        "organization_id": row.organization_id,
        "parent_run_id": row.parent_run_id,
        "child_run_id": row.child_run_id,
        "target_capability_id": row.target_capability_id,
        "status": row.status,
        "depth": row.depth,
        "permitted_tools": row.permitted_tools or [],
        "denial_reason": row.denial_reason,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "completed_at": row.completed_at.isoformat() if row.completed_at else None,
    }
