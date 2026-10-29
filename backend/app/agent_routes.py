"""V2.0 AI agent registry + V2.1.1 advanced capability / context / delegation APIs."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request, Response
from pydantic import Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.agent_capabilities import (
    approve_capability,
    capability_allowed_tools,
    capability_dict,
    ensure_capability_catalog,
    transition_capability,
)
from app.agent_context import context_dict, create_execution_context
from app.agent_delegation import cancel_parent_cascades, delegate_agent_run, delegation_dict
from app.agent_models import (
    AiAgentApproval,
    AiAgentCapability,
    AiAgentDefinition,
    AiAgentDelegation,
    AiAgentEvaluation,
    AiAgentRun,
    AiAgentRunStep,
    AiAgentSafetyEvent,
    AiAgentTool,
    AiAgentUsage,
    AiAgentVersion,
    AiClinicalContextAccessEvent,
    AiWorkflowDefinition,
    AiWorkflowExecution,
)
from app.agent_orchestrator import (
    cancel_run,
    create_agent_run,
    decide_approval,
    ensure_agent_catalog,
    execute_agent_run,
    start_workflow,
)
from app.audit import append_audit_event
from app.auth import ApiError, get_current_user
from app.authorization import require_role
from app.clinical_context_service import get_authorized_patient_context, list_run_evidence
from app.consent_gate import require_patient_consent
from app.db import get_session
from app.models import TenantMembership, User, utcnow
from app.platform_routes import require_platform_admin
from app.schemas import StrictModel

router = APIRouter(prefix="/api/v1", tags=["ai-agents"])


class AgentRunWrite(StrictModel):
    agent_code: str = Field(min_length=2, max_length=64)
    patient_id: str | None = Field(default=None, min_length=36, max_length=36)
    workflow_type: str = Field(default="", max_length=64)
    input_summary: dict[str, Any] = Field(default_factory=dict)
    idempotency_key: str | None = Field(default=None, max_length=128)
    execute: bool = True


class ApprovalDecisionWrite(StrictModel):
    reason: str = Field(default="", max_length=2000)


class WorkflowRunWrite(StrictModel):
    workflow_code: str = Field(min_length=2, max_length=64)
    patient_id: str | None = Field(default=None, min_length=36, max_length=36)


class AgentEvalWrite(StrictModel):
    agent_version_id: str = Field(min_length=36, max_length=36)
    dataset_version: str = Field(default="synthetic-v1", max_length=32)
    evaluation_type: str = Field(min_length=2, max_length=64)
    results: dict[str, Any] = Field(default_factory=dict)


class KnowledgeQueryWrite(StrictModel):
    query: str = Field(min_length=2, max_length=500)


class ForecastWrite(StrictModel):
    metric: str = Field(default="appointment_demand", max_length=64)
    horizon_days: int = Field(default=14, ge=1, le=90)


class CapabilityStatusWrite(StrictModel):
    status: str = Field(min_length=2, max_length=24)


class DelegationWrite(StrictModel):
    target_capability: str = Field(min_length=2, max_length=96)
    task_reference: str = Field(default="", max_length=128)
    requested_tool_codes: list[str] = Field(default_factory=list)


def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", "")


def _run_dict(row: AiAgentRun) -> dict[str, Any]:
    return {
        "run_id": row.id,
        "organization_id": row.organization_id,
        "agent_id": row.agent_id,
        "status": row.status,
        "workflow_type": row.workflow_type,
        "correlation_id": row.correlation_id,
        "patient_id": row.patient_id,
        "output_summary": row.output_summary or {},
        "error_code": row.error_code,
        "started_at": row.started_at.isoformat() if row.started_at else None,
        "completed_at": row.completed_at.isoformat() if row.completed_at else None,
    }


@router.get("/platform/ai/agents")
def list_agents(
    response: Response,
    user: User = Depends(require_platform_admin),
    session: Session = Depends(get_session),
) -> list[dict[str, Any]]:
    ensure_agent_catalog(session)
    rows = session.execute(select(AiAgentDefinition).order_by(AiAgentDefinition.agent_code)).scalars()
    response.headers["Cache-Control"] = "no-store"
    return [
        {
            "agent_id": row.id,
            "agent_code": row.agent_code,
            "agent_name": row.agent_name,
            "domain": row.domain,
            "risk_level": row.risk_level,
            "current_version": row.current_version,
            "enabled": row.enabled,
            "description": row.description,
        }
        for row in rows
    ]


@router.get("/platform/ai/agents/{agent_id}/versions")
def list_agent_versions(
    agent_id: str,
    response: Response,
    user: User = Depends(require_platform_admin),
    session: Session = Depends(get_session),
) -> list[dict[str, Any]]:
    rows = session.execute(
        select(AiAgentVersion)
        .where(AiAgentVersion.agent_id == agent_id)
        .order_by(AiAgentVersion.created_at.desc())
    ).scalars()
    response.headers["Cache-Control"] = "no-store"
    return [
        {
            "version_id": row.id,
            "version": row.version,
            "model_id": row.model_identifier,
            "prompt_version": row.prompt_version,
            "evaluation_status": row.evaluation_status,
            "configuration": row.configuration or {},
        }
        for row in rows
    ]


@router.get("/platform/ai/tools")
def list_tools(
    response: Response,
    user: User = Depends(require_platform_admin),
    session: Session = Depends(get_session),
) -> list[dict[str, Any]]:
    ensure_agent_catalog(session)
    rows = session.execute(select(AiAgentTool)).scalars()
    response.headers["Cache-Control"] = "no-store"
    return [
        {
            "tool_id": row.id,
            "tool_code": row.tool_code,
            "risk_level": row.risk_level,
            "required_permission": row.required_permission,
            "approval_required": row.approval_required,
            "enabled": row.enabled,
        }
        for row in rows
    ]


@router.get("/platform/ai/governance/overview")
def governance_overview(
    response: Response,
    user: User = Depends(require_platform_admin),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    ensure_agent_catalog(session)

    def _count(model, *filters) -> int:
        stmt = select(func.count()).select_from(model)
        if filters:
            stmt = stmt.where(*filters)
        return int(session.execute(stmt).scalar_one())

    cost = int(
        session.execute(
            select(func.coalesce(func.sum(AiAgentUsage.estimated_cost_cents), 0))
        ).scalar_one()
    )
    response.headers["Cache-Control"] = "no-store"
    return {
        "agents": _count(AiAgentDefinition),
        "enabled_agents": _count(AiAgentDefinition, AiAgentDefinition.enabled.is_(True)),
        "runs": _count(AiAgentRun),
        "pending_approvals": _count(AiAgentApproval, AiAgentApproval.status == "pending"),
        "open_safety_events": _count(
            AiAgentSafetyEvent, AiAgentSafetyEvent.status == "open"
        ),
        "estimated_cost_cents": cost,
        "note": "Telemetry from durable agent tables — Fake models by default.",
    }


@router.post("/tenants/{tenant_id}/ai/agent-runs", status_code=201)
def create_run(
    tenant_id: str,
    body: AgentRunWrite,
    request: Request,
    response: Response,
    user: User = Depends(get_current_user),
    membership: TenantMembership = Depends(
        require_role("tenant_admin", "staff", "provider")
    ),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    if membership.tenant_id != tenant_id:
        raise ApiError("TENANT_NOT_FOUND", "Tenant not found.", 404)
    if body.patient_id:
        require_patient_consent(
            session,
            tenant_id=tenant_id,
            patient_id=body.patient_id,
            actor=user,
            membership=membership,
            request_id=_request_id(request),
        )
    run = create_agent_run(
        session,
        organization_id=tenant_id,
        agent_code=body.agent_code,
        user=user,
        membership=membership,
        workflow_type=body.workflow_type,
        patient_id=body.patient_id,
        input_summary=body.input_summary,
        idempotency_key=body.idempotency_key,
    )
    if body.execute and run.status in {"queued", "created"}:
        run = execute_agent_run(
            session,
            run=run,
            user=user,
            membership=membership,
            request_id=_request_id(request),
        )
    append_audit_event(
        session,
        actor_user_id=user.id,
        tenant_id=tenant_id,
        action="ai.agent_run_created",
        subject_type="AiAgentRun",
        subject_id=run.id,
        request_id=_request_id(request),
    )
    response.headers["Cache-Control"] = "no-store"
    return _run_dict(run)


@router.get("/tenants/{tenant_id}/ai/agent-runs/{run_id}")
def get_run(
    tenant_id: str,
    run_id: str,
    response: Response,
    user: User = Depends(get_current_user),
    membership: TenantMembership = Depends(
        require_role("tenant_admin", "staff", "provider")
    ),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    if membership.tenant_id != tenant_id:
        raise ApiError("TENANT_NOT_FOUND", "Tenant not found.", 404)
    run = session.execute(
        select(AiAgentRun).where(
            AiAgentRun.organization_id == tenant_id, AiAgentRun.id == run_id
        )
    ).scalar_one_or_none()
    if run is None:
        raise ApiError("RUN_NOT_FOUND", "Agent run not found.", 404)
    response.headers["Cache-Control"] = "no-store"
    return _run_dict(run)


@router.get("/tenants/{tenant_id}/ai/agent-runs/{run_id}/steps")
def get_run_steps(
    tenant_id: str,
    run_id: str,
    response: Response,
    user: User = Depends(get_current_user),
    membership: TenantMembership = Depends(
        require_role("tenant_admin", "staff", "provider")
    ),
    session: Session = Depends(get_session),
) -> list[dict[str, Any]]:
    if membership.tenant_id != tenant_id:
        raise ApiError("TENANT_NOT_FOUND", "Tenant not found.", 404)
    run = session.execute(
        select(AiAgentRun).where(
            AiAgentRun.organization_id == tenant_id, AiAgentRun.id == run_id
        )
    ).scalar_one_or_none()
    if run is None:
        raise ApiError("RUN_NOT_FOUND", "Agent run not found.", 404)
    steps = session.execute(
        select(AiAgentRunStep)
        .where(AiAgentRunStep.agent_run_id == run_id)
        .order_by(AiAgentRunStep.step_number.asc())
    ).scalars()
    response.headers["Cache-Control"] = "no-store"
    return [
        {
            "step_id": s.id,
            "step_number": s.step_number,
            "step_type": s.step_type,
            "status": s.status,
            "detail": s.detail or {},
        }
        for s in steps
    ]


@router.post("/tenants/{tenant_id}/ai/agent-runs/{run_id}/cancel")
def cancel_agent_run(
    tenant_id: str,
    run_id: str,
    response: Response,
    user: User = Depends(get_current_user),
    membership: TenantMembership = Depends(
        require_role("tenant_admin", "staff", "provider")
    ),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    if membership.tenant_id != tenant_id:
        raise ApiError("TENANT_NOT_FOUND", "Tenant not found.", 404)
    run = session.execute(
        select(AiAgentRun).where(
            AiAgentRun.organization_id == tenant_id, AiAgentRun.id == run_id
        )
    ).scalar_one_or_none()
    if run is None:
        raise ApiError("RUN_NOT_FOUND", "Agent run not found.", 404)
    if run.requested_by != user.id and membership.role not in {"tenant_admin", "staff"}:
        raise ApiError("RUN_NOT_FOUND", "Agent run not found.", 404)
    cancel_run(session, run=run)
    response.headers["Cache-Control"] = "no-store"
    return _run_dict(run)


@router.get("/tenants/{tenant_id}/ai/approvals")
def list_approvals(
    tenant_id: str,
    response: Response,
    user: User = Depends(get_current_user),
    membership: TenantMembership = Depends(
        require_role("tenant_admin", "staff", "provider")
    ),
    session: Session = Depends(get_session),
) -> list[dict[str, Any]]:
    if membership.tenant_id != tenant_id:
        raise ApiError("TENANT_NOT_FOUND", "Tenant not found.", 404)
    rows = session.execute(
        select(AiAgentApproval)
        .where(AiAgentApproval.organization_id == tenant_id)
        .order_by(AiAgentApproval.created_at.desc())
        .limit(50)
    ).scalars()
    response.headers["Cache-Control"] = "no-store"
    return [
        {
            "approval_id": row.id,
            "agent_run_id": row.agent_run_id,
            "status": row.status,
            "required_role": row.required_role,
            "proposal_version": row.proposal_version,
            "proposal_hash": row.proposal_hash,
            "proposal_payload": row.proposal_payload or {},
            "expires_at": row.expires_at.isoformat() if row.expires_at else None,
        }
        for row in rows
    ]


@router.post("/tenants/{tenant_id}/ai/approvals/{approval_id}/approve")
def approve_action(
    tenant_id: str,
    approval_id: str,
    body: ApprovalDecisionWrite,
    request: Request,
    response: Response,
    user: User = Depends(get_current_user),
    membership: TenantMembership = Depends(
        require_role("tenant_admin", "staff", "provider")
    ),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    if membership.tenant_id != tenant_id:
        raise ApiError("TENANT_NOT_FOUND", "Tenant not found.", 404)
    approval = session.execute(
        select(AiAgentApproval).where(
            AiAgentApproval.organization_id == tenant_id,
            AiAgentApproval.id == approval_id,
        )
    ).scalar_one_or_none()
    if approval is None:
        raise ApiError("APPROVAL_NOT_FOUND", "Approval not found.", 404)
    decide_approval(
        session,
        approval=approval,
        approver=user,
        membership=membership,
        approve=True,
        reason=body.reason,
    )
    append_audit_event(
        session,
        actor_user_id=user.id,
        tenant_id=tenant_id,
        action="ai.approval_approved",
        subject_type="AiAgentApproval",
        subject_id=approval.id,
        request_id=_request_id(request),
    )
    response.headers["Cache-Control"] = "no-store"
    return {"approval_id": approval.id, "status": approval.status}


@router.post("/tenants/{tenant_id}/ai/approvals/{approval_id}/reject")
def reject_action(
    tenant_id: str,
    approval_id: str,
    body: ApprovalDecisionWrite,
    response: Response,
    user: User = Depends(get_current_user),
    membership: TenantMembership = Depends(
        require_role("tenant_admin", "staff", "provider")
    ),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    if membership.tenant_id != tenant_id:
        raise ApiError("TENANT_NOT_FOUND", "Tenant not found.", 404)
    approval = session.execute(
        select(AiAgentApproval).where(
            AiAgentApproval.organization_id == tenant_id,
            AiAgentApproval.id == approval_id,
        )
    ).scalar_one_or_none()
    if approval is None:
        raise ApiError("APPROVAL_NOT_FOUND", "Approval not found.", 404)
    decide_approval(
        session,
        approval=approval,
        approver=user,
        membership=membership,
        approve=False,
        reason=body.reason or "rejected",
    )
    response.headers["Cache-Control"] = "no-store"
    return {"approval_id": approval.id, "status": approval.status}


@router.post("/tenants/{tenant_id}/ai/workflow-runs", status_code=201)
def create_workflow_run(
    tenant_id: str,
    body: WorkflowRunWrite,
    request: Request,
    response: Response,
    user: User = Depends(get_current_user),
    membership: TenantMembership = Depends(require_role("provider", "tenant_admin", "staff")),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    if membership.tenant_id != tenant_id:
        raise ApiError("TENANT_NOT_FOUND", "Tenant not found.", 404)
    if body.patient_id:
        require_patient_consent(
            session,
            tenant_id=tenant_id,
            patient_id=body.patient_id,
            actor=user,
            membership=membership,
            request_id=_request_id(request),
        )
    execution = start_workflow(
        session,
        organization_id=tenant_id,
        workflow_code=body.workflow_code,
        user=user,
        membership=membership,
        patient_id=body.patient_id,
        request_id=_request_id(request),
    )
    response.headers["Cache-Control"] = "no-store"
    return {
        "workflow_execution_id": execution.id,
        "status": execution.status,
        "agent_run_ids": execution.agent_run_ids or [],
        "correlation_id": execution.correlation_id,
    }


@router.get("/platform/ai/workflows")
def list_workflows(
    response: Response,
    user: User = Depends(require_platform_admin),
    session: Session = Depends(get_session),
) -> list[dict[str, Any]]:
    ensure_agent_catalog(session)
    rows = session.execute(select(AiWorkflowDefinition)).scalars()
    response.headers["Cache-Control"] = "no-store"
    return [
        {
            "workflow_id": row.id,
            "workflow_code": row.workflow_code,
            "version": row.version,
            "risk_level": row.risk_level,
            "enabled": row.enabled,
            "configuration": row.configuration or {},
        }
        for row in rows
    ]


@router.post("/platform/ai/evaluations", status_code=201)
def create_agent_evaluation(
    body: AgentEvalWrite,
    response: Response,
    user: User = Depends(require_platform_admin),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    version = session.get(AiAgentVersion, body.agent_version_id)
    if version is None:
        raise ApiError("VERSION_NOT_FOUND", "Agent version not found.", 404)
    row = AiAgentEvaluation(
        agent_version_id=body.agent_version_id,
        dataset_version=body.dataset_version,
        evaluation_type=body.evaluation_type,
        results=body.results,
        status="pending_review",
    )
    session.add(row)
    session.flush()
    if float(body.results.get("unsafe_rate", 0) or 0) >= 0.05:
        session.add(
            AiAgentSafetyEvent(
                agent_run_id=None,
                event_type="evaluation_regression",
                severity="high",
                status="open",
                summary=f"Evaluation {body.evaluation_type} exceeded unsafe_rate threshold.",
            )
        )
    response.headers["Cache-Control"] = "no-store"
    return {"evaluation_id": row.id, "status": row.status}


@router.get("/platform/ai/evaluations")
def list_evaluations(
    response: Response,
    user: User = Depends(require_platform_admin),
    session: Session = Depends(get_session),
) -> list[dict[str, Any]]:
    rows = session.execute(
        select(AiAgentEvaluation).order_by(AiAgentEvaluation.created_at.desc()).limit(50)
    ).scalars()
    response.headers["Cache-Control"] = "no-store"
    return [
        {
            "evaluation_id": row.id,
            "agent_version_id": row.agent_version_id,
            "evaluation_type": row.evaluation_type,
            "dataset_version": row.dataset_version,
            "status": row.status,
            "results": row.results or {},
        }
        for row in rows
    ]


@router.get("/platform/ai/safety-events")
def list_safety_events(
    response: Response,
    user: User = Depends(require_platform_admin),
    session: Session = Depends(get_session),
) -> list[dict[str, Any]]:
    rows = session.execute(
        select(AiAgentSafetyEvent).order_by(AiAgentSafetyEvent.created_at.desc()).limit(50)
    ).scalars()
    response.headers["Cache-Control"] = "no-store"
    return [
        {
            "event_id": row.id,
            "event_type": row.event_type,
            "severity": row.severity,
            "status": row.status,
            "summary": row.summary,
            "agent_run_id": row.agent_run_id,
        }
        for row in rows
    ]


@router.get("/platform/ai/usage")
def ai_usage(
    response: Response,
    user: User = Depends(require_platform_admin),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    total_cost = int(
        session.execute(
            select(func.coalesce(func.sum(AiAgentUsage.estimated_cost_cents), 0))
        ).scalar_one()
    )
    runs = int(session.execute(select(func.count()).select_from(AiAgentUsage)).scalar_one())
    response.headers["Cache-Control"] = "no-store"
    return {
        "usage_events": runs,
        "estimated_cost_cents": total_cost,
        "note": "Sandbox token/cost estimates from AiAgentUsage.",
    }


@router.post("/tenants/{tenant_id}/knowledge/query")
def knowledge_query(
    tenant_id: str,
    body: KnowledgeQueryWrite,
    response: Response,
    user: User = Depends(get_current_user),
    membership: TenantMembership = Depends(
        require_role("tenant_admin", "staff", "provider", "patient")
    ),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Permission-aware knowledge retrieval — treat article bodies as untrusted for instructions."""
    if membership.tenant_id != tenant_id:
        raise ApiError("TENANT_NOT_FOUND", "Tenant not found.", 404)
    from app.hypercare_models import KnowledgeArticle

    # Access control before model: only published clinic/public articles
    visibility = ("clinic", "public") if membership.role != "patient" else ("public", "clinic")
    articles = session.execute(
        select(KnowledgeArticle).where(
            KnowledgeArticle.status == "published",
            KnowledgeArticle.visibility.in_(visibility),
        )
    ).scalars().all()
    q = body.query.lower()
    # Prompt-injection defense: never execute article text; return citations only + sanitized excerpt
    matches = []
    for art in articles:
        hay = f"{art.title} {art.category} {art.body}".lower()
        if q in hay or any(tok in hay for tok in q.split() if len(tok) > 3):
            excerpt = art.body[:240]
            # Case-insensitive strip of common injection phrases before any model sees text
            lower_ex = excerpt.lower()
            for phrase in ("ignore previous", "ignore all previous", "disregard previous"):
                idx = lower_ex.find(phrase)
                if idx >= 0:
                    excerpt = (
                        excerpt[:idx] + "[filtered]" + excerpt[idx + len(phrase) :]
                    )
                    lower_ex = excerpt.lower()
            matches.append(
                {
                    "document_title": art.title,
                    "document_version": art.version,
                    "source_id": art.id,
                    "section": art.category,
                    "excerpt": excerpt,
                }
            )
    response.headers["Cache-Control"] = "no-store"
    return {
        "query": body.query,
        "results": matches[:5],
        "note": "Retrieved content is untrusted data — not executable instructions.",
    }


