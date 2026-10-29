"""V1.8 operations: support tickets and launch readiness scorecard APIs."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request, Response
from pydantic import Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit import append_audit_event
from app.auth import ApiError, get_current_user
from app.authorization import require_role
from app.config import settings
from app.db import get_session
from app.models import TenantMembership, User, utcnow
from app.ops_models import LaunchReadinessCheck, SupportTicket
from app.platform_routes import require_platform_admin
from app.schemas import StrictModel

router = APIRouter(prefix="/api/v1", tags=["ops"])

DEFAULT_LAUNCH_CHECKS: list[dict[str, str]] = [
    {"gate": "functional", "check_code": "critical_workflows", "title": "Critical workflows pass acceptance"},
    {"gate": "security", "check_code": "tenant_isolation", "title": "Tenant isolation verified"},
    {"gate": "security", "check_code": "secrets_protected", "title": "Production secrets protected"},
    {"gate": "regulatory", "check_code": "hipaa_assessment", "title": "HIPAA readiness assessed"},
    {"gate": "operational", "check_code": "backup_restore", "title": "Backup restore tested"},
    {"gate": "operational", "check_code": "monitoring", "title": "Monitoring and alerting configured"},
    {"gate": "commercial", "check_code": "subscription_billing", "title": "Subscription billing validated"},
    {"gate": "commercial", "check_code": "baa_review", "title": "BAA / commercial agreements reviewed"},
    {"gate": "integration", "check_code": "live_integrations_gated", "title": "Live integrations remain gated"},
    {"gate": "executive", "check_code": "go_no_go", "title": "Formal go/no-go decision recorded"},
]


class SupportTicketWrite(StrictModel):
    category: str = Field(
        pattern="^(patient|clinic_admin|provider|billing|technical|security)$"
    )
    priority: str = Field(default="normal", pattern="^(low|normal|high|urgent)$")
    subject: str = Field(min_length=3, max_length=200)
    summary: str = Field(min_length=3, max_length=2000)


class SupportTicketUpdate(StrictModel):
    status: str = Field(pattern="^(open|assigned|resolved|closed)$")
    assigned_to_user_id: str | None = Field(default=None, min_length=36, max_length=36)
    resolution_summary: str = Field(default="", max_length=2000)


class LaunchCheckUpdate(StrictModel):
    status: str = Field(pattern="^(pass|fail|conditional|not_assessed)$")
    evidence_reference: str = Field(default="", max_length=256)
    notes: str = Field(default="", max_length=2000)


def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", "")


def _ticket_dict(row: SupportTicket) -> dict[str, Any]:
    return {
        "ticket_id": row.id,
        "ticket_number": row.ticket_number or row.id[:8],
        "tenant_id": row.tenant_id,
        "category": row.category,
        "priority": row.priority,
        "status": row.status,
        "subject": row.subject,
        "summary": row.summary,
        "assigned_team": row.assigned_team or "",
        "assigned_to_user_id": row.assigned_to_user_id,
        "resolution_summary": row.resolution_summary,
        "created_at": row.created_at.isoformat(),
        "resolved_at": row.resolved_at.isoformat() if row.resolved_at else None,
    }


@router.post("/tenants/{tenant_id}/support/tickets", status_code=201)
def create_support_ticket(
    tenant_id: str,
    body: SupportTicketWrite,
    request: Request,
    response: Response,
    user: User = Depends(get_current_user),
    membership: TenantMembership = Depends(
        require_role("patient", "tenant_admin", "staff", "provider")
    ),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    if membership.tenant_id != tenant_id:
        raise ApiError("TENANT_NOT_FOUND", "Tenant not found.", 404)
    # Reject obvious clinical dumps (soft guard — not a complete PHI classifier)
    lowered = body.summary.lower()
    if any(token in lowered for token in ("ssn", "diagnosis:", "prescription:", "mrn:")):
        raise ApiError(
            "SUPPORT_SUMMARY_RESTRICTED",
            "Do not include clinical identifiers or treatment detail in support tickets.",
            422,
        )
    row = SupportTicket(
        tenant_id=tenant_id,
        created_by_user_id=user.id,
        ticket_number=f"TKT-{utcnow().strftime('%Y%m%d')}-{user.id[:4].upper()}",
        category=body.category,
        priority=body.priority,
        subject=body.subject,
        summary=body.summary,
        assigned_team="",
        status="open",
    )
    session.add(row)
    session.flush()
    # Refine ticket number after id assignment
    row.ticket_number = f"TKT-{row.id[:8].upper()}"
    session.flush()
    append_audit_event(
        session,
        actor_user_id=user.id,
        tenant_id=tenant_id,
        action="support.ticket_created",
        subject_type="SupportTicket",
        subject_id=row.id,
        request_id=_request_id(request),
    )
    response.headers["Cache-Control"] = "no-store"
    return _ticket_dict(row)


@router.get("/tenants/{tenant_id}/support/tickets")
def list_support_tickets(
    tenant_id: str,
    response: Response,
    user: User = Depends(get_current_user),
    membership: TenantMembership = Depends(require_role("tenant_admin", "staff")),
    session: Session = Depends(get_session),
) -> list[dict[str, Any]]:
    if membership.tenant_id != tenant_id:
        raise ApiError("TENANT_NOT_FOUND", "Tenant not found.", 404)
    rows = session.execute(
        select(SupportTicket)
        .where(SupportTicket.tenant_id == tenant_id)
        .order_by(SupportTicket.created_at.desc())
        .limit(100)
    ).scalars()
    response.headers["Cache-Control"] = "no-store"
    return [_ticket_dict(row) for row in rows]


@router.patch("/tenants/{tenant_id}/support/tickets/{ticket_id}")
def update_support_ticket(
    tenant_id: str,
    ticket_id: str,
    body: SupportTicketUpdate,
    request: Request,
    response: Response,
    user: User = Depends(get_current_user),
    membership: TenantMembership = Depends(require_role("tenant_admin", "staff")),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    if membership.tenant_id != tenant_id:
        raise ApiError("TENANT_NOT_FOUND", "Tenant not found.", 404)
    row = session.execute(
        select(SupportTicket).where(
            SupportTicket.tenant_id == tenant_id, SupportTicket.id == ticket_id
        )
    ).scalar_one_or_none()
    if row is None:
        raise ApiError("TICKET_NOT_FOUND", "Support ticket not found.", 404)
    row.status = body.status
    if body.assigned_to_user_id:
        row.assigned_to_user_id = body.assigned_to_user_id
    if body.resolution_summary:
        row.resolution_summary = body.resolution_summary
    if body.status in {"resolved", "closed"}:
        row.resolved_at = utcnow()
    session.flush()
    append_audit_event(
        session,
        actor_user_id=user.id,
        tenant_id=tenant_id,
        action="support.ticket_updated",
        subject_type="SupportTicket",
        subject_id=row.id,
        request_id=_request_id(request),
    )
    response.headers["Cache-Control"] = "no-store"
    return _ticket_dict(row)


@router.get("/platform/launch-readiness")
def launch_readiness(
    response: Response,
    user: User = Depends(require_platform_admin),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    rows = list(session.execute(select(LaunchReadinessCheck)).scalars())
    if not rows:
        for item in DEFAULT_LAUNCH_CHECKS:
            session.add(
                LaunchReadinessCheck(
                    gate=item["gate"],
                    check_code=item["check_code"],
                    title=item["title"],
                    status="not_assessed",
                )
            )
        session.flush()
        rows = list(session.execute(select(LaunchReadinessCheck)).scalars())
    by_gate: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        by_gate.setdefault(row.gate, []).append(
            {
                "check_id": row.id,
                "check_code": row.check_code,
                "title": row.title,
                "status": row.status,
                "evidence_reference": row.evidence_reference,
                "notes": row.notes,
            }
        )
    response.headers["Cache-Control"] = "no-store"
    return {
        "environment": settings.environment,
        "launch_mode": settings.launch_mode,
        "gates": by_gate,
        "recommendation": "NO-GO until executive gate is recorded with organizational approvals.",
        "note": "Engineering readiness is not regulatory certification or launch authorization.",
    }


@router.patch("/platform/launch-readiness/{check_id}")
def update_launch_check(
    check_id: str,
    body: LaunchCheckUpdate,
    response: Response,
    user: User = Depends(require_platform_admin),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    row = session.get(LaunchReadinessCheck, check_id)
    if row is None:
        raise ApiError("CHECK_NOT_FOUND", "Launch readiness check not found.", 404)
    row.status = body.status
    row.evidence_reference = body.evidence_reference
    row.notes = body.notes
    row.assessed_by_user_id = user.id
    row.assessed_at = utcnow()
    session.flush()
    response.headers["Cache-Control"] = "no-store"
    return {
        "check_id": row.id,
        "gate": row.gate,
        "check_code": row.check_code,
        "status": row.status,
    }
