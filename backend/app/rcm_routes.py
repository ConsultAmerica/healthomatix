"""V1.6 insurance eligibility, charge capture, claims, denials, remittance, RCM analytics."""

from __future__ import annotations

from datetime import date
from uuid import uuid4

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.audit import append_audit_event
from app.auth import ApiError, get_current_user
from app.authorization import require_role
from app.db import get_session
from app.entitlements import require_entitlement
from app.integrations.clearinghouse_port import build_clearinghouse_adapter
from app.integrations.eligibility_port import build_eligibility_adapter
from app.models import TenantMembership, User, utcnow
from app.rcm_models import (
    Claim,
    ClaimDenial,
    ClaimLine,
    ClaimSubmission,
    EligibilityCheck,
    EncounterCharge,
    InsurancePayer,
    PatientFinancialTransaction,
    PatientInsurancePolicy,
    PayerRemittance,
    PaymentAllocation,
)
from app.schemas import (
    ChargeRead,
    ChargeWrite,
    ClaimCreateWrite,
    ClaimRead,
    ClaimSubmissionRead,
    ClaimSubmitWrite,
    DenialAssignWrite,
    DenialRead,
    DenialResolveWrite,
    EligibilityCheckRead,
    EligibilityVerifyWrite,
    InsurancePayerRead,
    InsurancePayerWrite,
    InsurancePolicyRead,
    InsurancePolicyWrite,
    PatientBillingRead,
    RcmAnalyticsRead,
    RemittanceImportWrite,
    RemittanceRead,
)

router = APIRouter(prefix="/api/v1", tags=["rcm"])

BILLING_ROLES = ("tenant_admin", "staff")


def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", "")


def _require_rcm(session: Session, tenant_id: str) -> None:
    require_entitlement(session, tenant_id=tenant_id, feature_code="rcm")


def _mask_member(value: str) -> str:
    if len(value) <= 4:
        return "****"
    return "*" * (len(value) - 4) + value[-4:]


def _policy_read(row: PatientInsurancePolicy) -> InsurancePolicyRead:
    return InsurancePolicyRead(
        policy_id=row.id,
        patient_id=row.patient_id,
        payer_id=row.payer_id,
        plan_name=row.plan_name,
        member_identifier=_mask_member(row.member_identifier),
        group_identifier=row.group_identifier,
        coverage_order=row.coverage_order,
        status=row.status,
        effective_date=row.effective_date,
        termination_date=row.termination_date,
    )


def _charge_read(row: EncounterCharge) -> ChargeRead:
    return ChargeRead(
        charge_id=row.id,
        encounter_id=row.encounter_id,
        patient_id=row.patient_id,
        service_code=row.service_code,
        diagnosis_codes=list(row.diagnosis_codes or []),
        units=row.units,
        charge_amount_cents=row.charge_amount_cents,
        status=row.status,
        ai_suggested=row.ai_suggested,
        ai_rationale=row.ai_rationale,
        created_at=row.created_at,
    )


def _claim_read(row: Claim) -> ClaimRead:
    return ClaimRead(
        claim_id=row.id,
        claim_number=row.claim_number,
        patient_id=row.patient_id,
        encounter_id=row.encounter_id,
        payer_id=row.payer_id,
        status=row.status,
        total_charge_cents=row.total_charge_cents,
        payer_claim_reference=row.payer_claim_reference,
        clearinghouse_reference=row.clearinghouse_reference,
        created_at=row.created_at,
    )


@router.get("/tenants/{tenant_id}/insurance/payers", response_model=list[InsurancePayerRead])
def list_payers(
    tenant_id: str,
    response: Response,
    user: User = Depends(get_current_user),
    membership: TenantMembership = Depends(require_role(*BILLING_ROLES, "provider")),
    session: Session = Depends(get_session),
) -> list[InsurancePayerRead]:
    if membership.tenant_id != tenant_id:
        raise ApiError("TENANT_NOT_FOUND", "Tenant not found.", 404)
    rows = session.execute(select(InsurancePayer).where(InsurancePayer.status == "active")).scalars()
    response.headers["Cache-Control"] = "no-store"
    return [
        InsurancePayerRead(
            payer_id=row.id, name=row.name, payer_identifier=row.payer_identifier, status=row.status
        )
        for row in rows
    ]