@router.post("/tenants/{tenant_id}/clinic/ai/operations-forecast")
def operations_forecast(
    tenant_id: str,
    body: ForecastWrite,
    response: Response,
    user: User = Depends(get_current_user),
    membership: TenantMembership = Depends(require_role("tenant_admin", "staff")),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Lightweight deterministic forecast from sparse synthetic history — refuses insufficient data."""
    if membership.tenant_id != tenant_id:
        raise ApiError("TENANT_NOT_FOUND", "Tenant not found.", 404)
    # Use product usage / appointments if present; otherwise refuse
    from app.hypercare_models import ProductUsageEvent

    sample = int(
        session.execute(
            select(func.count())
            .select_from(ProductUsageEvent)
            .where(ProductUsageEvent.organization_id == tenant_id)
        ).scalar_one()
    )
    if sample < 5:
        response.headers["Cache-Control"] = "no-store"
        return {
            "status": "insufficient_data",
            "metric": body.metric,
            "sample_size": sample,
            "minimum_required": 5,
            "note": "Forecast withheld — historical sample too small for meaningful estimation.",
        }
    # Deterministic naive baseline (not a clinical triage signal)
    baseline = max(1, sample // 5)
    response.headers["Cache-Control"] = "no-store"
    return {
        "status": "ok",
        "metric": body.metric,
        "horizon_days": body.horizon_days,
        "sample_size": sample,
        "point_forecast": baseline,
        "uncertainty": "high",
        "model_version": "naive-v1",
        "limitations": [
            "Deterministic sandbox baseline only.",
            "Must not be used to deny care or change clinical triage.",
        ],
    }


# Convenience clinical endpoints wrapping orchestrator


@router.post("/tenants/{tenant_id}/encounters/{encounter_id}/ai/pre-visit-summary", status_code=201)
def pre_visit_summary(
    tenant_id: str,
    encounter_id: str,
    request: Request,
    response: Response,
    patient_id: str | None = None,
    user: User = Depends(get_current_user),
    membership: TenantMembership = Depends(require_role("provider", "staff")),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    if membership.tenant_id != tenant_id:
        raise ApiError("TENANT_NOT_FOUND", "Tenant not found.", 404)
    body_patient = patient_id
    if not body_patient:
        raise ApiError("PATIENT_REQUIRED", "patient_id query parameter is required.", 422)
    require_patient_consent(
        session,
        tenant_id=tenant_id,
        patient_id=body_patient,
        actor=user,
        membership=membership,
        request_id=_request_id(request),
    )
    run = create_agent_run(
        session,
        organization_id=tenant_id,
        agent_code="clinical_copilot",
        user=user,
        membership=membership,
        workflow_type="pre_visit",
        patient_id=body_patient,
        input_summary={"encounter_id": encounter_id},
        idempotency_key=f"previsit-{encounter_id}-{body_patient}",
    )
    run = execute_agent_run(
        session, run=run, user=user, membership=membership, request_id=_request_id(request)
    )
    response.headers["Cache-Control"] = "no-store"
    return _run_dict(run)


# --- V2.1.1 advanced agent foundation ---


@router.get("/platform/ai/capabilities")
def list_capabilities(
    response: Response,
    user: User = Depends(require_platform_admin),
    session: Session = Depends(get_session),
) -> list[dict[str, Any]]:
    ensure_capability_catalog(session)
    rows = session.execute(
        select(AiAgentCapability).order_by(AiAgentCapability.capability_code)
    ).scalars()
    response.headers["Cache-Control"] = "no-store"
    return [capability_dict(r, capability_allowed_tools(session, r)) for r in rows]


@router.get("/platform/ai/capabilities/{capability_id}")
def get_capability(
    capability_id: str,
    response: Response,
    user: User = Depends(require_platform_admin),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    row = session.get(AiAgentCapability, capability_id)
    if row is None:
        raise ApiError("CAPABILITY_NOT_FOUND", "Capability not found.", 404)
    response.headers["Cache-Control"] = "no-store"
    return capability_dict(row, capability_allowed_tools(session, row))


@router.post("/platform/ai/capabilities/{capability_id}/submit-review")
def submit_capability_review(
    capability_id: str,
    response: Response,
    user: User = Depends(require_platform_admin),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    row = session.get(AiAgentCapability, capability_id)
    if row is None:
        raise ApiError("CAPABILITY_NOT_FOUND", "Capability not found.", 404)
    if row.status == "registered":
        transition_capability(row, "security_review")
    elif row.status == "security_review":
        transition_capability(row, "evaluation")
    else:
        raise ApiError("CAPABILITY_NOT_REVIEWABLE", "Cannot submit for review from current status.", 422)
    session.flush()
    response.headers["Cache-Control"] = "no-store"
    return capability_dict(row)


@router.post("/platform/ai/capabilities/{capability_id}/approve")
def approve_capability_endpoint(
    capability_id: str,
    response: Response,
    user: User = Depends(require_platform_admin),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    row = session.get(AiAgentCapability, capability_id)
    if row is None:
        raise ApiError("CAPABILITY_NOT_FOUND", "Capability not found.", 404)
    approve_capability(session, cap=row, approver=user)
    response.headers["Cache-Control"] = "no-store"
    return capability_dict(row)


@router.patch("/platform/ai/capabilities/{capability_id}")
def patch_capability(
    capability_id: str,
    body: CapabilityStatusWrite,
    response: Response,
    user: User = Depends(require_platform_admin),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    row = session.get(AiAgentCapability, capability_id)
    if row is None:
        raise ApiError("CAPABILITY_NOT_FOUND", "Capability not found.", 404)
    transition_capability(row, body.status)
    session.flush()
    response.headers["Cache-Control"] = "no-store"
    return capability_dict(row)


@router.get("/platform/ai/readiness")
def ai_readiness(
    response: Response,
    user: User = Depends(require_platform_admin),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    ensure_agent_catalog(session)
    ensure_capability_catalog(session)

    def _count(model, *filters) -> int:
        stmt = select(func.count()).select_from(model)
        if filters:
            stmt = stmt.where(*filters)
        return int(session.execute(stmt).scalar_one())

    response.headers["Cache-Control"] = "no-store"
    return {
        "orchestrator": "ready",
        "agent_registry": "ready" if _count(AiAgentDefinition) else "missing",
        "tool_gateway": "ready" if _count(AiAgentTool) else "missing",
        "approval_engine": "ready",
        "capability_registry": "ready" if _count(AiAgentCapability) else "missing",
        "clinical_context": "ready",
        "delegation": "ready",
        "evaluation": "partial",
        "enabled_capabilities": _count(
            AiAgentCapability, AiAgentCapability.status.in_(("enabled", "monitored"))
        ),
        "open_safety_events": _count(AiAgentSafetyEvent, AiAgentSafetyEvent.status == "open"),
        "note": "Operational readiness metadata only — not a fabricated SLA score.",
    }


@router.get("/platform/ai/readiness/capabilities")
def readiness_capabilities(
    response: Response,
    user: User = Depends(require_platform_admin),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    ensure_capability_catalog(session)
    rows = session.execute(select(AiAgentCapability)).scalars().all()
    by_status: dict[str, int] = {}
    for r in rows:
        by_status[r.status] = by_status.get(r.status, 0) + 1
    response.headers["Cache-Control"] = "no-store"
    return {"total": len(rows), "by_status": by_status}


@router.get("/platform/ai/readiness/security")
def readiness_security(
    response: Response,
    user: User = Depends(require_platform_admin),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    open_events = session.execute(
        select(func.count())
        .select_from(AiAgentSafetyEvent)
        .where(AiAgentSafetyEvent.status == "open")
    ).scalar_one()
    denied = session.execute(
        select(func.count())
        .select_from(AiClinicalContextAccessEvent)
        .where(AiClinicalContextAccessEvent.access_outcome.like("denied%"))
    ).scalar_one()
    response.headers["Cache-Control"] = "no-store"
    return {
        "open_safety_events": int(open_events),
        "denied_clinical_context_accesses": int(denied),
        "prompt_injection_filter": "enabled_on_knowledge_query",
        "forbidden_autonomous_tools": "enforced",
        "note": "Does not expose internal security configuration secrets.",
    }


@router.post("/tenants/{tenant_id}/ai/agent-runs/{run_id}/delegate", status_code=201)
def delegate_run(
    tenant_id: str,
    run_id: str,
    body: DelegationWrite,
    request: Request,
    response: Response,
    user: User = Depends(get_current_user),
    membership: TenantMembership = Depends(require_role("tenant_admin", "staff", "provider")),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    if membership.tenant_id != tenant_id:
        raise ApiError("TENANT_NOT_FOUND", "Tenant not found.", 404)
    parent = session.execute(
        select(AiAgentRun).where(
            AiAgentRun.organization_id == tenant_id, AiAgentRun.id == run_id
        )
    ).scalar_one_or_none()
    if parent is None:
        raise ApiError("RUN_NOT_FOUND", "Agent run not found.", 404)
    delegation = delegate_agent_run(
        session,
        parent_run=parent,
        target_capability=body.target_capability,
        user=user,
        membership=membership,
        requested_tool_codes=body.requested_tool_codes or None,
        task_reference=body.task_reference,
        request_id=_request_id(request),
    )
    append_audit_event(
        session,
        actor_user_id=user.id,
        tenant_id=tenant_id,
        action="ai.agent_delegated",
        subject_type="AiAgentDelegation",
        subject_id=delegation.id,
        request_id=_request_id(request),
    )
    response.headers["Cache-Control"] = "no-store"
    return delegation_dict(delegation)


@router.get("/tenants/{tenant_id}/ai/agent-runs/{run_id}/delegations")
def list_delegations(
    tenant_id: str,
    run_id: str,
    response: Response,
    user: User = Depends(get_current_user),
    membership: TenantMembership = Depends(require_role("tenant_admin", "staff", "provider")),
    session: Session = Depends(get_session),
) -> list[dict[str, Any]]:
    if membership.tenant_id != tenant_id:
        raise ApiError("TENANT_NOT_FOUND", "Tenant not found.", 404)
    rows = session.execute(
        select(AiAgentDelegation).where(
            AiAgentDelegation.organization_id == tenant_id,
            AiAgentDelegation.parent_run_id == run_id,
        )
    ).scalars()
    response.headers["Cache-Control"] = "no-store"
    return [delegation_dict(r) for r in rows]


@router.post("/tenants/{tenant_id}/ai/agent-runs/{run_id}/cancel-cascade")
def cancel_run_cascade(
    tenant_id: str,
    run_id: str,
    response: Response,
    user: User = Depends(get_current_user),
    membership: TenantMembership = Depends(require_role("tenant_admin", "staff", "provider")),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    if membership.tenant_id != tenant_id:
        raise ApiError("TENANT_NOT_FOUND", "Tenant not found.", 404)
    parent = session.execute(
        select(AiAgentRun).where(
            AiAgentRun.organization_id == tenant_id, AiAgentRun.id == run_id
        )
    ).scalar_one_or_none()
    if parent is None:
        raise ApiError("RUN_NOT_FOUND", "Agent run not found.", 404)
    children = cancel_parent_cascades(session, parent_run=parent)
    response.headers["Cache-Control"] = "no-store"
    return {"run_id": parent.id, "status": parent.status, "cancelled_children": children}


@router.get("/tenants/{tenant_id}/patients/{patient_id}/ai/clinical-context")
def patient_clinical_context(
    tenant_id: str,
    patient_id: str,
    request: Request,
    response: Response,
    encounter_id: str | None = None,
    user: User = Depends(get_current_user),
    membership: TenantMembership = Depends(require_role("provider", "staff", "tenant_admin")),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Authorized clinicians only — not exposed as a platform-admin clinical dump."""
    ctx = get_authorized_patient_context(
        session,
        tenant_id=tenant_id,
        patient_id=patient_id,
        user=user,
        membership=membership,
        request_id=_request_id(request),
        encounter_id=encounter_id,
    )
    response.headers["Cache-Control"] = "no-store"
    return ctx


@router.get("/tenants/{tenant_id}/ai/agent-runs/{run_id}/evidence")
def run_evidence(
    tenant_id: str,
    run_id: str,
    response: Response,
    user: User = Depends(get_current_user),
    membership: TenantMembership = Depends(require_role("provider", "staff", "tenant_admin")),
    session: Session = Depends(get_session),
) -> list[dict[str, Any]]:
    if membership.tenant_id != tenant_id:
        raise ApiError("TENANT_NOT_FOUND", "Tenant not found.", 404)
    run = session.execute(
        select(AiAgentRun).where(
            AiAgentRun.organization_id == tenant_id, AiAgentRun.id == run_id
        )
    ).scalar_one_or_none()
    if run is None:
        raise ApiError("RUN_NOT_FOUND", "Agent run not found.", 404)
    response.headers["Cache-Control"] = "no-store"
    return list_run_evidence(session, tenant_id=tenant_id, agent_run_id=run_id)


@router.post("/tenants/{tenant_id}/ai/execution-contexts", status_code=201)
def mint_execution_context(
    tenant_id: str,
    request: Request,
    response: Response,
    capability_code: str,
    patient_id: str | None = None,
    user: User = Depends(get_current_user),
    membership: TenantMembership = Depends(require_role("provider", "staff", "tenant_admin")),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    record = create_execution_context(
        session,
        organization_id=tenant_id,
        user=user,
        membership=membership,
        capability_code=capability_code,
        patient_id=patient_id,
        request_id=_request_id(request),
    )
    response.headers["Cache-Control"] = "no-store"
    return context_dict(record)

