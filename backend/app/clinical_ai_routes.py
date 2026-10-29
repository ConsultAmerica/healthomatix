"""Phase 5 AI clinical support: /summaries, /notes, /tasks with hard approval gate."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit import append_audit_event
from app.auth import ApiError, get_current_user
from app.authorization import require_role
from app.consent_gate import require_patient_consent
from app.db import get_session
from app.fhir_models import ClinicalDraft, VideoSession
from app.fhir_store import create_resource, search_resources, write_provenance
from app.intelligence.clinical_ai_port import build_clinical_ai_adapter
from app.models import TenantMembership, User, utcnow
from app.schemas import (
    ClinicalDraftApproveWrite,
    ClinicalDraftCreate,
    ClinicalDraftRead,
)

router = APIRouter(prefix="/api/v1", tags=["clinical-ai"])


def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", "")


def _to_read(row: ClinicalDraft) -> ClinicalDraftRead:
    return ClinicalDraftRead(
        draft_id=row.id,
        patient_id=row.patient_id,
        draft_type=row.draft_type,
        status=row.status,
        title=row.title,
        content=row.content or {},
        source_links=row.source_links or [],
        session_id=row.session_id,
        encounter_id=row.encounter_id,
        approved_resource_id=row.approved_resource_id,
        created_at=row.created_at,
        approved_at=row.approved_at,
    )


def _require_clinician_consent(
    session: Session,
    *,
    tenant_id: str,
    patient_id: str,
    user: User,
    membership: TenantMembership,
    request_id: str,
) -> None:
    require_patient_consent(
        session,
        tenant_id=tenant_id,
        patient_id=patient_id,
        actor=user,
        membership=membership,
        request_id=request_id,
        subject_type="Patient",
        subject_id=patient_id,
    )


@router.post(
    "/tenants/{tenant_id}/summaries",
    response_model=ClinicalDraftRead,
    status_code=201,
)
def create_previsit_summary(
    tenant_id: str,
    body: ClinicalDraftCreate,
    request: Request,
    response: Response,
    user: User = Depends(get_current_user),
    membership: TenantMembership = Depends(require_role("tenant_admin", "staff", "provider")),
    session: Session = Depends(get_session),
) -> ClinicalDraftRead:
    if membership.tenant_id != tenant_id:
        raise ApiError("TENANT_NOT_FOUND", "Tenant not found.", 404)
    _require_clinician_consent(
        session,
        tenant_id=tenant_id,
        patient_id=body.patient_id,
        user=user,
        membership=membership,
        request_id=_request_id(request),
    )
    observations = search_resources(
        session,
        tenant_id=tenant_id,
        resource_type="Observation",
        patient_id=body.patient_id,
        limit=50,
    )
    encounters = search_resources(
        session,
        tenant_id=tenant_id,
        resource_type="Encounter",
        patient_id=body.patient_id,
        limit=20,
    )
    bundle = build_clinical_ai_adapter().previsit_summary(
        patient_id=body.patient_id,
        observations=observations,
        encounters=encounters,
    )
    row = ClinicalDraft(
        tenant_id=tenant_id,
        patient_id=body.patient_id,
        draft_type="summary",
        status="draft",
        title=bundle.title,
        content=bundle.content,
        source_links=bundle.source_links,
        session_id=body.session_id,
        created_by_user_id=user.id,
    )
    session.add(row)
    session.flush()
    append_audit_event(
        session,
        actor_user_id=user.id,
        tenant_id=tenant_id,
        action="clinical_draft.created",
        subject_type="ClinicalDraft",
        subject_id=row.id,
        request_id=_request_id(request),
    )
    response.headers["Cache-Control"] = "no-store"
    return _to_read(row)


@router.post(
    "/tenants/{tenant_id}/notes",
    response_model=ClinicalDraftRead,
    status_code=201,
)
def create_visit_note_draft(
    tenant_id: str,
    body: ClinicalDraftCreate,
    request: Request,
    response: Response,
    user: User = Depends(get_current_user),
    membership: TenantMembership = Depends(require_role("tenant_admin", "staff", "provider")),
    session: Session = Depends(get_session),
) -> ClinicalDraftRead:
    if membership.tenant_id != tenant_id:
        raise ApiError("TENANT_NOT_FOUND", "Tenant not found.", 404)
    _require_clinician_consent(
        session,
        tenant_id=tenant_id,
        patient_id=body.patient_id,
        user=user,
        membership=membership,
        request_id=_request_id(request),
    )
    follow_up = ""
    encounter_id = None
    if body.session_id:
        video = session.execute(
            select(VideoSession).where(
                VideoSession.tenant_id == tenant_id,
                VideoSession.id == body.session_id,
            )
        ).scalar_one_or_none()
        if video is None or video.patient_user_id != body.patient_id:
            raise ApiError("SESSION_NOT_FOUND", "Session not found.", 404)
        follow_up = video.follow_up_plan or ""
        encounter_id = video.encounter_id
    observations = search_resources(
        session,
        tenant_id=tenant_id,
        resource_type="Observation",
        patient_id=body.patient_id,
        limit=20,
    )
    bundle = build_clinical_ai_adapter().visit_note(
        patient_id=body.patient_id,
        follow_up_plan=follow_up,
        observations=observations,
        transcript="",
    )
    row = ClinicalDraft(
        tenant_id=tenant_id,
        patient_id=body.patient_id,
        draft_type="note",
        status="draft",
        title=bundle.title,
        content=bundle.content,
        source_links=bundle.source_links,
        session_id=body.session_id,
        encounter_id=encounter_id,
        created_by_user_id=user.id,
    )
    session.add(row)
    session.flush()
    append_audit_event(
        session,
        actor_user_id=user.id,
        tenant_id=tenant_id,
        action="clinical_draft.created",
        subject_type="ClinicalDraft",
        subject_id=row.id,
        request_id=_request_id(request),
    )
    response.headers["Cache-Control"] = "no-store"
    return _to_read(row)


@router.post(
    "/tenants/{tenant_id}/tasks",
    response_model=ClinicalDraftRead,
    status_code=201,
)
def create_follow_up_task_draft(
    tenant_id: str,
    body: ClinicalDraftCreate,
    request: Request,
    response: Response,
    user: User = Depends(get_current_user),
    membership: TenantMembership = Depends(require_role("tenant_admin", "staff", "provider")),
    session: Session = Depends(get_session),
) -> ClinicalDraftRead:
    if membership.tenant_id != tenant_id:
        raise ApiError("TENANT_NOT_FOUND", "Tenant not found.", 404)
    _require_clinician_consent(
        session,
        tenant_id=tenant_id,
        patient_id=body.patient_id,
        user=user,
        membership=membership,
        request_id=_request_id(request),
    )
    follow_up = ""
    if body.session_id:
        video = session.execute(
            select(VideoSession).where(
                VideoSession.tenant_id == tenant_id,
                VideoSession.id == body.session_id,
            )
        ).scalar_one_or_none()
        if video is None or video.patient_user_id != body.patient_id:
            raise ApiError("SESSION_NOT_FOUND", "Session not found.", 404)
        follow_up = video.follow_up_plan or ""
    bundle = build_clinical_ai_adapter().follow_up_tasks(
        patient_id=body.patient_id,
        follow_up_plan=follow_up,
    )
    row = ClinicalDraft(
        tenant_id=tenant_id,
        patient_id=body.patient_id,
        draft_type="task",
        status="draft",
        title=bundle.title,
        content=bundle.content,
        source_links=bundle.source_links,
        session_id=body.session_id,
        created_by_user_id=user.id,
    )
    session.add(row)
    session.flush()
    append_audit_event(
        session,
        actor_user_id=user.id,
        tenant_id=tenant_id,
        action="clinical_draft.created",
        subject_type="ClinicalDraft",
        subject_id=row.id,
        request_id=_request_id(request),
    )
    response.headers["Cache-Control"] = "no-store"
    return _to_read(row)


@router.get("/tenants/{tenant_id}/drafts", response_model=list[ClinicalDraftRead])
def list_drafts(
    tenant_id: str,
    request: Request,
    response: Response,
    patient_id: str = Query(...),
    draft_type: str | None = Query(default=None),
    status: str | None = Query(default="draft"),
    user: User = Depends(get_current_user),
    membership: TenantMembership = Depends(require_role("tenant_admin", "staff", "provider")),
    session: Session = Depends(get_session),
) -> list[ClinicalDraftRead]:
    if membership.tenant_id != tenant_id:
        raise ApiError("TENANT_NOT_FOUND", "Tenant not found.", 404)
    _require_clinician_consent(
        session,
        tenant_id=tenant_id,
        patient_id=patient_id,
        user=user,
        membership=membership,
        request_id=_request_id(request),
    )
    stmt = select(ClinicalDraft).where(
        ClinicalDraft.tenant_id == tenant_id,
        ClinicalDraft.patient_id == patient_id,
    )
    if draft_type:
        stmt = stmt.where(ClinicalDraft.draft_type == draft_type)
    if status:
        stmt = stmt.where(ClinicalDraft.status == status)
    rows = session.execute(stmt.order_by(ClinicalDraft.created_at.desc()).limit(50)).scalars()
    response.headers["Cache-Control"] = "no-store"
    return [_to_read(row) for row in rows]


@router.get("/tenants/{tenant_id}/drafts/{draft_id}", response_model=ClinicalDraftRead)
def get_draft(
    tenant_id: str,
    draft_id: str,
    request: Request,
    response: Response,
    user: User = Depends(get_current_user),
    membership: TenantMembership = Depends(require_role("tenant_admin", "staff", "provider")),
    session: Session = Depends(get_session),
) -> ClinicalDraftRead:
    if membership.tenant_id != tenant_id:
        raise ApiError("TENANT_NOT_FOUND", "Tenant not found.", 404)
    row = session.execute(
        select(ClinicalDraft).where(
            ClinicalDraft.tenant_id == tenant_id,
            ClinicalDraft.id == draft_id,
        )
    ).scalar_one_or_none()
    if row is None:
        raise ApiError("DRAFT_NOT_FOUND", "Draft not found.", 404)
    _require_clinician_consent(
        session,
        tenant_id=tenant_id,
        patient_id=row.patient_id,
        user=user,
        membership=membership,
        request_id=_request_id(request),
    )
    response.headers["Cache-Control"] = "no-store"
    return _to_read(row)


@router.post(
    "/tenants/{tenant_id}/drafts/{draft_id}/approve",
    response_model=ClinicalDraftRead,
)
def approve_draft(
    tenant_id: str,
    draft_id: str,
    body: ClinicalDraftApproveWrite,
    request: Request,
    response: Response,
    user: User = Depends(get_current_user),
    membership: TenantMembership = Depends(require_role("tenant_admin", "staff", "provider")),
    session: Session = Depends(get_session),
) -> ClinicalDraftRead:
    """Hard gate: only approval writes Composition/Task into Clinical Records."""
    if membership.tenant_id != tenant_id:
        raise ApiError("TENANT_NOT_FOUND", "Tenant not found.", 404)
    row = session.execute(
        select(ClinicalDraft).where(
            ClinicalDraft.tenant_id == tenant_id,
            ClinicalDraft.id == draft_id,
        )
    ).scalar_one_or_none()
    if row is None:
        raise ApiError("DRAFT_NOT_FOUND", "Draft not found.", 404)
    if row.status != "draft":
        raise ApiError("DRAFT_NOT_PENDING", "Draft is not awaiting approval.", 409)
    _require_clinician_consent(
        session,
        tenant_id=tenant_id,
        patient_id=row.patient_id,
        user=user,
        membership=membership,
        request_id=_request_id(request),
    )

    if body.edited_content is not None:
        row.content = body.edited_content
    if body.edited_title is not None:
        row.title = body.edited_title.strip() or row.title

    resource = _promote_draft_to_fhir(session, tenant_id=tenant_id, draft=row, actor_id=user.id)
    row.status = "approved"
    row.approved_by_user_id = user.id
    row.approved_at = utcnow()
    row.approved_resource_id = resource["id"]
    session.flush()

    append_audit_event(
        session,
        actor_user_id=user.id,
        tenant_id=tenant_id,
        action="clinical_draft.approved",
        subject_type=resource["resourceType"],
        subject_id=resource["id"],
        request_id=_request_id(request),
    )
    response.headers["Cache-Control"] = "no-store"
    return _to_read(row)


def _promote_draft_to_fhir(
    session: Session,
    *,
    tenant_id: str,
    draft: ClinicalDraft,
    actor_id: str,
) -> dict[str, Any]:
    content = draft.content or {}
    if draft.draft_type in {"summary", "note"}:
        sections = []
        if draft.draft_type == "summary":
            for point in content.get("points") or []:
                if isinstance(point, dict):
                    sections.append(
                        {
                            "title": "Finding",
                            "text": {"status": "additional", "div": f"<div>{point.get('text')}</div>"},
                            "entry": [{"reference": point.get("source")}]
                            if point.get("source")
                            else [],
                        }
                    )
        else:
            sections.append(
                {
                    "title": "Visit narrative",
                    "text": {
                        "status": "additional",
                        "div": f"<div>{content.get('narrative', '')}</div>",
                    },
                }
            )
        body = {
            "resourceType": "Composition",
            "status": "final",
            "type": {"text": draft.title or draft.draft_type},
            "subject": {"reference": f"Patient/{draft.patient_id}"},
            "date": utcnow().isoformat().replace("+00:00", "Z"),
            "title": draft.title,
            "author": [{"reference": f"Practitioner/{actor_id}"}],
            "section": sections,
            "extension": [
                {"url": "urn:healthomatix:draft-id", "valueString": draft.id},
            ],
        }
        if draft.encounter_id:
            body["encounter"] = {"reference": f"Encounter/{draft.encounter_id}"}
        resource = create_resource(
            session, tenant_id=tenant_id, resource_type="Composition", body=body
        )
        write_provenance(
            session,
            tenant_id=tenant_id,
            target_type="Composition",
            target_id=resource["id"],
            patient_id=draft.patient_id,
            agent_user_id=actor_id,
            entity_refs=[("ClinicalDraft", draft.id)],
        )
        return resource

    # task draft → one Task per suggested item (first becomes primary return)
    tasks = content.get("tasks") or []
    created: dict[str, Any] | None = None
    for item in tasks:
        if not isinstance(item, dict):
            continue
        task_body = {
            "resourceType": "Task",
            "status": "requested",
            "intent": "order",
            "description": item.get("description") or draft.title,
            "for": {"reference": item.get("for") or f"Patient/{draft.patient_id}"},
            "priority": item.get("priority") or "routine",
            "extension": [
                {"url": "urn:healthomatix:draft-id", "valueString": draft.id},
            ],
        }
        resource = create_resource(
            session, tenant_id=tenant_id, resource_type="Task", body=task_body
        )
        write_provenance(
            session,
            tenant_id=tenant_id,
            target_type="Task",
            target_id=resource["id"],
            patient_id=draft.patient_id,
            agent_user_id=actor_id,
            entity_refs=[("ClinicalDraft", draft.id)],
        )
        if created is None:
            created = resource
    if created is None:
        raise ApiError("DRAFT_EMPTY", "Draft has no tasks to approve.", 422)
    return created
