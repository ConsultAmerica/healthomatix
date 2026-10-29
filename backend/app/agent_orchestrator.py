"""V2.0 agent orchestration — durable runs, approvals, usage, safety."""

from __future__ import annotations

from datetime import timedelta
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agent_models import (
    AiAgentApproval,
    AiAgentDefinition,
    AiAgentRun,
    AiAgentRunStep,
    AiAgentSafetyEvent,
    AiAgentTool,
    AiAgentToolExecution,
    AiAgentUsage,
    AiAgentVersion,
    AiWorkflowDefinition,
    AiWorkflowExecution,
)
from app.agent_tools import (
    PROPOSAL_TOOLS,
    READ_TOOLS,
    authorize_tool_role,
    canonical_hash,
    execute_read_tool,
)
from app.auth import ApiError
from app.intelligence.clinical_ai_port import PROMPT_VERSION, build_clinical_ai_adapter
from app.models import TenantMembership, User, new_id, utcnow

ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
    "created": frozenset({"queued", "cancelled"}),
    "queued": frozenset({"running", "cancelled", "timed_out"}),
    "running": frozenset(
        {"waiting_approval", "waiting_external", "completed", "failed", "cancelled", "timed_out"}
    ),
    "waiting_approval": frozenset({"running", "rejected", "cancelled", "timed_out", "completed"}),
    "waiting_external": frozenset({"running", "failed", "cancelled", "timed_out"}),
    "completed": frozenset(),
    "failed": frozenset({"queued"}),  # retry
    "cancelled": frozenset(),
    "timed_out": frozenset({"queued"}),
    "rejected": frozenset(),
}

DEFAULT_AGENTS: tuple[dict[str, Any], ...] = (
    {
        "agent_code": "clinical_copilot",
        "agent_name": "Clinical Copilot",
        "domain": "clinical",
        "risk_level": "high",
        "description": "Source-grounded chart summaries for authorized clinicians.",
        "tools": ["patient.get_authorized_summary", "patient.get_verified_observations", "clinical.propose_note_draft"],
    },
    {
        "agent_code": "medical_scribe",
        "agent_name": "Medical Scribe",
        "domain": "clinical",
        "risk_level": "high",
        "description": "Consent-aware documentation drafts; clinician signs.",
        "tools": ["clinical.propose_note_draft"],
    },
    {
        "agent_code": "patient_engagement",
        "agent_name": "Patient Engagement",
        "domain": "clinical",
        "risk_level": "medium",
        "description": "Education and message drafts requiring approval.",
        "tools": ["messaging.propose_patient_message"],
    },
    {
        "agent_code": "clinic_operations",
        "agent_name": "Clinic Operations",
        "domain": "business",
        "risk_level": "medium",
        "description": "Scheduling and capacity analysis proposals.",
        "tools": ["scheduling.propose_appointment_change"],
    },
    {
        "agent_code": "revenue_cycle",
        "agent_name": "Revenue Cycle Intelligence",
        "domain": "business",
        "risk_level": "high",
        "description": "Claim review proposals — no autonomous submit/refund.",
        "tools": ["billing.propose_claim_correction"],
    },
    {
        "agent_code": "integration_ops",
        "agent_name": "Healthcare Integration",
        "domain": "platform",
        "risk_level": "medium",
        "description": "Failure classification and governed retry proposals.",
        "tools": ["integration.get_transaction_status", "integration.propose_retry"],
    },
    {
        "agent_code": "support_assist",
        "agent_name": "Support Assistant",
        "domain": "business",
        "risk_level": "medium",
        "description": "Ticket summaries and response drafts.",
        "tools": ["support.get_ticket_summary", "support.propose_response"],
    },
    {
        "agent_code": "enterprise_knowledge",
        "agent_name": "Enterprise Knowledge",
        "domain": "platform",
        "risk_level": "low",
        "description": "Permission-aware help article retrieval.",
        "tools": [],
    },
)


def transition(run: AiAgentRun, new_status: str) -> None:
    allowed = ALLOWED_TRANSITIONS.get(run.status, frozenset())
    if new_status not in allowed:
        raise ApiError(
            "INVALID_STATE_TRANSITION",
            f"Cannot transition agent run from {run.status} to {new_status}.",
            422,
        )
    run.status = new_status