@router.post("/tenants/{tenant_id}/insurance/payers", response_model=InsurancePayerRead, status_code=201)
def create_payer(
    tenant_id: str,
    body: InsurancePayerWrite,
    response: Response,
    user: User = Depends(get_current_user),
    membership: TenantMembership = Depends(require_role(*BILLING_ROLES)),
    session: Session = Depends(get_session),
) -> InsurancePayerRead:
    if membership.tenant_id != tenant_id:
        raise ApiError("TENANT_NOT_FOUND", "Tenant not found.", 404)
    ident = body.payer_identifier.strip() or f"SANDBOX-{uuid4().hex[:8].upper()}"
    existing = session.execute(
        select(InsurancePayer).where(InsurancePayer.payer_identifier == ident)
    ).scalar_one_or_none()
    if existing:
        response.headers["Cache-Control"] = "no-store"
        return InsurancePayerRead(
            payer_id=existing.id,
            name=existing.name,
            payer_identifier=existing.payer_identifier,
            status=existing.status,
        )
    row = InsurancePayer(name=body.name.strip() or "Sandbox Payer", payer_identifier=ident)
    session.add(row)
    session.flush()
    response.headers["Cache-Control"] = "no-store"
    return InsurancePayerRead(
        payer_id=row.id, name=row.name, payer_identifier=row.payer_identifier, status=row.status
    )


@router.post(
    "/tenants/{tenant_id}/patients/{patient_id}/insurance",
    response_model=InsurancePolicyRead,
    status_code=201,
)
def create_insurance_policy(
    tenant_id: str,
    patient_id: str,
    body: InsurancePolicyWrite,
    request: Request,
    response: Response,
    user: User = Depends(get_current_user),
    membership: TenantMembership = Depends(require_role(*BILLING_ROLES, "provider")),
    session: Session = Depends(get_session),
) -> InsurancePolicyRead:
    if membership.tenant_id != tenant_id:
        raise ApiError("TENANT_NOT_FOUND", "Tenant not found.", 404)
    if body.patient_id != patient_id:
        raise ApiError("PATIENT_MISMATCH", "Path patient_id must match body.", 422)
    _require_rcm(session, tenant_id)
    payer = session.get(InsurancePayer, body.payer_id)
    if payer is None:
        raise ApiError("PAYER_NOT_FOUND", "Insurance payer not found.", 404)
    row = PatientInsurancePolicy(
        tenant_id=tenant_id,
        patient_id=patient_id,
        payer_id=body.payer_id,
        plan_name=body.plan_name,
        member_identifier=body.member_identifier,
        group_identifier=body.group_identifier,
        subscriber_name=body.subscriber_name,
        subscriber_relationship=body.subscriber_relationship,
        coverage_order=body.coverage_order,
        effective_date=body.effective_date,
        termination_date=body.termination_date,
        status="active",
    )
    session.add(row)
    session.flush()
    append_audit_event(
        session,
        actor_user_id=user.id,
        tenant_id=tenant_id,
        action="insurance.policy_created",
        subject_type="PatientInsurancePolicy",
        subject_id=row.id,
        request_id=_request_id(request),
    )
    response.headers["Cache-Control"] = "no-store"
    return _policy_read(row)


@router.get(
    "/tenants/{tenant_id}/patients/{patient_id}/insurance",
    response_model=list[InsurancePolicyRead],
)
def list_insurance_policies(
    tenant_id: str,
    patient_id: str,
    response: Response,
    user: User = Depends(get_current_user),
    membership: TenantMembership = Depends(require_role(*BILLING_ROLES, "provider", "patient")),
    session: Session = Depends(get_session),
) -> list[InsurancePolicyRead]:
    if membership.tenant_id != tenant_id:
        raise ApiError("TENANT_NOT_FOUND", "Tenant not found.", 404)
    if membership.role == "patient" and user.id != patient_id:
        raise ApiError("PATIENT_NOT_FOUND", "Patient not found.", 404)
    rows = session.execute(
        select(PatientInsurancePolicy)
        .where(
            PatientInsurancePolicy.tenant_id == tenant_id,
            PatientInsurancePolicy.patient_id == patient_id,
        )
        .order_by(PatientInsurancePolicy.coverage_order.asc())
    ).scalars()
    response.headers["Cache-Control"] = "no-store"
    return [_policy_read(row) for row in rows]


