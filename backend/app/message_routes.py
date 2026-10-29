from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.audit import append_audit_event
from app.auth import ApiError, get_current_user
from app.authorization import require_clinic_patient, require_membership, require_role
from app.db import get_session
from app.models import ClinicPatient, Message, MessageThread, TenantMembership, User, utcnow
from app.schemas import MessageCreate, MessageRead, ThreadCreate, ThreadRead

router = APIRouter(prefix="/api/v1")


def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", "")


def _sender_role(session: Session, *, tenant_id: str, user_id: str) -> str | None:
    membership = session.execute(
        select(TenantMembership).where(
            TenantMembership.tenant_id == tenant_id,
            TenantMembership.user_id == user_id,
            TenantMembership.status == "active",
        )
    ).scalar_one_or_none()
    return membership.role if membership else None


def _message_read(session: Session, row: Message) -> MessageRead:
    return MessageRead(
        message_id=row.id,
        thread_id=row.thread_id,
        sender_user_id=row.sender_user_id,
        sender_role=_sender_role(session, tenant_id=row.tenant_id, user_id=row.sender_user_id),
        body=row.body,
        created_at=row.created_at,
    )


def _thread_read(session: Session, thread: MessageThread) -> ThreadRead:
    count = session.execute(
        select(func.count()).select_from(Message).where(Message.thread_id == thread.id)
    ).scalar_one()
    return ThreadRead(
        thread_id=thread.id,
        clinic_patient_id=thread.clinic_patient_id,
        subject=thread.subject,
        status=thread.status,
        created_at=thread.created_at,
        updated_at=thread.updated_at,
        message_count=int(count or 0),
    )


def _can_access_thread(
    *,
    membership: TenantMembership,
    user: User,
    thread: MessageThread,
    session: Session,
) -> bool:
    if membership.role in {"tenant_admin", "staff", "provider"}:
        return True
    if membership.role != "patient":
        return False
    clinic_patient = session.execute(
        select(ClinicPatient).where(
            ClinicPatient.id == thread.clinic_patient_id,
            ClinicPatient.tenant_id == thread.tenant_id,
            ClinicPatient.patient_user_id == user.id,
            ClinicPatient.status == "active",
        )
    ).scalar_one_or_none()
    return clinic_patient is not None


@router.get("/tenants/{tenant_id}/threads", response_model=list[ThreadRead])
def list_threads(
    tenant_id: str,
    response: Response,
    user: User = Depends(get_current_user),
    membership: TenantMembership = Depends(require_membership),
    session: Session = Depends(get_session),
    clinic_patient_id: str | None = None,
) -> list[ThreadRead]:
    if membership.tenant_id != tenant_id:
        raise ApiError("TENANT_NOT_FOUND", "Tenant not found.", 404)
    response.headers["Cache-Control"] = "no-store"

    query = select(MessageThread).where(MessageThread.tenant_id == tenant_id)
    if membership.role == "patient":
        clinic_patient = require_clinic_patient(session, tenant_id=tenant_id, user_id=user.id)
        query = query.where(MessageThread.clinic_patient_id == clinic_patient.id)
    elif membership.role not in {"tenant_admin", "staff", "provider"}:
        raise ApiError("ROLE_REQUIRED", "You are not authorized for this action.", 403)
    elif clinic_patient_id:
        query = query.where(MessageThread.clinic_patient_id == clinic_patient_id)

    rows = session.execute(query.order_by(MessageThread.updated_at.desc()).limit(100)).scalars()
    return [_thread_read(session, row) for row in rows]


@router.post("/tenants/{tenant_id}/threads", response_model=ThreadRead, status_code=201)
def create_thread(
    tenant_id: str,
    body: ThreadCreate,
    request: Request,
    response: Response,
    user: User = Depends(get_current_user),
    membership: TenantMembership = Depends(require_membership),
    session: Session = Depends(get_session),
) -> ThreadRead:
    if membership.tenant_id != tenant_id:
        raise ApiError("TENANT_NOT_FOUND", "Tenant not found.", 404)

    if membership.role == "patient":
        clinic_patient = require_clinic_patient(session, tenant_id=tenant_id, user_id=user.id)
    elif membership.role in {"tenant_admin", "staff", "provider"}:
        if not body.clinic_patient_id:
            raise ApiError(
                "PATIENT_REQUIRED",
                "Select a clinic patient to message.",
                422,
            )
        clinic_patient = session.execute(
            select(ClinicPatient).where(
                ClinicPatient.tenant_id == tenant_id,
                ClinicPatient.id == body.clinic_patient_id,
                ClinicPatient.status == "active",
            )
        ).scalar_one_or_none()
        if clinic_patient is None:
            raise ApiError("PATIENT_NOT_FOUND", "Patient not found.", 404)
    else:
        raise ApiError("ROLE_REQUIRED", "You are not authorized for this action.", 403)

    thread = MessageThread(
        tenant_id=tenant_id,
        clinic_patient_id=clinic_patient.id,
        subject=body.subject,
        created_by_user_id=user.id,
        status="open",
    )
    session.add(thread)
    session.flush()
    session.add(
        Message(
            tenant_id=tenant_id,
            thread_id=thread.id,
            sender_user_id=user.id,
            body=body.body,
        )
    )
    append_audit_event(
        session,
        actor_user_id=user.id,
        tenant_id=tenant_id,
        action="message_thread.created",
        subject_type="message_thread",
        subject_id=thread.id,
        request_id=_request_id(request),
    )
    response.headers["Cache-Control"] = "no-store"
    return _thread_read(session, thread)