def ensure_agent_catalog(session: Session) -> None:
    for tool_code, meta in {**READ_TOOLS, **PROPOSAL_TOOLS}.items():
        existing = session.execute(
            select(AiAgentTool).where(AiAgentTool.tool_code == tool_code)
        ).scalar_one_or_none()
        if existing is None:
            session.add(
                AiAgentTool(
                    tool_code=tool_code,
                    description=tool_code,
                    risk_level=meta["risk"],
                    required_permission=meta["permission"],
                    approval_required=bool(meta.get("approval_required", True)),
                    enabled=True,
                )
            )
    for spec in DEFAULT_AGENTS:
        agent = session.execute(
            select(AiAgentDefinition).where(AiAgentDefinition.agent_code == spec["agent_code"])
        ).scalar_one_or_none()
        if agent is None:
            agent = AiAgentDefinition(
                agent_code=spec["agent_code"],
                agent_name=spec["agent_name"],
                domain=spec["domain"],
                description=spec["description"],
                risk_level=spec["risk_level"],
                current_version="1.0.0",
                enabled=True,
            )
            session.add(agent)
            session.flush()
            session.add(
                AiAgentVersion(
                    agent_id=agent.id,
                    version="1.0.0",
                    model_identifier="fake",
                    prompt_version=PROMPT_VERSION,
                    configuration={"allowed_tools": list(spec["tools"])},
                    evaluation_status="sandbox_approved",
                )
            )
    wf = session.execute(
        select(AiWorkflowDefinition).where(
            AiWorkflowDefinition.workflow_code == "clinical_previsit",
            AiWorkflowDefinition.version == "1.0.0",
        )
    ).scalar_one_or_none()
    if wf is None:
        session.add(
            AiWorkflowDefinition(
                workflow_code="clinical_previsit",
                version="1.0.0",
                risk_level="high",
                configuration={"agents": ["clinical_copilot"]},
                enabled=True,
            )
        )
    session.flush()


def _add_step(
    session: Session,
    *,
    run_id: str,
    step_number: int,
    step_type: str,
    status: str,
    detail: dict[str, Any] | None = None,
    output_reference: str = "",
) -> AiAgentRunStep:
    step = AiAgentRunStep(
        agent_run_id=run_id,
        step_number=step_number,
        step_type=step_type,
        status=status,
        detail=detail or {},
        output_reference=output_reference,
        started_at=utcnow(),
        completed_at=utcnow() if status in {"completed", "failed"} else None,
    )
    session.add(step)
    session.flush()
    return step