@router.post(
    "/tenants/{tenant_id}/insurance/policies/{policy_id}/verify-eligibility",
    response_model=EligibilityCheckRead,
)
def verify_eligibility(
    tenant_id: str,
    policy_id: str,
    body: EligibilityVerifyWrite,
    request: Request,
    response: Response,
    user: User = Depends(get_current_user),
    membership: TenantMembership = Depends(require_role(*BILLING_ROLES, "provider")),
    session: Session = Depends(get_session),
) -> EligibilityCheckRead:
    if membership.tenant_id != tenant_id:
        raise ApiError("TENANT_NOT_FOUND", "Tenant not found.", 404)
    _require_rcm(session, tenant_id)
    policy = session.execute(
        select(PatientInsurancePolicy).where(
            PatientInsurancePolicy.tenant_id == tenant_id,
            PatientInsurancePolicy.id == policy_id,
        )
    ).scalar_one_or_none()
    if policy is None:
        raise ApiError("POLICY_NOT_FOUND", "Insurance policy not found.", 404)
    payer = session.get(InsurancePayer, policy.payer_id)
    result = build_eligibility_adapter().verify(
        payer_identifier=payer.payer_identifier if payer else "UNKNOWN",
        member_identifier=policy.member_identifier,
    )
    row = EligibilityCheck(
        tenant_id=tenant_id,
        patient_id=policy.patient_id,
        insurance_policy_id=policy.id,
        appointment_id=body.appointment_id,
        request_reference=result.request_reference,
        response_reference=result.response_reference,
        coverage_status=result.coverage_status,
        financial_readiness=result.financial_readiness,
        benefits_summary=result.benefits_summary,
        disclaimer=result.disclaimer,
        status="completed",
        checked_at=utcnow(),
    )
    session.add(row)
    session.flush()
    append_audit_event(
        session,
        actor_user_id=user.id,
        tenant_id=tenant_id,
        action="insurance.eligibility_checked",
        subject_type="EligibilityCheck",
        subject_id=row.id,
        request_id=_request_id(request),
    )
    response.headers["Cache-Control"] = "no-store"
    return EligibilityCheckRead(
        eligibility_id=row.id,
        patient_id=row.patient_id,
        insurance_policy_id=row.insurance_policy_id,
        coverage_status=row.coverage_status,
        financial_readiness=row.financial_readiness,
        benefits_summary=row.benefits_summary or {},
        disclaimer=row.disclaimer,
        request_reference=row.request_reference,
        response_reference=row.response_reference,
        checked_at=row.checked_at,
    )


@router.post(
    "/tenants/{tenant_id}/encounters/{encounter_id}/charges",
    response_model=ChargeRead,
    status_code=201,
)
def create_charge(
    tenant_id: str,
    encounter_id: str,
    body: ChargeWrite,
    request: Request,
    response: Response,
    user: User = Depends(get_current_user),
    membership: TenantMembership = Depends(require_role(*BILLING_ROLES, "provider")),
    session: Session = Depends(get_session),
) -> ChargeRead:
    if membership.tenant_id != tenant_id:
        raise ApiError("TENANT_NOT_FOUND", "Tenant not found.", 404)
    if body.encounter_id != encounter_id:
        raise ApiError("ENCOUNTER_MISMATCH", "Path encounter_id must match body.", 422)
    _require_rcm(session, tenant_id)
    row = EncounterCharge(
        tenant_id=tenant_id,
        encounter_id=encounter_id,
        patient_id=body.patient_id,
        provider_user_id=body.provider_user_id,
        service_date=body.service_date,
        service_code=body.service_code,
        service_code_system=body.service_code_system,
        diagnosis_codes=body.diagnosis_codes,
        units=body.units,
        charge_amount_cents=body.charge_amount_cents,
        status="pending_review",
        documentation_references=body.documentation_references,
    )
    session.add(row)
    session.flush()
    append_audit_event(
        session,
        actor_user_id=user.id,
        tenant_id=tenant_id,
        action="rcm.charge_created",
        subject_type="EncounterCharge",
        subject_id=row.id,
        request_id=_request_id(request),
    )
    response.headers["Cache-Control"] = "no-store"
    return _charge_read(row)


@router.post(
    "/tenants/{tenant_id}/charges/{charge_id}/ai-review",
    response_model=ChargeRead,
)
def ai_review_charge(
    tenant_id: str,
    charge_id: str,
    response: Response,
    user: User = Depends(get_current_user),
    membership: TenantMembership = Depends(require_role(*BILLING_ROLES, "provider")),
    session: Session = Depends(get_session),
) -> ChargeRead:
    if membership.tenant_id != tenant_id:
        raise ApiError("TENANT_NOT_FOUND", "Tenant not found.", 404)
    _require_rcm(session, tenant_id)
    row = session.execute(
        select(EncounterCharge).where(
            EncounterCharge.tenant_id == tenant_id, EncounterCharge.id == charge_id
        )
    ).scalar_one_or_none()
    if row is None:
        raise ApiError("CHARGE_NOT_FOUND", "Charge not found.", 404)
    row.ai_suggested = True
    row.ai_rationale = (
        f"Sandbox suggestion: verify service code {row.service_code} against documented encounter "
        f"services. AI must not invent services or upcode. Human approval required."
    )
    if not row.documentation_references:
        row.documentation_references = [f"Encounter/{row.encounter_id}"]
    session.flush()
    response.headers["Cache-Control"] = "no-store"
    return _charge_read(row)