@router.post(
    "/tenants/{tenant_id}/threads/{thread_id}/close",
    response_model=ThreadRead,
)
def close_thread(
    tenant_id: str,
    thread_id: str,
    request: Request,
    response: Response,
    user: User = Depends(get_current_user),
    membership: TenantMembership = Depends(require_membership),
    session: Session = Depends(get_session),
) -> ThreadRead:
    if membership.tenant_id != tenant_id:
        raise ApiError("TENANT_NOT_FOUND", "Tenant not found.", 404)
    thread = session.execute(
        select(MessageThread).where(
            MessageThread.tenant_id == tenant_id,
            MessageThread.id == thread_id,
        )
    ).scalar_one_or_none()
    if thread is None or not _can_access_thread(
        membership=membership, user=user, thread=thread, session=session
    ):
        raise ApiError("THREAD_NOT_FOUND", "Thread not found.", 404)
    if membership.role not in {"patient", "tenant_admin", "staff", "provider"}:
        raise ApiError("ROLE_REQUIRED", "You are not authorized for this action.", 403)
    if thread.status == "closed":
        response.headers["Cache-Control"] = "no-store"
        return _thread_read(session, thread)

    thread.status = "closed"
    thread.updated_at = utcnow()
    append_audit_event(
        session,
        actor_user_id=user.id,
        tenant_id=tenant_id,
        action="message_thread.closed",
        subject_type="message_thread",
        subject_id=thread.id,
        request_id=_request_id(request),
    )
    response.headers["Cache-Control"] = "no-store"
    return _thread_read(session, thread)


@router.get(
    "/tenants/{tenant_id}/threads/{thread_id}/messages",
    response_model=list[MessageRead],
)
def list_messages(
    tenant_id: str,
    thread_id: str,
    response: Response,
    user: User = Depends(get_current_user),
    membership: TenantMembership = Depends(require_membership),
    session: Session = Depends(get_session),
) -> list[MessageRead]:
    if membership.tenant_id != tenant_id:
        raise ApiError("TENANT_NOT_FOUND", "Tenant not found.", 404)
    thread = session.execute(
        select(MessageThread).where(
            MessageThread.tenant_id == tenant_id,
            MessageThread.id == thread_id,
        )
    ).scalar_one_or_none()
    if thread is None or not _can_access_thread(
        membership=membership, user=user, thread=thread, session=session
    ):
        raise ApiError("THREAD_NOT_FOUND", "Thread not found.", 404)

    response.headers["Cache-Control"] = "no-store"
    rows = session.execute(
        select(Message)
        .where(Message.thread_id == thread.id, Message.tenant_id == tenant_id)
        .order_by(Message.created_at.asc())
        .limit(500)
    ).scalars()
    return [_message_read(session, row) for row in rows]


@router.post(
    "/tenants/{tenant_id}/threads/{thread_id}/messages",
    response_model=MessageRead,
    status_code=201,
)
def post_message(
    tenant_id: str,
    thread_id: str,
    body: MessageCreate,
    request: Request,
    response: Response,
    user: User = Depends(get_current_user),
    membership: TenantMembership = Depends(require_membership),
    session: Session = Depends(get_session),
) -> MessageRead:
    if membership.tenant_id != tenant_id:
        raise ApiError("TENANT_NOT_FOUND", "Tenant not found.", 404)
    thread = session.execute(
        select(MessageThread).where(
            MessageThread.tenant_id == tenant_id,
            MessageThread.id == thread_id,
        )
    ).scalar_one_or_none()
    if thread is None or not _can_access_thread(
        membership=membership, user=user, thread=thread, session=session
    ):
        raise ApiError("THREAD_NOT_FOUND", "Thread not found.", 404)
    if thread.status != "open":
        raise ApiError("THREAD_CLOSED", "This thread is closed.", 409)
    if membership.role not in {"patient", "tenant_admin", "staff", "provider"}:
        raise ApiError("ROLE_REQUIRED", "You are not authorized for this action.", 403)

    now = utcnow()
    message = Message(
        tenant_id=tenant_id,
        thread_id=thread.id,
        sender_user_id=user.id,
        body=body.body,
        created_at=now,
    )
    session.add(message)
    thread.updated_at = now
    append_audit_event(
        session,
        actor_user_id=user.id,
        tenant_id=tenant_id,
        action="message.posted",
        subject_type="message",
        subject_id=message.id,
        request_id=_request_id(request),
    )
    session.flush()
    response.headers["Cache-Control"] = "no-store"
    return _message_read(session, message)
