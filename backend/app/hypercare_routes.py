"""V1.9 platform hypercare, onboarding, customer success, analytics, compliance."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from fastapi import APIRouter, Depends, Request, Response
from pydantic import Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.audit import append_audit_event
from app.auth import ApiError, get_current_user
from app.authorization import require_role
from app.config import settings
from app.db import get_session
from app.hypercare_models import (
    AiEvaluationRun,
    AiOperationalMetric,
    ComplianceControlReview,
    ComplianceEvidenceRegistry,
    ContinuousImprovementItem,
    CustomerOnboardingTask,
    CustomerOnboardingWorkflow,
    CustomerSuccessProfile,
    CustomerSuccessTask,
    KnowledgeArticle,
    OperationalAutomationRule,
    OperationalAutomationRun,
    OperationalIncident,
    OperationalIncidentEvent,
    ProductUsageEvent,
    SupportTicketEvent,
)
from app.interop_models import IntegrationConnection, IntegrationJob, IntegrationTransaction
from app.models import Tenant, TenantMembership, User, new_id, utcnow
from app.ops_models import SupportTicket
from app.platform_routes import require_platform_admin
from app.rcm_models import OrganizationSubscription, PlatformBillingEvent, SubscriptionPlan
from app.schemas import StrictModel
from app.subscription_routes import ensure_default_plans

router = APIRouter(prefix="/api/v1", tags=["hypercare"])

# Documented synthetic SaaS list prices (cents / month) for sandbox MRR — not live billing.
PLAN_MRR_CENTS = {"starter": 4900, "professional": 9900, "enterprise": 24900}

ONBOARDING_TASKS = (
    ("org_profile", "Organization profile completed"),
    ("admin_verified", "Authorized administrator verified"),
    ("subscription_activated", "Subscription activated"),
    ("clinic_location", "Clinic location configured"),
    ("provider_profiles", "Provider profiles created"),
    ("staff_invited", "Staff invited"),
    ("permissions_reviewed", "Permissions reviewed"),
    ("ai_consent_reviewed", "AI consent settings reviewed"),
    ("telehealth_tested", "Telehealth configuration tested"),
    ("training_acknowledged", "Training acknowledged"),
    ("readiness_approved", "Launch readiness approved"),
)

HEALTH_SCORE_VERSION = "v1"


class IncidentWrite(StrictModel):
    environment: str = Field(default="development", max_length=32)
    organization_id: str | None = Field(default=None, max_length=36)
    category: str = Field(min_length=2, max_length=64)
    severity: str = Field(pattern="^(SEV-1|SEV-2|SEV-3|SEV-4)$")
    affected_service: str = Field(min_length=2, max_length=64)
    impact_summary: str = Field(default="", max_length=2000)


class IncidentUpdate(StrictModel):
    status: str | None = Field(
        default=None,
        pattern="^(open|investigating|mitigating|resolved|closed)$",
    )
    assigned_owner_id: str | None = Field(default=None, max_length=36)
    mitigation: str | None = Field(default=None, max_length=4000)
    resolution: str | None = Field(default=None, max_length=4000)
    root_cause: str | None = Field(default=None, max_length=4000)
    corrective_actions: str | None = Field(default=None, max_length=4000)


class OnboardingTaskUpdate(StrictModel):
    status: str = Field(pattern="^(pending|in_progress|blocked|completed)$")


class CsTaskWrite(StrictModel):
    organization_id: str = Field(min_length=36, max_length=36)
    task_type: str = Field(min_length=2, max_length=64)
    notes: str = Field(default="", max_length=2000)
    assigned_to: str | None = Field(default=None, max_length=36)


class AiEvalWrite(StrictModel):
    capability: str = Field(min_length=2, max_length=64)
    model_id: str = Field(default="fake", max_length=120)
    prompt_version: str = Field(default="1", max_length=32)
    dataset_version: str = Field(default="synthetic-v1", max_length=32)
    results: dict[str, Any] = Field(default_factory=dict)


class ComplianceReviewWrite(StrictModel):
    control_code: str = Field(min_length=2, max_length=64)
    organization_scope: str = Field(default="platform", max_length=64)
    notes: str = Field(default="", max_length=2000)


class AutomationRuleWrite(StrictModel):
    rule_code: str = Field(min_length=2, max_length=64)
    trigger_type: str = Field(min_length=2, max_length=64)
    action_type: str = Field(min_length=2, max_length=64)
    approval_required: bool = True
    enabled: bool = True


class AutomationRunWrite(StrictModel):
    source_event_id: str = Field(min_length=2, max_length=128)
    approved: bool = False


class ImprovementWrite(StrictModel):
    source_type: str = Field(min_length=2, max_length=64)
    source_reference: str = Field(default="", max_length=128)
    title: str = Field(min_length=3, max_length=200)
    priority: str = Field(default="normal", pattern="^(low|normal|high|critical)$")


def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", "")


def _incident_number(session: Session) -> str:
    count = int(session.execute(select(func.count()).select_from(OperationalIncident)).scalar_one())
    return f"INC-{count + 1:05d}"


def _add_incident_event(
    session: Session, *, incident_id: str, event_type: str, actor_id: str | None, summary: str
) -> None:
    session.add(
        OperationalIncidentEvent(
            incident_id=incident_id,
            event_type=event_type,
            actor_id=actor_id,
            event_summary=summary,
        )
    )


def _compute_health(session: Session, *, organization_id: str) -> tuple[int, dict[str, Any]]:
    """Explainable, versioned customer health — not a clinical score."""
    factors: dict[str, Any] = {"version": HEALTH_SCORE_VERSION}
    score = 40
    onboarding = session.execute(
        select(CustomerOnboardingWorkflow).where(
            CustomerOnboardingWorkflow.organization_id == organization_id
        )
    ).scalar_one_or_none()
    if onboarding and onboarding.status == "activated":
        score += 25
        factors["onboarding"] = "activated (+25)"
    elif onboarding and onboarding.status in {"ready_for_review", "approved"}:
        score += 15
        factors["onboarding"] = f"{onboarding.status} (+15)"
    else:
        factors["onboarding"] = "incomplete (+0)"

    sub = session.execute(
        select(OrganizationSubscription)
        .where(
            OrganizationSubscription.tenant_id == organization_id,
            OrganizationSubscription.status == "active",
        )
        .order_by(OrganizationSubscription.created_at.desc())
    ).scalars().first()
    if sub:
        score += 20
        factors["subscription"] = "active (+20)"
    else:
        factors["subscription"] = "inactive (+0)"

    open_tickets = int(
        session.execute(
            select(func.count())
            .select_from(SupportTicket)
            .where(
                SupportTicket.tenant_id == organization_id,
                SupportTicket.status.notin_(("resolved", "closed")),
            )
        ).scalar_one()
    )
    if open_tickets == 0:
        score += 10
        factors["support"] = "no open tickets (+10)"
    elif open_tickets <= 2:
        score += 5
        factors["support"] = f"{open_tickets} open (+5)"
    else:
        score -= 10
        factors["support"] = f"{open_tickets} open (-10)"

    open_incidents = int(
        session.execute(
            select(func.count())
            .select_from(OperationalIncident)
            .where(
                OperationalIncident.organization_id == organization_id,
                OperationalIncident.status.in_(("open", "investigating", "mitigating")),
                OperationalIncident.severity.in_(("SEV-1", "SEV-2")),
            )
        ).scalar_one()
    )
    if open_incidents:
        score -= 20
        factors["critical_incidents"] = f"{open_incidents} open (-20)"
    else:
        factors["critical_incidents"] = "none (+0)"

    score = max(0, min(100, score))
    factors["score"] = score
    return score, factors


# --- Command center ---


@router.get("/platform/operations/overview")
def operations_overview(
    response: Response,
    user: User = Depends(require_platform_admin),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    def _count(model, *filters) -> int:
        stmt = select(func.count()).select_from(model)
        if filters:
            stmt = stmt.where(*filters)
        return int(session.execute(stmt).scalar_one())

    open_incidents = _count(
        OperationalIncident,
        OperationalIncident.status.in_(("open", "investigating", "mitigating")),
    )
    response.headers["Cache-Control"] = "no-store"
    return {
        "environment": settings.environment,
        "launch_mode": settings.launch_mode,
        "deployment_version": "1.9.0",
        "launch_state": "development_only"
        if settings.launch_mode in {"development", "staging"}
        else settings.launch_mode,
        "note": "Telemetry from live application tables — not invented production SLAs.",
        "application_availability": "process_up",
        "database_health": "reachable",
        "open_incidents": open_incidents,
        "sev1_open": _count(
            OperationalIncident,
            OperationalIncident.severity == "SEV-1",
            OperationalIncident.status.in_(("open", "investigating", "mitigating")),
        ),
        "integration_connections": _count(IntegrationConnection),
        "integration_failed": _count(
            IntegrationTransaction, IntegrationTransaction.status == "failed"
        ),
        "jobs_queued": _count(IntegrationJob, IntegrationJob.status == "queued"),
        "support_open": _count(
            SupportTicket, SupportTicket.status.notin_(("resolved", "closed"))
        ),
        "active_subscriptions": _count(
            OrganizationSubscription, OrganizationSubscription.status == "active"
        ),
        "ai_failures_24h": _count(
            AiOperationalMetric,
            AiOperationalMetric.processing_status == "failed",
            AiOperationalMetric.occurred_at >= utcnow() - timedelta(hours=24),
        ),
    }


@router.get("/platform/operations/service-health")
def service_health(
    response: Response,
    user: User = Depends(require_platform_admin),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    response.headers["Cache-Control"] = "no-store"
    return {
        "frontend": {"status": "unknown_external", "note": "Wire RUM/Core Web Vitals in hosting."},
        "backend": {"status": "up", "rate_limit_enabled": settings.api_rate_limit_enabled},
        "database": {"status": "reachable"},
        "background_workers": {
            "queued_jobs": int(
                session.execute(
                    select(func.count())
                    .select_from(IntegrationJob)
                    .where(IntegrationJob.status == "queued")
                ).scalar_one()
            )
        },
        "integrations": {
            "connections": int(
                session.execute(select(func.count()).select_from(IntegrationConnection)).scalar_one()
            ),
            "failed_transactions": int(
                session.execute(
                    select(func.count())
                    .select_from(IntegrationTransaction)
                    .where(IntegrationTransaction.status == "failed")
                ).scalar_one()
            ),
        },
    }


@router.get("/platform/operations/incidents")
def list_incidents(
    response: Response,
    user: User = Depends(require_platform_admin),
    session: Session = Depends(get_session),
) -> list[dict[str, Any]]:
    rows = session.execute(
        select(OperationalIncident).order_by(OperationalIncident.detected_at.desc()).limit(100)
    ).scalars()
    response.headers["Cache-Control"] = "no-store"
    return [
        {
            "incident_id": row.id,
            "incident_number": row.incident_number,
            "environment": row.environment,
            "organization_id": row.organization_id,
            "category": row.category,
            "severity": row.severity,
            "status": row.status,
            "affected_service": row.affected_service,
            "impact_summary": row.impact_summary,
            "assigned_owner_id": row.assigned_owner_id,
            "detected_at": row.detected_at.isoformat(),
            "resolved_at": row.resolved_at.isoformat() if row.resolved_at else None,
        }
        for row in rows
    ]


@router.post("/platform/operations/incidents", status_code=201)
def create_incident(
    body: IncidentWrite,
    request: Request,
    response: Response,
    user: User = Depends(require_platform_admin),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    row = OperationalIncident(
        environment=body.environment or settings.environment,
        organization_id=body.organization_id,
        incident_number=_incident_number(session),
        category=body.category,
        severity=body.severity,
        status="open",
        affected_service=body.affected_service,
        impact_summary=body.impact_summary,
        assigned_owner_id=user.id,
    )
    session.add(row)
    session.flush()
    _add_incident_event(
        session,
        incident_id=row.id,
        event_type="created",
        actor_id=user.id,
        summary=f"Incident {row.incident_number} opened ({row.severity}).",
    )
    append_audit_event(
        session,
        actor_user_id=user.id,
        tenant_id=body.organization_id,
        action="ops.incident_created",
        subject_type="OperationalIncident",
        subject_id=row.id,
        request_id=_request_id(request),
    )
    # Safe automation: create improvement item for SEV-1/2
    if body.severity in {"SEV-1", "SEV-2"}:
        session.add(
            ContinuousImprovementItem(
                source_type="incident",
                source_reference=row.id,
                title=f"Remediate {row.incident_number}: {row.affected_service}",
                priority="critical" if body.severity == "SEV-1" else "high",
                status="identified",
            )
        )
    response.headers["Cache-Control"] = "no-store"
    return {"incident_id": row.id, "incident_number": row.incident_number, "status": row.status}


@router.get("/platform/operations/incidents/{incident_id}")
def get_incident(
    incident_id: str,
    response: Response,
    user: User = Depends(require_platform_admin),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    row = session.get(OperationalIncident, incident_id)
    if row is None:
        raise ApiError("INCIDENT_NOT_FOUND", "Incident not found.", 404)
    events = session.execute(
        select(OperationalIncidentEvent)
        .where(OperationalIncidentEvent.incident_id == incident_id)
        .order_by(OperationalIncidentEvent.occurred_at.asc())
    ).scalars()
    response.headers["Cache-Control"] = "no-store"
    return {
        "incident_id": row.id,
        "incident_number": row.incident_number,
        "environment": row.environment,
        "organization_id": row.organization_id,
        "category": row.category,
        "severity": row.severity,
        "status": row.status,
        "affected_service": row.affected_service,
        "impact_summary": row.impact_summary,
        "mitigation": row.mitigation,
        "resolution": row.resolution,
        "root_cause": row.root_cause,
        "corrective_actions": row.corrective_actions,
        "assigned_owner_id": row.assigned_owner_id,
        "detected_at": row.detected_at.isoformat(),
        "resolved_at": row.resolved_at.isoformat() if row.resolved_at else None,
        "events": [
            {
                "event_type": e.event_type,
                "summary": e.event_summary,
                "occurred_at": e.occurred_at.isoformat(),
            }
            for e in events
        ],
    }


@router.patch("/platform/operations/incidents/{incident_id}")
def update_incident(
    incident_id: str,
    body: IncidentUpdate,
    request: Request,
    response: Response,
    user: User = Depends(require_platform_admin),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    row = session.get(OperationalIncident, incident_id)
    if row is None:
        raise ApiError("INCIDENT_NOT_FOUND", "Incident not found.", 404)
    if body.status:
        row.status = body.status
        if body.status in {"resolved", "closed"} and row.resolved_at is None:
            row.resolved_at = utcnow()
    if body.assigned_owner_id is not None:
        row.assigned_owner_id = body.assigned_owner_id
    if body.mitigation is not None:
        row.mitigation = body.mitigation
    if body.resolution is not None:
        row.resolution = body.resolution
    if body.root_cause is not None:
        row.root_cause = body.root_cause
    if body.corrective_actions is not None:
        row.corrective_actions = body.corrective_actions
    session.flush()
    _add_incident_event(
        session,
        incident_id=row.id,
        event_type="updated",
        actor_id=user.id,
        summary=f"Incident updated to status={row.status}.",
    )
    response.headers["Cache-Control"] = "no-store"
    return {"incident_id": row.id, "status": row.status}


# --- Onboarding (tenant + platform) ---


@router.post("/tenants/{tenant_id}/onboarding/start", status_code=201)
def start_onboarding(
    tenant_id: str,
    request: Request,
    response: Response,
    user: User = Depends(get_current_user),
    membership: TenantMembership = Depends(require_role("tenant_admin")),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    if membership.tenant_id != tenant_id:
        raise ApiError("TENANT_NOT_FOUND", "Tenant not found.", 404)
    existing = session.execute(
        select(CustomerOnboardingWorkflow).where(
            CustomerOnboardingWorkflow.organization_id == tenant_id
        )
    ).scalar_one_or_none()
    if existing is not None:
        response.headers["Cache-Control"] = "no-store"
        return {
            "workflow_id": existing.id,
            "status": existing.status,
            "duplicate": True,
            "note": "Idempotent — existing onboarding workflow returned.",
        }
    workflow = CustomerOnboardingWorkflow(
        organization_id=tenant_id,
        status="in_progress",
        assigned_owner_id=user.id,
        started_at=utcnow(),
    )
    session.add(workflow)
    session.flush()
    for code, name in ONBOARDING_TASKS:
        session.add(
            CustomerOnboardingTask(
                organization_id=tenant_id,
                workflow_id=workflow.id,
                task_code=code,
                task_name=name,
                status="pending",
            )
        )
    profile = session.execute(
        select(CustomerSuccessProfile).where(
            CustomerSuccessProfile.organization_id == tenant_id
        )
    ).scalar_one_or_none()
    if profile is None:
        score, factors = _compute_health(session, organization_id=tenant_id)
        session.add(
            CustomerSuccessProfile(
                organization_id=tenant_id,
                lifecycle_stage="onboarding",
                health_score=score,
                health_score_version=HEALTH_SCORE_VERSION,
                health_factors=factors,
            )
        )
    append_audit_event(
        session,
        actor_user_id=user.id,
        tenant_id=tenant_id,
        action="onboarding.started",
        subject_type="CustomerOnboardingWorkflow",
        subject_id=workflow.id,
        request_id=_request_id(request),
    )
    response.headers["Cache-Control"] = "no-store"
    return {"workflow_id": workflow.id, "status": workflow.status, "duplicate": False}


@router.get("/tenants/{tenant_id}/onboarding")
def get_onboarding(
    tenant_id: str,
    response: Response,
    user: User = Depends(get_current_user),
    membership: TenantMembership = Depends(require_role("tenant_admin", "staff")),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    if membership.tenant_id != tenant_id:
        raise ApiError("TENANT_NOT_FOUND", "Tenant not found.", 404)
    workflow = session.execute(
        select(CustomerOnboardingWorkflow).where(
            CustomerOnboardingWorkflow.organization_id == tenant_id
        )
    ).scalar_one_or_none()
    if workflow is None:
        raise ApiError("ONBOARDING_NOT_FOUND", "Onboarding has not started.", 404)
    tasks = session.execute(
        select(CustomerOnboardingTask)
        .where(CustomerOnboardingTask.workflow_id == workflow.id)
        .order_by(CustomerOnboardingTask.task_code.asc())
    ).scalars().all()
    completed = sum(1 for t in tasks if t.status == "completed")
    response.headers["Cache-Control"] = "no-store"
    return {
        "workflow_id": workflow.id,
        "status": workflow.status,
        "progress": {"completed": completed, "total": len(tasks)},
        "tasks": [
            {
                "task_id": t.id,
                "task_code": t.task_code,
                "task_name": t.task_name,
                "status": t.status,
                "completed_at": t.completed_at.isoformat() if t.completed_at else None,
            }
            for t in tasks
        ],
    }


@router.patch("/tenants/{tenant_id}/onboarding/tasks/{task_id}")
def update_onboarding_task(
    tenant_id: str,
    task_id: str,
    body: OnboardingTaskUpdate,
    response: Response,
    user: User = Depends(get_current_user),
    membership: TenantMembership = Depends(require_role("tenant_admin", "staff")),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    if membership.tenant_id != tenant_id:
        raise ApiError("TENANT_NOT_FOUND", "Tenant not found.", 404)
    task = session.execute(
        select(CustomerOnboardingTask).where(
            CustomerOnboardingTask.organization_id == tenant_id,
            CustomerOnboardingTask.id == task_id,
        )
    ).scalar_one_or_none()
    if task is None:
        raise ApiError("TASK_NOT_FOUND", "Onboarding task not found.", 404)
    task.status = body.status
    if body.status == "completed":
        task.completed_at = utcnow()
    session.flush()
    workflow = session.get(CustomerOnboardingWorkflow, task.workflow_id)
    if workflow:
        tasks = session.execute(
            select(CustomerOnboardingTask).where(
                CustomerOnboardingTask.workflow_id == workflow.id
            )
        ).scalars().all()
        if all(t.status == "completed" for t in tasks):
            workflow.status = "ready_for_review"
        elif any(t.status == "blocked" for t in tasks):
            workflow.status = "blocked"
        else:
            workflow.status = "in_progress"
        session.flush()
    response.headers["Cache-Control"] = "no-store"
    return {"task_id": task.id, "status": task.status, "workflow_status": workflow.status if workflow else None}


@router.post("/tenants/{tenant_id}/onboarding/submit-review")
def submit_onboarding_review(
    tenant_id: str,
    request: Request,
    response: Response,
    user: User = Depends(get_current_user),
    membership: TenantMembership = Depends(require_role("tenant_admin")),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    if membership.tenant_id != tenant_id:
        raise ApiError("TENANT_NOT_FOUND", "Tenant not found.", 404)
    workflow = session.execute(
        select(CustomerOnboardingWorkflow).where(
            CustomerOnboardingWorkflow.organization_id == tenant_id
        )
    ).scalar_one_or_none()
    if workflow is None:
        raise ApiError("ONBOARDING_NOT_FOUND", "Onboarding has not started.", 404)
    if workflow.status not in {"ready_for_review", "approved", "activated"}:
        raise ApiError(
            "ONBOARDING_INCOMPLETE",
            "Complete all onboarding tasks before submitting for review.",
            422,
        )
    workflow.status = "ready_for_review"
    session.flush()
    response.headers["Cache-Control"] = "no-store"
    return {"workflow_id": workflow.id, "status": workflow.status}


@router.post("/platform/onboarding/{tenant_id}/activate")
def activate_clinic(
    tenant_id: str,
    request: Request,
    response: Response,
    user: User = Depends(require_platform_admin),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    workflow = session.execute(
        select(CustomerOnboardingWorkflow).where(
            CustomerOnboardingWorkflow.organization_id == tenant_id
        )
    ).scalar_one_or_none()
    if workflow is None:
        raise ApiError("ONBOARDING_NOT_FOUND", "Onboarding has not started.", 404)
    if workflow.status not in {"ready_for_review", "approved"}:
        raise ApiError(
            "ONBOARDING_NOT_READY",
            "Clinic activation requires readiness review completion.",
            422,
        )
    workflow.status = "activated"
    workflow.completed_at = utcnow()
    profile = session.execute(
        select(CustomerSuccessProfile).where(
            CustomerSuccessProfile.organization_id == tenant_id
        )
    ).scalar_one_or_none()
    score, factors = _compute_health(session, organization_id=tenant_id)
    if profile is None:
        profile = CustomerSuccessProfile(organization_id=tenant_id)
        session.add(profile)
    profile.lifecycle_stage = "activated"
    profile.health_score = score
    profile.health_score_version = HEALTH_SCORE_VERSION
    profile.health_factors = factors
    profile.last_reviewed_at = utcnow()
    session.flush()
    append_audit_event(
        session,
        actor_user_id=user.id,
        tenant_id=tenant_id,
        action="onboarding.activated",
        subject_type="CustomerOnboardingWorkflow",
        subject_id=workflow.id,
        request_id=_request_id(request),
    )
    response.headers["Cache-Control"] = "no-store"
    return {"workflow_id": workflow.id, "status": workflow.status, "health_score": score}


# --- Customer success ---


@router.get("/platform/customer-success/overview")
def cs_overview(
    response: Response,
    user: User = Depends(require_platform_admin),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    profiles = session.execute(select(CustomerSuccessProfile)).scalars().all()
    by_stage: dict[str, int] = {}
    for p in profiles:
        by_stage[p.lifecycle_stage] = by_stage.get(p.lifecycle_stage, 0) + 1
    response.headers["Cache-Control"] = "no-store"
    return {
        "customers": len(profiles),
        "by_lifecycle_stage": by_stage,
        "open_cs_tasks": int(
            session.execute(
                select(func.count())
                .select_from(CustomerSuccessTask)
                .where(CustomerSuccessTask.status == "open")
            ).scalar_one()
        ),
        "note": "Customer health is commercial/ops scoring — not clinical patient health.",
    }


@router.get("/platform/customer-success/organizations")
def cs_organizations(
    response: Response,
    user: User = Depends(require_platform_admin),
    session: Session = Depends(get_session),
) -> list[dict[str, Any]]:
    tenants = session.execute(select(Tenant).order_by(Tenant.created_at.desc()).limit(100)).scalars()
    ensure_default_plans(session)
    result = []
    for tenant in tenants:
        score, factors = _compute_health(session, organization_id=tenant.id)
        profile = session.execute(
            select(CustomerSuccessProfile).where(
                CustomerSuccessProfile.organization_id == tenant.id
            )
        ).scalar_one_or_none()
        sub = session.execute(
            select(OrganizationSubscription, SubscriptionPlan)
            .join(SubscriptionPlan, SubscriptionPlan.id == OrganizationSubscription.plan_id)
            .where(OrganizationSubscription.tenant_id == tenant.id)
            .order_by(OrganizationSubscription.created_at.desc())
        ).first()
        onboarding = session.execute(
            select(CustomerOnboardingWorkflow).where(
                CustomerOnboardingWorkflow.organization_id == tenant.id
            )
        ).scalar_one_or_none()
        result.append(
            {
                "organization_id": tenant.id,
                "display_name": tenant.display_name,
                "lifecycle_stage": profile.lifecycle_stage if profile else "prospect",
                "health_score": score,
                "health_score_version": HEALTH_SCORE_VERSION,
                "health_factors": factors,
                "onboarding_status": onboarding.status if onboarding else "not_started",
                "plan_code": sub[1].plan_code if sub else None,
                "subscription_status": sub[0].status if sub else None,
                "renewal_date": sub[0].billing_period_end.isoformat() if sub and sub[0].billing_period_end else None,
            }
        )
    response.headers["Cache-Control"] = "no-store"
    return result


@router.post("/platform/customer-success/tasks", status_code=201)
def create_cs_task(
    body: CsTaskWrite,
    response: Response,
    user: User = Depends(require_platform_admin),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    if session.get(Tenant, body.organization_id) is None:
        raise ApiError("TENANT_NOT_FOUND", "Organization not found.", 404)
    row = CustomerSuccessTask(
        organization_id=body.organization_id,
        task_type=body.task_type,
        notes=body.notes,
        assigned_to=body.assigned_to or user.id,
        due_at=utcnow() + timedelta(days=7),
    )
    session.add(row)
    session.flush()
    response.headers["Cache-Control"] = "no-store"
    return {"task_id": row.id, "status": row.status, "task_type": row.task_type}


@router.get("/platform/customer-success/tasks")
def list_cs_tasks(
    response: Response,
    user: User = Depends(require_platform_admin),
    session: Session = Depends(get_session),
) -> list[dict[str, Any]]:
    rows = session.execute(
        select(CustomerSuccessTask).order_by(CustomerSuccessTask.created_at.desc()).limit(100)
    ).scalars()
    response.headers["Cache-Control"] = "no-store"
    return [
        {
            "task_id": row.id,
            "organization_id": row.organization_id,
            "task_type": row.task_type,
            "status": row.status,
            "due_at": row.due_at.isoformat() if row.due_at else None,
        }
        for row in rows
    ]


# --- SaaS revenue (reconciled from subscriptions) ---


@router.get("/platform/analytics/revenue")
def saas_revenue(
    response: Response,
    user: User = Depends(require_platform_admin),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    ensure_default_plans(session)
    rows = session.execute(
        select(OrganizationSubscription, SubscriptionPlan)
        .join(SubscriptionPlan, SubscriptionPlan.id == OrganizationSubscription.plan_id)
        .where(OrganizationSubscription.status.in_(("active", "trial")))
    ).all()
    mrr = 0
    active = 0
    trial = 0
    by_plan: dict[str, int] = {}
    for sub, plan in rows:
        cents = PLAN_MRR_CENTS.get(plan.plan_code, 0)
        if sub.status == "trial":
            trial += 1
        else:
            active += 1
            mrr += cents
            by_plan[plan.plan_code] = by_plan.get(plan.plan_code, 0) + cents
    cancelled = int(
        session.execute(
            select(func.count())
            .select_from(OrganizationSubscription)
            .where(OrganizationSubscription.status == "cancelled")
        ).scalar_one()
    )
    billing_events = int(
        session.execute(select(func.count()).select_from(PlatformBillingEvent)).scalar_one()
    )
    response.headers["Cache-Control"] = "no-store"
    return {
        "mrr_cents": mrr,
        "arr_cents": mrr * 12,
        "active_subscriptions": active,
        "trial_subscriptions": trial,
        "cancelled_subscriptions": cancelled,
        "mrr_by_plan_cents": by_plan,
        "billing_events_recorded": billing_events,
        "methodology": {
            "mrr": "Sum of documented PLAN_MRR_CENTS for active (non-trial) subscriptions.",
            "arr": "MRR × 12 (annualization).",
            "source": "organization_subscriptions + subscription_plans (+ platform_billing_events count).",
            "note": "Sandbox list prices — not live payment processor settlement.",
        },
    }


@router.get("/platform/analytics/renewals")
def renewals(
    response: Response,
    user: User = Depends(require_platform_admin),
    session: Session = Depends(get_session),
) -> list[dict[str, Any]]:
    horizon = utcnow().date() + timedelta(days=45)
    rows = session.execute(
        select(OrganizationSubscription, SubscriptionPlan, Tenant)
        .join(SubscriptionPlan, SubscriptionPlan.id == OrganizationSubscription.plan_id)
        .join(Tenant, Tenant.id == OrganizationSubscription.tenant_id)
        .where(
            OrganizationSubscription.status == "active",
            OrganizationSubscription.billing_period_end.is_not(None),
            OrganizationSubscription.billing_period_end <= horizon,
        )
    ).all()
    response.headers["Cache-Control"] = "no-store"
    return [
        {
            "organization_id": tenant.id,
            "display_name": tenant.display_name,
            "plan_code": plan.plan_code,
            "renewal_date": sub.billing_period_end.isoformat() if sub.billing_period_end else None,
            "subscription_status": sub.status,
        }
        for sub, plan, tenant in rows
    ]


# --- AI ops ---


@router.get("/platform/ai-operations/overview")
def ai_ops_overview(
    response: Response,
    user: User = Depends(require_platform_admin),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    total = int(session.execute(select(func.count()).select_from(AiOperationalMetric)).scalar_one())
    failed = int(
        session.execute(
            select(func.count())
            .select_from(AiOperationalMetric)
            .where(AiOperationalMetric.processing_status == "failed")
        ).scalar_one()
    )
    cost = int(
        session.execute(
            select(func.coalesce(func.sum(AiOperationalMetric.estimated_cost_cents), 0))
        ).scalar_one()
    )
    evals = int(session.execute(select(func.count()).select_from(AiEvaluationRun)).scalar_one())
    response.headers["Cache-Control"] = "no-store"
    return {
        "requests": total,
        "failures": failed,
        "estimated_cost_cents": cost,
        "evaluation_runs": evals,
        "capabilities_tracked": [
            "document_intelligence",
            "lab_extraction",
            "medical_scribe",
            "clinical_copilot",
            "messaging_assist",
            "coding_assist",
        ],
        "note": "Metrics reflect recorded AiOperationalMetric rows (synthetic/fake models by default).",
    }


@router.post("/platform/ai-operations/metrics", status_code=201)
def record_ai_metric(
    body: dict[str, Any],
    response: Response,
    user: User = Depends(require_platform_admin),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    row = AiOperationalMetric(
        organization_id=body.get("organization_id"),
        capability=str(body.get("capability") or "unknown")[:64],
        model_identifier=str(body.get("model_identifier") or "fake")[:120],
        request_reference=str(body.get("request_reference") or new_id())[:128],
        processing_status=str(body.get("processing_status") or "success")[:24],
        latency_ms=int(body.get("latency_ms") or 0),
        usage_quantity=int(body.get("usage_quantity") or 0),
        estimated_cost_cents=int(body.get("estimated_cost_cents") or 0),
    )
    session.add(row)
    session.flush()
    response.headers["Cache-Control"] = "no-store"
    return {"metric_id": row.id, "processing_status": row.processing_status}


@router.post("/platform/ai-operations/evaluations", status_code=201)
def create_ai_evaluation(
    body: AiEvalWrite,
    response: Response,
    user: User = Depends(require_platform_admin),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    row = AiEvaluationRun(
        capability=body.capability,
        model_identifier=body.model_id,
        prompt_version=body.prompt_version,
        dataset_version=body.dataset_version,
        evaluation_status="pending_review",
        results=body.results,
        reviewed_by=None,
    )
    session.add(row)
    session.flush()
    if float(body.results.get("unsupported_rate", 0) or 0) >= 0.1:
        session.add(
            OperationalIncident(
                environment=settings.environment,
                incident_number=_incident_number(session),
                category="ai_quality",
                severity="SEV-3",
                status="open",
                affected_service=f"ai:{body.capability}",
                impact_summary="AI evaluation reported elevated unsupported output rate.",
                assigned_owner_id=user.id,
            )
        )
    response.headers["Cache-Control"] = "no-store"
    return {"evaluation_id": row.id, "evaluation_status": row.evaluation_status}


@router.get("/platform/ai-operations/evaluations")
def list_ai_evaluations(
    response: Response,
    user: User = Depends(require_platform_admin),
    session: Session = Depends(get_session),
) -> list[dict[str, Any]]:
    rows = session.execute(
        select(AiEvaluationRun).order_by(AiEvaluationRun.created_at.desc()).limit(50)
    ).scalars()
    response.headers["Cache-Control"] = "no-store"
    return [
        {
            "evaluation_id": row.id,
            "capability": row.capability,
            "model_identifier": row.model_identifier,
            "prompt_version": row.prompt_version,
            "dataset_version": row.dataset_version,
            "evaluation_status": row.evaluation_status,
            "results": row.results or {},
        }
        for row in rows
    ]


# --- Integration ops (reuse V1.7) ---


@router.get("/platform/integration-operations/overview")
def integration_ops_overview(
    response: Response,
    user: User = Depends(require_platform_admin),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    response.headers["Cache-Control"] = "no-store"
    return {
        "connections": int(
            session.execute(select(func.count()).select_from(IntegrationConnection)).scalar_one()
        ),
        "transactions": int(
            session.execute(select(func.count()).select_from(IntegrationTransaction)).scalar_one()
        ),
        "processed": int(
            session.execute(
                select(func.count())
                .select_from(IntegrationTransaction)
                .where(IntegrationTransaction.status == "processed")
            ).scalar_one()
        ),
        "failed": int(
            session.execute(
                select(func.count())
                .select_from(IntegrationTransaction)
                .where(IntegrationTransaction.status == "failed")
            ).scalar_one()
        ),
        "awaiting_review": int(
            session.execute(
                select(func.count())
                .select_from(IntegrationTransaction)
                .where(IntegrationTransaction.status == "awaiting_review")
            ).scalar_one()
        ),
        "note": "Counts from durable integration hub tables.",
    }


# --- Compliance ---


@router.post("/platform/compliance/reviews", status_code=201)
def create_compliance_review(
    body: ComplianceReviewWrite,
    response: Response,
    user: User = Depends(require_platform_admin),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    row = ComplianceControlReview(
        control_code=body.control_code,
        organization_scope=body.organization_scope,
        assigned_owner_id=user.id,
        review_status="open",
        due_at=utcnow() + timedelta(days=30),
        notes=body.notes,
    )
    session.add(row)
    session.flush()
    response.headers["Cache-Control"] = "no-store"
    return {"review_id": row.id, "control_code": row.control_code, "review_status": row.review_status}


@router.get("/platform/compliance/reviews")
def list_compliance_reviews(
    response: Response,
    user: User = Depends(require_platform_admin),
    session: Session = Depends(get_session),
) -> list[dict[str, Any]]:
    rows = session.execute(
        select(ComplianceControlReview).order_by(ComplianceControlReview.created_at.desc()).limit(100)
    ).scalars()
    response.headers["Cache-Control"] = "no-store"
    return [
        {
            "review_id": row.id,
            "control_code": row.control_code,
            "organization_scope": row.organization_scope,
            "review_status": row.review_status,
            "due_at": row.due_at.isoformat() if row.due_at else None,
        }
        for row in rows
    ]


@router.post("/platform/compliance/reviews/{review_id}/evidence", status_code=201)
def add_compliance_evidence(
    review_id: str,
    body: dict[str, str],
    response: Response,
    user: User = Depends(require_platform_admin),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    review = session.get(ComplianceControlReview, review_id)
    if review is None:
        raise ApiError("REVIEW_NOT_FOUND", "Compliance review not found.", 404)
    ref = (body.get("secure_artifact_reference") or "").strip()
    if not ref.startswith("secure://"):
        raise ApiError(
            "EVIDENCE_REF_INVALID",
            "Evidence must use a secure:// artifact reference (no public URLs).",
            422,
        )
    row = ComplianceEvidenceRegistry(
        control_review_id=review_id,
        evidence_type=body.get("evidence_type") or "document",
        secure_artifact_reference=ref,
    )
    session.add(row)
    session.flush()
    response.headers["Cache-Control"] = "no-store"
    return {"evidence_id": row.id, "secure_artifact_reference": row.secure_artifact_reference}


# --- Automation ---


@router.post("/platform/automations", status_code=201)
def create_automation_rule(
    body: AutomationRuleWrite,
    response: Response,
    user: User = Depends(require_platform_admin),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    # High-impact action types always require approval
    high_impact = body.action_type in {
        "disable_security_control",
        "modify_privileged_access",
        "delete_clinical_records",
        "issue_refund",
        "change_subscription",
    }
    row = OperationalAutomationRule(
        rule_code=body.rule_code,
        trigger_type=body.trigger_type,
        action_type=body.action_type,
        enabled=body.enabled,
        approval_required=True if high_impact else body.approval_required,
    )
    session.add(row)
    session.flush()
    response.headers["Cache-Control"] = "no-store"
    return {
        "rule_id": row.id,
        "rule_code": row.rule_code,
        "approval_required": row.approval_required,
    }


@router.get("/platform/automations")
def list_automations(
    response: Response,
    user: User = Depends(require_platform_admin),
    session: Session = Depends(get_session),
) -> list[dict[str, Any]]:
    rows = session.execute(select(OperationalAutomationRule)).scalars()
    response.headers["Cache-Control"] = "no-store"
    return [
        {
            "rule_id": row.id,
            "rule_code": row.rule_code,
            "trigger_type": row.trigger_type,
            "action_type": row.action_type,
            "enabled": row.enabled,
            "approval_required": row.approval_required,
        }
        for row in rows
    ]


@router.post("/platform/automations/{rule_id}/runs", status_code=201)
def run_automation(
    rule_id: str,
    body: AutomationRunWrite,
    response: Response,
    user: User = Depends(require_platform_admin),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    rule = session.get(OperationalAutomationRule, rule_id)
    if rule is None:
        raise ApiError("RULE_NOT_FOUND", "Automation rule not found.", 404)
    if not rule.enabled:
        raise ApiError("RULE_DISABLED", "Automation rule is disabled.", 422)
    existing = session.execute(
        select(OperationalAutomationRun).where(
            OperationalAutomationRun.rule_id == rule_id,
            OperationalAutomationRun.source_event_id == body.source_event_id,
        )
    ).scalar_one_or_none()
    if existing is not None:
        response.headers["Cache-Control"] = "no-store"
        return {
            "run_id": existing.id,
            "status": existing.status,
            "duplicate": True,
        }
    if rule.approval_required and not body.approved:
        run = OperationalAutomationRun(
            rule_id=rule_id,
            source_event_id=body.source_event_id,
            status="awaiting_approval",
            result_summary={"note": "High-impact or approval-gated action pending."},
        )
        session.add(run)
        session.flush()
        response.headers["Cache-Control"] = "no-store"
        return {"run_id": run.id, "status": run.status, "duplicate": False}
    # Safe actions only: notify/create ticket/create incident metadata — never clinical mutations
    if rule.action_type in {
        "disable_security_control",
        "modify_privileged_access",
        "delete_clinical_records",
        "issue_refund",
        "change_subscription",
        "send_clinical_advice",
    }:
        raise ApiError(
            "AUTOMATION_FORBIDDEN",
            "This automation action is not permitted without separate authorized workflow.",
            403,
        )
    run = OperationalAutomationRun(
        rule_id=rule_id,
        source_event_id=body.source_event_id,
        status="completed",
        executed_at=utcnow(),
        result_summary={"action": rule.action_type, "executed_by": user.id},
    )
    session.add(run)
    session.flush()
    response.headers["Cache-Control"] = "no-store"
    return {"run_id": run.id, "status": run.status, "duplicate": False}


# --- Knowledge base + improvements ---


@router.get("/support/knowledge")
def list_knowledge(
    response: Response,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> list[dict[str, Any]]:
    rows = session.execute(
        select(KnowledgeArticle).where(KnowledgeArticle.status == "published").limit(50)
    ).scalars()
    response.headers["Cache-Control"] = "no-store"
    return [
        {
            "article_id": row.id,
            "slug": row.slug,
            "title": row.title,
            "category": row.category,
            "visibility": row.visibility,
            "version": row.version,
        }
        for row in rows
    ]


@router.post("/platform/knowledge", status_code=201)
def create_knowledge(
    body: dict[str, str],
    response: Response,
    user: User = Depends(require_platform_admin),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    row = KnowledgeArticle(
        slug=body["slug"][:120],
        title=body["title"][:200],
        category=body.get("category") or "general",
        body=body.get("body") or "",
        visibility=body.get("visibility") or "clinic",
    )
    session.add(row)
    session.flush()
    response.headers["Cache-Control"] = "no-store"
    return {"article_id": row.id, "slug": row.slug}


@router.post("/platform/improvements", status_code=201)
def create_improvement(
    body: ImprovementWrite,
    response: Response,
    user: User = Depends(require_platform_admin),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    row = ContinuousImprovementItem(
        source_type=body.source_type,
        source_reference=body.source_reference,
        title=body.title,
        priority=body.priority,
        owner_id=user.id,
    )
    session.add(row)
    session.flush()
    response.headers["Cache-Control"] = "no-store"
    return {"improvement_id": row.id, "status": row.status, "priority": row.priority}


@router.get("/platform/improvements")
def list_improvements(
    response: Response,
    user: User = Depends(require_platform_admin),
    session: Session = Depends(get_session),
) -> list[dict[str, Any]]:
    rows = session.execute(
        select(ContinuousImprovementItem)
        .order_by(ContinuousImprovementItem.created_at.desc())
        .limit(100)
    ).scalars()
    response.headers["Cache-Control"] = "no-store"
    return [
        {
            "improvement_id": row.id,
            "source_type": row.source_type,
            "title": row.title,
            "priority": row.priority,
            "status": row.status,
            "release_assignment": row.release_assignment,
        }
        for row in rows
    ]


# --- Support ticket events (extend V1.8) ---


@router.post("/tenants/{tenant_id}/support/tickets/{ticket_id}/events", status_code=201)
def add_ticket_event(
    tenant_id: str,
    ticket_id: str,
    body: dict[str, str],
    response: Response,
    user: User = Depends(get_current_user),
    membership: TenantMembership = Depends(require_role("tenant_admin", "staff")),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    if membership.tenant_id != tenant_id:
        raise ApiError("TENANT_NOT_FOUND", "Tenant not found.", 404)
    ticket = session.execute(
        select(SupportTicket).where(
            SupportTicket.tenant_id == tenant_id, SupportTicket.id == ticket_id
        )
    ).scalar_one_or_none()
    if ticket is None:
        raise ApiError("TICKET_NOT_FOUND", "Support ticket not found.", 404)
    summary = (body.get("summary") or "")[:500]
    lowered = summary.lower()
    if any(token in lowered for token in ("ssn", "diagnosis:", "prescription:", "mrn:")):
        raise ApiError(
            "SUPPORT_SUMMARY_RESTRICTED",
            "Do not include clinical identifiers in ticket events.",
            422,
        )
    event = SupportTicketEvent(
        ticket_id=ticket_id,
        actor_id=user.id,
        event_type=body.get("event_type") or "comment",
        summary=summary,
    )
    session.add(event)
    session.flush()
    response.headers["Cache-Control"] = "no-store"
    return {"event_id": event.id, "event_type": event.event_type}


@router.post("/tenants/{tenant_id}/usage-events", status_code=201)
def record_product_usage(
    tenant_id: str,
    body: dict[str, str],
    response: Response,
    user: User = Depends(get_current_user),
    membership: TenantMembership = Depends(
        require_role("tenant_admin", "staff", "provider", "patient")
    ),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    if membership.tenant_id != tenant_id:
        raise ApiError("TENANT_NOT_FOUND", "Tenant not found.", 404)
    event_id = body.get("event_id") or new_id()
    existing = session.execute(
        select(ProductUsageEvent).where(
            ProductUsageEvent.organization_id == tenant_id,
            ProductUsageEvent.event_id == event_id,
        )
    ).scalar_one_or_none()
    if existing is not None:
        response.headers["Cache-Control"] = "no-store"
        return {"usage_id": existing.id, "duplicate": True}
    row = ProductUsageEvent(
        organization_id=tenant_id,
        actor_reference=user.id[:8],  # privacy-preserving truncation
        feature_code=(body.get("feature_code") or "unknown")[:64],
        event_type=(body.get("event_type") or "view")[:64],
        event_id=event_id[:128],
    )
    session.add(row)
    session.flush()
    response.headers["Cache-Control"] = "no-store"
    return {"usage_id": row.id, "duplicate": False}