@router.post("/tenants/{tenant_id}/charges/{charge_id}/approve", response_model=ChargeRead)
def approve_charge(
    tenant_id: str,
    charge_id: str,
    request: Request,
    response: Response,
    user: User = Depends(get_current_user),
    membership: TenantMembership = Depends(require_role(*BILLING_ROLES)),
    session: Session = Depends(get_session),
) -> ChargeRead:
    if membership.tenant_id != tenant_id:
        raise ApiError("TENANT_NOT_FOUND", "Tenant not found.", 404)
    _require_rcm(session, tenant_id)
    row = session.execute(
        select(EncounterCharge).where(
            EncounterCharge.tenant_id == tenant_id, EncounterCharge.id == charge_id
        )
    ).scalar_one_or_none()
    if row is None:
        raise ApiError("CHARGE_NOT_FOUND", "Charge not found.", 404)
    if row.status == "approved":
        response.headers["Cache-Control"] = "no-store"
        return _charge_read(row)
    row.status = "approved"
    row.approved_by_user_id = user.id
    row.approved_at = utcnow()
    session.flush()
    append_audit_event(
        session,
        actor_user_id=user.id,
        tenant_id=tenant_id,
        action="rcm.charge_approved",
        subject_type="EncounterCharge",
        subject_id=row.id,
        request_id=_request_id(request),
    )
    response.headers["Cache-Control"] = "no-store"
    return _charge_read(row)


@router.post("/tenants/{tenant_id}/claims", response_model=ClaimRead, status_code=201)
def create_claim(
    tenant_id: str,
    body: ClaimCreateWrite,
    request: Request,
    response: Response,
    user: User = Depends(get_current_user),
    membership: TenantMembership = Depends(require_role(*BILLING_ROLES)),
    session: Session = Depends(get_session),
) -> ClaimRead:
    if membership.tenant_id != tenant_id:
        raise ApiError("TENANT_NOT_FOUND", "Tenant not found.", 404)
    _require_rcm(session, tenant_id)
    charges = []
    total = 0
    for charge_id in body.charge_ids:
        charge = session.execute(
            select(EncounterCharge).where(
                EncounterCharge.tenant_id == tenant_id, EncounterCharge.id == charge_id
            )
        ).scalar_one_or_none()
        if charge is None or charge.status != "approved":
            raise ApiError("CHARGE_NOT_APPROVED", "All charges must be approved before claim creation.", 409)
        charges.append(charge)
        total += charge.charge_amount_cents
    diagnoses = body.diagnosis_codes or list(
        {code for charge in charges for code in (charge.diagnosis_codes or [])}
    )
    if not diagnoses:
        raise ApiError("CLAIM_INVALID", "At least one diagnosis code is required.", 422)
    claim = Claim(
        tenant_id=tenant_id,
        patient_id=body.patient_id,
        encounter_id=body.encounter_id,
        payer_id=body.payer_id,
        insurance_policy_id=body.insurance_policy_id,
        billing_provider_user_id=user.id,
        rendering_provider_user_id=body.rendering_provider_user_id,
        claim_number=f"CLM-{uuid4().hex[:10].upper()}",
        diagnosis_codes=diagnoses,
        total_charge_cents=total,
        status="validated",
    )
    session.add(claim)
    session.flush()
    for charge in charges:
        session.add(
            ClaimLine(
                tenant_id=tenant_id,
                claim_id=claim.id,
                charge_id=charge.id,
                service_code=charge.service_code,
                units=charge.units,
                billed_amount_cents=charge.charge_amount_cents,
            )
        )
    session.flush()
    append_audit_event(
        session,
        actor_user_id=user.id,
        tenant_id=tenant_id,
        action="rcm.claim_created",
        subject_type="Claim",
        subject_id=claim.id,
        request_id=_request_id(request),
    )
    response.headers["Cache-Control"] = "no-store"
    return _claim_read(claim)