def create_agent_run(
    session: Session,
    *,
    organization_id: str,
    agent_code: str,
    user: User,
    membership: TenantMembership,
    workflow_type: str = "",
    patient_id: str | None = None,
    input_summary: dict[str, Any] | None = None,
    idempotency_key: str | None = None,
) -> AiAgentRun:
    ensure_agent_catalog(session)
    if membership.tenant_id != organization_id:
        raise ApiError("TENANT_NOT_FOUND", "Tenant not found.", 404)
    key = idempotency_key or f"run-{uuid4().hex}"
    existing = session.execute(
        select(AiAgentRun).where(
            AiAgentRun.organization_id == organization_id,
            AiAgentRun.idempotency_key == key,
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing

    agent = session.execute(
        select(AiAgentDefinition).where(
            AiAgentDefinition.agent_code == agent_code, AiAgentDefinition.enabled.is_(True)
        )
    ).scalar_one_or_none()
    if agent is None:
        raise ApiError("AGENT_NOT_FOUND", "Agent is not registered or disabled.", 404)
    version = session.execute(
        select(AiAgentVersion)
        .where(
            AiAgentVersion.agent_id == agent.id,
            AiAgentVersion.version == agent.current_version,
        )
        .order_by(AiAgentVersion.created_at.desc())
    ).scalars().first()
    if version is None:
        raise ApiError("AGENT_VERSION_MISSING", "Agent version is not configured.", 500)

    run = AiAgentRun(
        organization_id=organization_id,
        agent_id=agent.id,
        agent_version_id=version.id,
        requested_by=user.id,
        workflow_type=workflow_type,
        status="created",
        correlation_id=uuid4().hex,
        idempotency_key=key,
        patient_id=patient_id,
        input_summary=input_summary or {},
    )
    session.add(run)
    session.flush()
    _add_step(session, run_id=run.id, step_number=1, step_type="created", status="completed")
    transition(run, "queued")
    session.flush()
    return run


def execute_agent_run(
    session: Session,
    *,
    run: AiAgentRun,
    user: User,
    membership: TenantMembership,
    request_id: str,
) -> AiAgentRun:
    if run.status not in {"queued", "running", "failed", "timed_out"}:
        if run.status == "created":
            transition(run, "queued")
        else:
            raise ApiError("RUN_NOT_EXECUTABLE", f"Run status {run.status} cannot execute.", 422)

    transition(run, "running")
    run.started_at = run.started_at or utcnow()
    agent = session.get(AiAgentDefinition, run.agent_id)
    version = session.get(AiAgentVersion, run.agent_version_id)
    if agent is None or version is None:
        raise ApiError("AGENT_NOT_FOUND", "Agent missing.", 404)

    step_n = 2
    _add_step(
        session,
        run_id=run.id,
        step_number=step_n,
        step_type="authorize",
        status="completed",
        detail={"role": membership.role, "tenant_id": membership.tenant_id},
    )
    step_n += 1

    context: dict[str, Any] = {"agent_code": agent.agent_code, "sources": []}
    allowed_tools = list((version.configuration or {}).get("allowed_tools") or [])

    # Context retrieval for clinical agents
    if run.patient_id and "patient.get_authorized_summary" in allowed_tools:
        summary = execute_read_tool(
            session,
            tool_code="patient.get_authorized_summary",
            tenant_id=run.organization_id,
            user=user,
            membership=membership,
            request_id=request_id,
            params={"patient_id": run.patient_id},
        )
        context["patient_summary"] = summary
        context["sources"].append({"type": "Patient", "id": run.patient_id})
        _record_tool_exec(
            session,
            run=run,
            tool_code="patient.get_authorized_summary",
            actor_id=user.id,
            status="completed",
            target=f"Patient/{run.patient_id}",
            result=summary,
        )
        step_n += 1
        _add_step(
            session,
            run_id=run.id,
            step_number=step_n,
            step_type="tool:patient.get_authorized_summary",
            status="completed",
        )

    if run.patient_id and "patient.get_verified_observations" in allowed_tools:
        obs = execute_read_tool(
            session,
            tool_code="patient.get_verified_observations",
            tenant_id=run.organization_id,
            user=user,
            membership=membership,
            request_id=request_id,
            params={"patient_id": run.patient_id},
        )
        context["observations"] = obs
        for item in obs.get("verified_or_chart") or []:
            context["sources"].append(
                {
                    "type": "Observation",
                    "id": item.get("id"),
                    "verification": item.get("verification"),
                }
            )
        for item in obs.get("imported_unverified") or []:
            context["sources"].append(
                {
                    "type": "Observation",
                    "id": item.get("id"),
                    "verification": "imported_unverified",
                }
            )
        _record_tool_exec(
            session,
            run=run,
            tool_code="patient.get_verified_observations",
            actor_id=user.id,
            status="completed",
            target=f"Patient/{run.patient_id}",
            result={"counts": {"verified": len(obs.get("verified_or_chart") or []), "unverified": len(obs.get("imported_unverified") or [])}},
        )

    # Produce reviewable proposal for high-risk clinical/business outputs
    proposal_tool = None
    for code in allowed_tools:
        if code in PROPOSAL_TOOLS:
            proposal_tool = code
            break

    ai = build_clinical_ai_adapter()
    draft_text = ""
    if agent.agent_code == "clinical_copilot":
        draft_text = (
            "Pre-visit operational summary (review required). "
            f"Authorized patient context loaded={bool(context.get('patient_summary'))}. "
            f"Chart observations={len((context.get('observations') or {}).get('verified_or_chart') or [])}. "
            f"Imported unverified labs={len((context.get('observations') or {}).get('imported_unverified') or [])}. "
            "This is not a diagnosis or treatment plan."
        )
    elif agent.agent_code == "medical_scribe":
        bundle = ai.generate_soap_draft(
            patient_id=run.patient_id or "unknown",
            visit_reason=str((run.input_summary or {}).get("visit_reason") or "Follow-up"),
            clinician_notes=str((run.input_summary or {}).get("clinician_notes") or ""),
            transcript=str((run.input_summary or {}).get("transcript") or "Synthetic encounter notes."),
            observations=list((context.get("observations") or {}).get("verified_or_chart") or []),
        )
        content = bundle.content if isinstance(bundle.content, dict) else {}
        draft_text = (
            f"S:{content.get('subjective', '')}\n"
            f"O:{content.get('objective', '')}\n"
            f"A:{content.get('assessment', '')}\n"
            f"P:{content.get('plan', '')}"
        )
        for link in bundle.source_links or []:
            context["sources"].append(
                {
                    "type": "source_link",
                    "reference": link.get("reference"),
                    "label": link.get("label"),
                }
            )
    elif agent.agent_code == "revenue_cycle":
        draft_text = (
            "Claim review proposal: verify coding completeness and denial reason codes "
            "against authorized claim metadata. No claim will be submitted without approval."
        )
    elif agent.agent_code == "integration_ops":
        txn_id = str((run.input_summary or {}).get("transaction_id") or "")
        if txn_id and "integration.get_transaction_status" in allowed_tools:
            status = execute_read_tool(
                session,
                tool_code="integration.get_transaction_status",
                tenant_id=run.organization_id,
                user=user,
                membership=membership,
                request_id=request_id,
                params={"transaction_id": txn_id},
            )
            context["transaction"] = status
            draft_text = f"Integration remediation proposal for status={status.get('status')}."
        else:
            draft_text = "Integration investigation requires a transaction_id."
    else:
        draft_text = f"Agent {agent.agent_code} prepared a reviewable administrative draft."

    output = {
        "draft": draft_text,
        "sources": context.get("sources") or [],
        "unverified_data_flagged": bool(
            (context.get("observations") or {}).get("imported_unverified")
        ),
        "disclaimer": "AI output requires authorized human review for clinical/financial actions.",
    }
    run.output_summary = output

    session.add(
        AiAgentUsage(
            organization_id=run.organization_id,
            agent_id=run.agent_id,
            agent_run_id=run.id,
            model_identifier=version.model_identifier,
            input_tokens=50,
            output_tokens=80,
            estimated_cost_cents=1,
        )
    )

    if proposal_tool:
        meta = PROPOSAL_TOOLS[proposal_tool]
        authorize_tool_role(membership, meta)
        payload = {
            "tool": proposal_tool,
            "draft": draft_text,
            "sources": output["sources"],
            "patient_id": run.patient_id,
            "run_id": run.id,
        }
        approval = AiAgentApproval(
            organization_id=run.organization_id,
            agent_run_id=run.id,
            proposal_version=1,
            proposal_hash=canonical_hash(payload),
            proposal_payload=payload,
            required_role=str(meta.get("required_role") or "provider"),
            status="pending",
            execution_token=uuid4().hex,
            expires_at=utcnow() + timedelta(hours=24),
        )
        session.add(approval)
        session.flush()
        _record_tool_exec(
            session,
            run=run,
            tool_code=proposal_tool,
            actor_id=user.id,
            status="proposed",
            target=run.patient_id or run.organization_id,
            result={"approval_id": approval.id},
            approval_id=approval.id,
        )
        transition(run, "waiting_approval")
        _add_step(
            session,
            run_id=run.id,
            step_number=step_n + 1,
            step_type="awaiting_approval",
            status="completed",
            detail={"approval_id": approval.id, "proposal_hash": approval.proposal_hash},
        )
    else:
        transition(run, "completed")
        run.completed_at = utcnow()
        _add_step(
            session,
            run_id=run.id,
            step_number=step_n + 1,
            step_type="completed",
            status="completed",
            detail=output,
        )
    session.flush()
    return run


def _record_tool_exec(
    session: Session,
    *,
    run: AiAgentRun,
    tool_code: str,
    actor_id: str,
    status: str,
    target: str,
    result: dict[str, Any],
    approval_id: str | None = None,
) -> None:
    tool = session.execute(
        select(AiAgentTool).where(AiAgentTool.tool_code == tool_code)
    ).scalar_one_or_none()
    if tool is None:
        return
    session.add(
        AiAgentToolExecution(
            organization_id=run.organization_id,
            agent_run_id=run.id,
            tool_id=tool.id,
            actor_id=actor_id,
            target_resource_reference=str(target)[:128],
            status=status,
            approval_id=approval_id,
            result_summary=result,
            executed_at=utcnow() if status == "completed" else None,
        )
    )
    session.flush()


def decide_approval(
    session: Session,
    *,
    approval: AiAgentApproval,
    approver: User,
    membership: TenantMembership,
    approve: bool,
    reason: str = "",
) -> AiAgentApproval:
    if approval.status != "pending":
        raise ApiError("APPROVAL_NOT_PENDING", "Approval is not pending.", 422)
    if approval.expires_at:
        expires = approval.expires_at
        now = utcnow()
        # SQLite may return naive datetimes for timezone-aware columns
        if expires.tzinfo is None and now.tzinfo is not None:
            expires = expires.replace(tzinfo=now.tzinfo)
        elif expires.tzinfo is not None and now.tzinfo is None:
            now = now.replace(tzinfo=expires.tzinfo)
        if expires < now:
            approval.status = "expired"
            session.flush()
            raise ApiError("APPROVAL_EXPIRED", "Approval has expired.", 410)
    if membership.tenant_id != approval.organization_id:
        raise ApiError("TENANT_NOT_FOUND", "Tenant not found.", 404)
    if membership.role != approval.required_role and membership.role not in {
        "tenant_admin",
        approval.required_role,
    }:
        # tenant_admin may approve staff/provider proposals for ops; clinical high-risk still prefers provider
        if approval.required_role == "provider" and membership.role != "provider":
            raise ApiError("APPROVER_ROLE_REQUIRED", "Provider approval is required.", 403)
        if approval.required_role == "tenant_admin" and membership.role != "tenant_admin":
            raise ApiError("APPROVER_ROLE_REQUIRED", "Administrator approval is required.", 403)

    # Integrity: hash must still match stored payload
    current_hash = canonical_hash(approval.proposal_payload or {})
    if current_hash != approval.proposal_hash:
        session.add(
            AiAgentSafetyEvent(
                organization_id=approval.organization_id,
                agent_run_id=approval.agent_run_id,
                event_type="proposal_tamper",
                severity="high",
                status="open",
                summary="Proposal hash mismatch — approval blocked.",
            )
        )
        raise ApiError("PROPOSAL_INTEGRITY_FAILED", "Proposal was modified after creation.", 409)

    approval.approver_id = approver.id
    approval.decision_reason = reason
    approval.decided_at = utcnow()
    approval.status = "approved" if approve else "rejected"
    run = session.get(AiAgentRun, approval.agent_run_id)
    if run:
        if approve:
            # Mark approved but do not auto-execute high-risk clinical commit
            transition(run, "completed")
            run.completed_at = utcnow()
            approval.status = "executed"
            run.output_summary = {
                **(run.output_summary or {}),
                "approval_status": "approved",
                "execution_note": "Proposal approved for authorized downstream workflow — agent did not auto-sign/submit.",
            }
        else:
            transition(run, "rejected")
            run.completed_at = utcnow()
    session.flush()
    return approval


def cancel_run(session: Session, *, run: AiAgentRun) -> AiAgentRun:
    if run.status in {"completed", "cancelled", "rejected"}:
        raise ApiError("RUN_NOT_CANCELLABLE", "Run cannot be cancelled.", 422)
    transition(run, "cancelled")
    run.completed_at = utcnow()
    session.flush()
    return run


def start_workflow(
    session: Session,
    *,
    organization_id: str,
    workflow_code: str,
    user: User,
    membership: TenantMembership,
    patient_id: str | None,
    request_id: str,
) -> AiWorkflowExecution:
    ensure_agent_catalog(session)
    wf = session.execute(
        select(AiWorkflowDefinition).where(
            AiWorkflowDefinition.workflow_code == workflow_code,
            AiWorkflowDefinition.enabled.is_(True),
        )
    ).scalars().first()
    if wf is None:
        raise ApiError("WORKFLOW_NOT_FOUND", "Workflow not found.", 404)
    agents = list((wf.configuration or {}).get("agents") or [])
    run_ids: list[str] = []
    for agent_code in agents:
        run = create_agent_run(
            session,
            organization_id=organization_id,
            agent_code=agent_code,
            user=user,
            membership=membership,
            workflow_type=workflow_code,
            patient_id=patient_id,
            input_summary={"workflow": workflow_code},
            idempotency_key=f"wf-{workflow_code}-{organization_id}-{patient_id or 'none'}-{uuid4().hex[:8]}",
        )
        execute_agent_run(
            session, run=run, user=user, membership=membership, request_id=request_id
        )
        run_ids.append(run.id)
    # Delegation must not expand permissions — each run revalidated independently above
    execution = AiWorkflowExecution(
        organization_id=organization_id,
        workflow_definition_id=wf.id,
        requested_by=user.id,
        status="completed" if run_ids else "failed",
        correlation_id=uuid4().hex,
        agent_run_ids=run_ids,
        completed_at=utcnow(),
    )
    session.add(execution)
    session.flush()
    return execution