@router.post("/tenants/{tenant_id}/claims/{claim_id}/approve", response_model=ClaimRead)
def approve_claim(
    tenant_id: str,
    claim_id: str,
    request: Request,
    response: Response,
    user: User = Depends(get_current_user),
    membership: TenantMembership = Depends(require_role(*BILLING_ROLES)),
    session: Session = Depends(get_session),
) -> ClaimRead:
    if membership.tenant_id != tenant_id:
        raise ApiError("TENANT_NOT_FOUND", "Tenant not found.", 404)
    _require_rcm(session, tenant_id)
    claim = session.execute(
        select(Claim).where(Claim.tenant_id == tenant_id, Claim.id == claim_id)
    ).scalar_one_or_none()
    if claim is None:
        raise ApiError("CLAIM_NOT_FOUND", "Claim not found.", 404)
    if claim.status not in {"validated", "approved"}:
        raise ApiError("CLAIM_STATE", "Claim cannot be approved from its current state.", 409)
    claim.status = "approved"
    session.flush()
    append_audit_event(
        session,
        actor_user_id=user.id,
        tenant_id=tenant_id,
        action="rcm.claim_approved",
        subject_type="Claim",
        subject_id=claim.id,
        request_id=_request_id(request),
    )
    response.headers["Cache-Control"] = "no-store"
    return _claim_read(claim)


@router.post(
    "/tenants/{tenant_id}/claims/{claim_id}/submit",
    response_model=ClaimSubmissionRead,
)
def submit_claim(
    tenant_id: str,
    claim_id: str,
    body: ClaimSubmitWrite,
    request: Request,
    response: Response,
    user: User = Depends(get_current_user),
    membership: TenantMembership = Depends(require_role(*BILLING_ROLES)),
    session: Session = Depends(get_session),
) -> ClaimSubmissionRead:
    if membership.tenant_id != tenant_id:
        raise ApiError("TENANT_NOT_FOUND", "Tenant not found.", 404)
    _require_rcm(session, tenant_id)
    existing = session.execute(
        select(ClaimSubmission).where(
            ClaimSubmission.tenant_id == tenant_id,
            ClaimSubmission.idempotency_key == body.idempotency_key,
        )
    ).scalar_one_or_none()
    if existing:
        response.headers["Cache-Control"] = "no-store"
        return ClaimSubmissionRead(
            submission_id=existing.id,
            claim_id=existing.claim_id,
            clearinghouse_reference=existing.clearinghouse_reference,
            submission_status=existing.submission_status,
            acknowledgment_code=existing.acknowledgment_code,
            submitted_at=existing.submitted_at,
        )
    claim = session.execute(
        select(Claim).where(Claim.tenant_id == tenant_id, Claim.id == claim_id)
    ).scalar_one_or_none()
    if claim is None:
        raise ApiError("CLAIM_NOT_FOUND", "Claim not found.", 404)
    if claim.status != "approved":
        raise ApiError("CLAIM_NOT_APPROVED", "Approve the claim before sandbox submission.", 409)
    result = build_clearinghouse_adapter().submit_professional_claim(
        claim_number=claim.claim_number,
        total_charge_cents=claim.total_charge_cents,
        force_reject=body.force_reject,
    )
    submission = ClaimSubmission(
        tenant_id=tenant_id,
        claim_id=claim.id,
        clearinghouse_reference=result.clearinghouse_reference,
        submission_status=result.submission_status,
        acknowledgment_code=result.acknowledgment_code,
        response_payload=result.response_payload,
        idempotency_key=body.idempotency_key,
    )
    session.add(submission)
    claim.clearinghouse_reference = result.clearinghouse_reference
    claim.payer_claim_reference = result.payer_claim_reference
    claim.status = "rejected" if result.submission_status == "rejected" else "accepted"
    session.flush()
    append_audit_event(
        session,
        actor_user_id=user.id,
        tenant_id=tenant_id,
        action="rcm.claim_submitted",
        subject_type="ClaimSubmission",
        subject_id=submission.id,
        request_id=_request_id(request),
    )
    response.headers["Cache-Control"] = "no-store"
    return ClaimSubmissionRead(
        submission_id=submission.id,
        claim_id=submission.claim_id,
        clearinghouse_reference=submission.clearinghouse_reference,
        submission_status=submission.submission_status,
        acknowledgment_code=submission.acknowledgment_code,
        submitted_at=submission.submitted_at,
    )


@router.get("/tenants/{tenant_id}/rcm/denials", response_model=list[DenialRead])
def list_denials(
    tenant_id: str,
    response: Response,
    user: User = Depends(get_current_user),
    membership: TenantMembership = Depends(require_role(*BILLING_ROLES)),
    session: Session = Depends(get_session),
) -> list[DenialRead]:
    if membership.tenant_id != tenant_id:
        raise ApiError("TENANT_NOT_FOUND", "Tenant not found.", 404)
    _require_rcm(session, tenant_id)
    rows = session.execute(
        select(ClaimDenial)
        .where(ClaimDenial.tenant_id == tenant_id)
        .order_by(ClaimDenial.created_at.desc())
        .limit(100)
    ).scalars()
    response.headers["Cache-Control"] = "no-store"
    return [
        DenialRead(
            denial_id=row.id,
            claim_id=row.claim_id,
            denial_code=row.denial_code,
            denial_category=row.denial_category,
            denied_amount_cents=row.denied_amount_cents,
            status=row.status,
            assigned_to_user_id=row.assigned_to_user_id,
            created_at=row.created_at,
        )
        for row in rows
    ]


@router.post("/tenants/{tenant_id}/rcm/denials/{denial_id}/assign", response_model=DenialRead)
def assign_denial(
    tenant_id: str,
    denial_id: str,
    body: DenialAssignWrite,
    response: Response,
    user: User = Depends(get_current_user),
    membership: TenantMembership = Depends(require_role(*BILLING_ROLES)),
    session: Session = Depends(get_session),
) -> DenialRead:
    if membership.tenant_id != tenant_id:
        raise ApiError("TENANT_NOT_FOUND", "Tenant not found.", 404)
    denial = session.execute(
        select(ClaimDenial).where(ClaimDenial.tenant_id == tenant_id, ClaimDenial.id == denial_id)
    ).scalar_one_or_none()
    if denial is None:
        raise ApiError("DENIAL_NOT_FOUND", "Denial not found.", 404)
    denial.assigned_to_user_id = body.assigned_to_user_id
    denial.status = "assigned"
    session.flush()
    response.headers["Cache-Control"] = "no-store"
    return DenialRead(
        denial_id=denial.id,
        claim_id=denial.claim_id,
        denial_code=denial.denial_code,
        denial_category=denial.denial_category,
        denied_amount_cents=denial.denied_amount_cents,
        status=denial.status,
        assigned_to_user_id=denial.assigned_to_user_id,
        created_at=denial.created_at,
    )


@router.post("/tenants/{tenant_id}/rcm/denials/{denial_id}/resolve", response_model=DenialRead)
def resolve_denial(
    tenant_id: str,
    denial_id: str,
    body: DenialResolveWrite,
    response: Response,
    user: User = Depends(get_current_user),
    membership: TenantMembership = Depends(require_role(*BILLING_ROLES)),
    session: Session = Depends(get_session),
) -> DenialRead:
    if membership.tenant_id != tenant_id:
        raise ApiError("TENANT_NOT_FOUND", "Tenant not found.", 404)
    denial = session.execute(
        select(ClaimDenial).where(ClaimDenial.tenant_id == tenant_id, ClaimDenial.id == denial_id)
    ).scalar_one_or_none()
    if denial is None:
        raise ApiError("DENIAL_NOT_FOUND", "Denial not found.", 404)
    denial.status = "resolved"
    denial.resolution_notes = body.resolution_notes
    denial.resolved_at = utcnow()
    session.flush()
    response.headers["Cache-Control"] = "no-store"
    return DenialRead(
        denial_id=denial.id,
        claim_id=denial.claim_id,
        denial_code=denial.denial_code,
        denial_category=denial.denial_category,
        denied_amount_cents=denial.denied_amount_cents,
        status=denial.status,
        assigned_to_user_id=denial.assigned_to_user_id,
        created_at=denial.created_at,
    )


@router.post(
    "/tenants/{tenant_id}/rcm/remittances/import",
    response_model=RemittanceRead,
    status_code=201,
)
def import_remittance(
    tenant_id: str,
    body: RemittanceImportWrite,
    request: Request,
    response: Response,
    user: User = Depends(get_current_user),
    membership: TenantMembership = Depends(require_role(*BILLING_ROLES)),
    session: Session = Depends(get_session),
) -> RemittanceRead:
    if membership.tenant_id != tenant_id:
        raise ApiError("TENANT_NOT_FOUND", "Tenant not found.", 404)
    _require_rcm(session, tenant_id)
    claim = session.execute(
        select(Claim).where(Claim.tenant_id == tenant_id, Claim.id == body.claim_id)
    ).scalar_one_or_none()
    if claim is None:
        raise ApiError("CLAIM_NOT_FOUND", "Claim not found.", 404)
    if claim.status not in {"accepted", "paid", "partial", "denied"}:
        raise ApiError("CLAIM_NOT_SUBMITTED", "Import remittance only for accepted sandbox claims.", 409)
    batch = build_clearinghouse_adapter().build_sandbox_remittance(
        claim_number=claim.claim_number,
        total_charge_cents=claim.total_charge_cents,
        deny=body.deny,
    )
    remit = PayerRemittance(
        tenant_id=tenant_id,
        payer_id=claim.payer_id,
        remittance_reference=batch.remittance_reference,
        payment_date=date.today(),
        total_amount_cents=batch.total_amount_cents,
        status="posted",
    )
    session.add(remit)
    session.flush()
    for line in batch.lines:
        if line.denial_code:
            denial = ClaimDenial(
                tenant_id=tenant_id,
                claim_id=claim.id,
                denial_code=line.denial_code,
                denial_category=line.denial_category or "other",
                denial_reason="Sandbox payer denial from remittance import.",
                denied_amount_cents=claim.total_charge_cents,
                status="open",
            )
            session.add(denial)
            claim.status = "denied"
            continue
        if line.paid_cents:
            session.add(
                PaymentAllocation(
                    tenant_id=tenant_id,
                    remittance_id=remit.id,
                    claim_id=claim.id,
                    amount_cents=line.paid_cents,
                    adjustment_type="payment",
                )
            )
            session.add(
                PatientFinancialTransaction(
                    tenant_id=tenant_id,
                    patient_id=claim.patient_id,
                    claim_id=claim.id,
                    transaction_type="insurance_payment",
                    amount_cents=-line.paid_cents,
                    reference=batch.remittance_reference,
                )
            )
        if line.contractual_cents:
            session.add(
                PaymentAllocation(
                    tenant_id=tenant_id,
                    remittance_id=remit.id,
                    claim_id=claim.id,
                    amount_cents=line.contractual_cents,
                    adjustment_type="contractual",
                )
            )
            session.add(
                PatientFinancialTransaction(
                    tenant_id=tenant_id,
                    patient_id=claim.patient_id,
                    claim_id=claim.id,
                    transaction_type="adjustment",
                    amount_cents=-line.contractual_cents,
                    reference=batch.remittance_reference,
                )
            )
        if line.patient_responsibility_cents:
            session.add(
                PaymentAllocation(
                    tenant_id=tenant_id,
                    remittance_id=remit.id,
                    claim_id=claim.id,
                    amount_cents=line.patient_responsibility_cents,
                    adjustment_type="patient_responsibility",
                )
            )
            session.add(
                PatientFinancialTransaction(
                    tenant_id=tenant_id,
                    patient_id=claim.patient_id,
                    claim_id=claim.id,
                    transaction_type="responsibility",
                    amount_cents=line.patient_responsibility_cents,
                    reference=batch.remittance_reference,
                )
            )
            claim.status = "partial"
        else:
            claim.status = "paid"
    # Record original charge responsibility baseline if missing
    existing_charge_txn = session.execute(
        select(PatientFinancialTransaction).where(
            PatientFinancialTransaction.tenant_id == tenant_id,
            PatientFinancialTransaction.claim_id == claim.id,
            PatientFinancialTransaction.transaction_type == "charge",
        )
    ).scalar_one_or_none()
    if existing_charge_txn is None:
        session.add(
            PatientFinancialTransaction(
                tenant_id=tenant_id,
                patient_id=claim.patient_id,
                claim_id=claim.id,
                transaction_type="charge",
                amount_cents=claim.total_charge_cents,
                reference=claim.claim_number,
            )
        )
    session.flush()
    append_audit_event(
        session,
        actor_user_id=user.id,
        tenant_id=tenant_id,
        action="rcm.remittance_imported",
        subject_type="PayerRemittance",
        subject_id=remit.id,
        request_id=_request_id(request),
    )
    response.headers["Cache-Control"] = "no-store"
    return RemittanceRead(
        remittance_id=remit.id,
        remittance_reference=remit.remittance_reference,
        total_amount_cents=remit.total_amount_cents,
        status=remit.status,
        payment_date=remit.payment_date,
    )


@router.get(
    "/tenants/{tenant_id}/patients/{patient_id}/billing",
    response_model=PatientBillingRead,
)
def patient_billing(
    tenant_id: str,
    patient_id: str,
    response: Response,
    user: User = Depends(get_current_user),
    membership: TenantMembership = Depends(require_role(*BILLING_ROLES, "patient")),
    session: Session = Depends(get_session),
) -> PatientBillingRead:
    if membership.tenant_id != tenant_id:
        raise ApiError("TENANT_NOT_FOUND", "Tenant not found.", 404)
    if membership.role == "patient" and user.id != patient_id:
        raise ApiError("PATIENT_NOT_FOUND", "Patient not found.", 404)
    rows = session.execute(
        select(PatientFinancialTransaction)
        .where(
            PatientFinancialTransaction.tenant_id == tenant_id,
            PatientFinancialTransaction.patient_id == patient_id,
        )
        .order_by(PatientFinancialTransaction.created_at.asc())
    ).scalars().all()
    balance = sum(row.amount_cents for row in rows)
    response.headers["Cache-Control"] = "no-store"
    return PatientBillingRead(
        patient_id=patient_id,
        balance_cents=balance,
        transactions=[
            {
                "transaction_id": row.id,
                "transaction_type": row.transaction_type,
                "amount_cents": row.amount_cents,
                "reference": row.reference,
                "created_at": row.created_at.isoformat(),
            }
            for row in rows
        ],
    )


@router.get("/tenants/{tenant_id}/analytics/rcm/overview", response_model=RcmAnalyticsRead)
def rcm_analytics(
    tenant_id: str,
    response: Response,
    user: User = Depends(get_current_user),
    membership: TenantMembership = Depends(require_role(*BILLING_ROLES, "tenant_admin")),
    session: Session = Depends(get_session),
) -> RcmAnalyticsRead:
    if membership.tenant_id != tenant_id:
        raise ApiError("TENANT_NOT_FOUND", "Tenant not found.", 404)
    _require_rcm(session, tenant_id)

    def _count(model, *filters) -> int:
        return int(session.execute(select(func.count()).select_from(model).where(*filters)).scalar_one())

    charges = _count(EncounterCharge, EncounterCharge.tenant_id == tenant_id)
    claims = _count(Claim, Claim.tenant_id == tenant_id)
    accepted = _count(Claim, Claim.tenant_id == tenant_id, Claim.status == "accepted")
    rejected = _count(Claim, Claim.tenant_id == tenant_id, Claim.status == "rejected")
    denied = _count(Claim, Claim.tenant_id == tenant_id, Claim.status == "denied")
    paid = _count(Claim, Claim.tenant_id == tenant_id, Claim.status.in_(("paid", "partial")))
    denials_open = _count(
        ClaimDenial, ClaimDenial.tenant_id == tenant_id, ClaimDenial.status.in_(("open", "assigned"))
    )
    payments = session.execute(
        select(func.coalesce(func.sum(PayerRemittance.total_amount_cents), 0)).where(
            PayerRemittance.tenant_id == tenant_id
        )
    ).scalar_one()
    ar = session.execute(
        select(func.coalesce(func.sum(PatientFinancialTransaction.amount_cents), 0)).where(
            PatientFinancialTransaction.tenant_id == tenant_id
        )
    ).scalar_one()

    response.headers["Cache-Control"] = "no-store"
    return RcmAnalyticsRead(
        overview={
            "charges": charges,
            "claims": claims,
            "accepted": accepted,
            "rejected": rejected,
            "denied": denied,
            "paid_or_partial": paid,
            "payments_posted_cents": int(payments or 0),
            "patient_ar_cents": int(ar or 0),
        },
        ar_aging={
            "0_30": int(ar or 0),
            "31_60": 0,
            "61_90": 0,
            "91_120": 0,
            "120_plus": 0,
            "method": "Sandbox snapshot of ledger balance in 0–30 bucket only.",
        },
        denials={"open_denials": denials_open, "denied_claims": denied},
        collections={"remittance_total_cents": int(payments or 0)},
        notes=[
            "Eligibility verification does not guarantee payment.",
            "Clearinghouse acceptance is not payer payment.",
            "Amounts are synthetic sandbox cents.",
        ],
    )


@router.get("/tenants/{tenant_id}/claims", response_model=list[ClaimRead])
def list_claims(
    tenant_id: str,
    response: Response,
    user: User = Depends(get_current_user),
    membership: TenantMembership = Depends(require_role(*BILLING_ROLES)),
    session: Session = Depends(get_session),
) -> list[ClaimRead]:
    if membership.tenant_id != tenant_id:
        raise ApiError("TENANT_NOT_FOUND", "Tenant not found.", 404)
    _require_rcm(session, tenant_id)
    rows = session.execute(
        select(Claim)
        .where(Claim.tenant_id == tenant_id)
        .order_by(Claim.created_at.desc())
        .limit(100)
    ).scalars()
    response.headers["Cache-Control"] = "no-store"
    return [_claim_read(row) for row in rows]
