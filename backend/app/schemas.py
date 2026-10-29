from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from pydantic import BaseModel, ConfigDict, Field, field_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ErrorDetail(BaseModel):
    code: str
    message: str
    request_id: str = ""


class ErrorResponse(BaseModel):
    error: ErrorDetail


class MembershipRead(StrictModel):
    tenant_id: str
    tenant_name: str
    role: str
    status: str


class UserRead(StrictModel):
    user_id: str
    memberships: list[MembershipRead]


class PatientProfileWrite(StrictModel):
    preferred_name: str = Field(default="", max_length=120)
    legal_name: str = Field(default="", max_length=200)
    phone: str = Field(default="", max_length=40)
    preferred_language: str = Field(default="en", min_length=2, max_length=32)


class PatientProfileRead(PatientProfileWrite):
    user_id: str
    updated_at: datetime


class ProviderProfileWrite(StrictModel):
    display_name: str = Field(default="", max_length=200)
    specialty: str = Field(default="", max_length=120)


class ProviderProfileRead(ProviderProfileWrite):
    user_id: str
    profile_status: str
    updated_at: datetime


class CredentialWrite(StrictModel):
    jurisdiction: str = Field(min_length=2, max_length=32)
    credential_type: str = Field(min_length=2, max_length=96)
    regulator: str = Field(min_length=2, max_length=200)
    verification_reference: str = Field(default="", max_length=512)


class CredentialRead(StrictModel):
    credential_id: str
    jurisdiction: str
    credential_type: str
    regulator: str
    status: str
    submitted_at: datetime
    reviewed_at: datetime | None


class CredentialReviewQueueRead(CredentialRead):
    provider_user_id: str
    provider_display_name: str
    provider_specialty: str


class CredentialReview(StrictModel):
    decision: str = Field(pattern="^(verified|rejected)$")
    review_source: str = Field(min_length=2, max_length=512)


class ConsentWrite(StrictModel):
    purpose: str = Field(min_length=2, max_length=96)
    scope: str = Field(min_length=2, max_length=128)
    policy_version: str = Field(min_length=1, max_length=64)
    expires_at: datetime | None = None


class ConsentRead(StrictModel):
    grant_id: str
    purpose: str
    scope: str
    policy_version: str
    granted_at: datetime
    expires_at: datetime | None
    withdrawn_at: datetime | None


class ConsentWithdrawalWrite(StrictModel):
    reason_code: str = Field(min_length=2, max_length=64)


class DocumentRead(StrictModel):
    document_id: str
    original_filename: str
    content_type: str
    size_bytes: int
    lifecycle_state: str
    created_at: datetime
    clinic_patient_id: str | None = None
    document_reference_id: str | None = None
    processing_status: str | None = None
    document_category: str | None = None


class ExtractionFieldRead(StrictModel):
    name: str
    value: str
    unit: str = ""
    reference_range: str = ""
    effective_date: str = ""
    confidence: float
    source_region: dict[str, object] = Field(default_factory=dict)
    # V1.3 extensions (optional for backward compatibility)
    test_name_raw: str | None = None
    value_raw: str | None = None
    value_numeric: float | None = None
    value_text: str | None = None
    unit_raw: str | None = None
    reference_range_raw: str | None = None
    abnormal_flag_raw: str | None = None
    abnormal_flag: str | None = None
    collection_date: str | None = None
    source_page: int | None = None
    source_text: str | None = None
    source_coordinates: dict[str, object] | None = None
    confidence_metadata: dict[str, object] | None = None
    require_review: bool | None = None
    verification_status: str | None = None
    original_extracted: dict[str, object] | None = None
    correction_reason: str | None = None


class ExtractionRead(StrictModel):
    extraction_id: str
    document_id: str
    document_reference_id: str | None = None
    patient_id: str
    status: str
    fields: list[ExtractionFieldRead]
    ocr_text: str = ""
    created_at: datetime
    verified_at: datetime | None = None
    processing_job_id: str | None = None


class ExtractionVerifyWrite(StrictModel):
    extraction_id: str = Field(min_length=36, max_length=36)
    fields: list[ExtractionFieldRead]


class DocumentProcessingJobRead(StrictModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, protected_namespaces=())

    job_id: str
    document_id: str
    patient_id: str
    job_type: str
    status: str
    attempt_count: int
    processor_version: str
    model_identifier: str
    prompt_version: str
    classification: dict[str, object] = Field(default_factory=dict)
    extraction_id: str | None = None
    error_code: str | None = None
    error_summary: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime


class TrendPointRead(StrictModel):
    observation_id: str
    effective_at: str
    value: float
    unit: str
    reference_low: float | None = None
    reference_high: float | None = None
    reference_range_text: str = ""
    in_range: bool | None = None
    document_reference_id: str | None = None
    extraction_id: str | None = None
    status: str = "final"


class TrendSeriesRead(StrictModel):
    patient_id: str
    test_code: str
    test_label: str
    unit: str
    reference_low: float | None = None
    reference_high: float | None = None
    reference_range_text: str = ""
    point_count: int = 0
    latest_value: float | None = None
    latest_at: str | None = None
    previous_value: float | None = None
    delta: float | None = None
    delta_pct: float | None = None
    min_value: float | None = None
    max_value: float | None = None
    points: list[TrendPointRead]


class TrendTestRead(StrictModel):
    code: str
    label: str
    unit: str
    point_count: int = 0
    latest_value: float | None = None
    latest_at: str | None = None
    has_data: bool = False


class InsightFlagRead(StrictModel):
    code: str
    severity: str
    title: str
    explanation: str
    framing: str = "educational_support_for_clinician_discussion"


class TrendInsightsRead(StrictModel):
    patient_id: str
    test_code: str
    test_label: str
    flags: list[InsightFlagRead]
    disclaimer: str
    point_count: int = 0


class ThreadCreate(StrictModel):
    subject: str = Field(min_length=2, max_length=200)
    body: str = Field(min_length=1, max_length=4000)
    clinic_patient_id: str | None = Field(default=None, min_length=36, max_length=36)


class MessageCreate(StrictModel):
    body: str = Field(min_length=1, max_length=4000)


class ThreadRead(StrictModel):
    thread_id: str
    clinic_patient_id: str
    subject: str
    status: str
    created_at: datetime
    updated_at: datetime
    message_count: int


class MessageRead(StrictModel):
    message_id: str
    thread_id: str
    sender_user_id: str
    sender_role: str | None = None
    body: str
    created_at: datetime


class ChartNumberWrite(StrictModel):
    chart_number: str | None = Field(default=None, max_length=96)


class ClinicOnboardingWrite(StrictModel):
    slug: str = Field(min_length=3, max_length=96, pattern="^[a-z0-9]+(?:-[a-z0-9]+)*$")
    display_name: str = Field(min_length=2, max_length=200)
    location_name: str = Field(min_length=2, max_length=160)
    timezone: str = Field(min_length=1, max_length=64)


class LocationWrite(StrictModel):
    name: str = Field(min_length=2, max_length=160)
    timezone: str = Field(min_length=1, max_length=64)


class LocationRead(StrictModel):
    location_id: str
    name: str
    timezone: str


class ClinicRead(StrictModel):
    tenant_id: str
    slug: str
    display_name: str
    role: str
    location_id: str
    location_name: str
    timezone: str


class PlatformTenantProvisionWrite(ClinicOnboardingWrite):
    owner_user_id: str = Field(min_length=1, max_length=36)


class PlatformTenantRead(StrictModel):
    tenant_id: str
    slug: str
    display_name: str
    status: str
    created_at: datetime


class SupportAccessRequestWrite(StrictModel):
    tenant_id: str = Field(min_length=1, max_length=36)
    ticket_reference: str = Field(
        min_length=3,
        max_length=128,
        pattern="^[A-Za-z0-9._-]+$",
    )
    purpose: str = Field(
        pattern="^(account_configuration|billing_support|"
        "security_investigation|service_availability)$"
    )
    requested_until: datetime

    @field_validator("requested_until")
    @classmethod
    def validate_requested_until(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("requested_until must include a timezone.")
        now = datetime.now(UTC)
        requested_until = value.astimezone(UTC)
        if requested_until <= now or requested_until > now + timedelta(hours=8):
            raise ValueError("requested_until must be within the next eight hours.")
        return requested_until


class SupportAccessRequestRead(StrictModel):
    request_id: str
    tenant_id: str
    requested_by_user_id: str
    ticket_reference: str
    purpose: str
    requested_until: datetime
    status: str
    created_at: datetime


class InvitationWrite(StrictModel):
    role: str = Field(pattern="^(staff|patient|provider)$")


class InvitationCreated(StrictModel):
    invitation_id: str
    role: str
    invitation_code: str
    expires_at: datetime


class InvitationRead(StrictModel):
    invitation_id: str
    role: str
    status: str
    expires_at: datetime
    created_at: datetime


class InvitationAcceptWrite(StrictModel):
    invitation_code: str = Field(min_length=32, max_length=128)


class MemberRead(StrictModel):
    user_id: str
    role: str
    status: str
    created_at: datetime


class ClinicPatientRead(StrictModel):
    clinic_patient_id: str
    chart_number: str | None
    status: str
    created_at: datetime


class ClinicPatientDetailRead(ClinicPatientRead):
    """Roster-safe detail plus FHIR Patient id for consent-gated chart views."""

    patient_user_id: str
    document_count: int = 0
    open_thread_count: int = 0
    upcoming_appointment_count: int = 0


class AvailabilityWrite(StrictModel):
    location_id: str
    starts_at: datetime

    @field_validator("starts_at")
    @classmethod
    def validate_slot_time(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("starts_at must include a timezone.")
        utc_value = value.astimezone(UTC)
        if utc_value.minute not in (0, 30) or utc_value.second or utc_value.microsecond:
            raise ValueError("Availability starts on a 30-minute UTC boundary.")
        return value


class AvailabilityRead(StrictModel):
    availability_id: str
    tenant_id: str
    provider_user_id: str
    provider_name: str
    location_id: str
    location_name: str
    timezone: str
    starts_at: datetime
    ends_at: datetime
    status: str


class AppointmentCreate(StrictModel):
    availability_id: str
    idempotency_key: str = Field(min_length=8, max_length=128)


class AppointmentRescheduleWrite(StrictModel):
    availability_id: str


class AppointmentRead(StrictModel):
    appointment_id: str
    tenant_id: str
    clinic_patient_id: str
    provider_user_id: str
    provider_name: str
    location_id: str
    location_name: str
    timezone: str
    starts_at: datetime
    ends_at: datetime
    status: str
    created_at: datetime
    session_id: str | None = None
    session_status: str | None = None


class SessionCreate(StrictModel):
    appointment_id: str = Field(min_length=36, max_length=36)


class SessionJoinRead(StrictModel):
    session_id: str
    appointment_id: str
    status: str
    video_provider: str
    room_id: str
    role: str
    token: str
    join_url: str
    expires_in_seconds: int
    patient_user_id: str
    provider_user_id: str
    clinic_patient_id: str
    encounter_id: str | None = None
    follow_up_plan: str = ""


class SessionRead(StrictModel):
    session_id: str
    appointment_id: str
    status: str
    video_provider: str
    room_id: str
    patient_user_id: str
    provider_user_id: str
    clinic_patient_id: str
    encounter_id: str | None = None
    follow_up_plan: str = ""
    created_at: datetime
    started_at: datetime | None = None
    ended_at: datetime | None = None


class SessionCompleteWrite(StrictModel):
    follow_up_plan: str = Field(default="", max_length=4000)


class WaitingRoomEntryRead(StrictModel):
    entry_id: str
    appointment_id: str
    session_id: str | None = None
    patient_user_id: str
    provider_user_id: str
    clinic_patient_id: str
    status: str
    checked_in_at: datetime | None = None
    admitted_at: datetime | None = None
    left_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class ClinicalNoteWrite(StrictModel):
    patient_id: str = Field(min_length=36, max_length=36)
    session_id: str | None = Field(default=None, min_length=36, max_length=36)
    appointment_id: str | None = Field(default=None, min_length=36, max_length=36)
    subjective: str = Field(default="", max_length=8000)
    objective: str = Field(default="", max_length=8000)
    assessment: str = Field(default="", max_length=8000)
    plan: str = Field(default="", max_length=8000)
    ai_assisted: bool = False
    source_draft_id: str | None = Field(default=None, min_length=36, max_length=36)
    expected_version: int | None = None


class ClinicalNoteRead(StrictModel):
    note_id: str
    patient_id: str
    author_user_id: str
    session_id: str | None = None
    encounter_id: str | None = None
    appointment_id: str | None = None
    note_type: str
    subjective: str
    objective: str
    assessment: str
    plan: str
    status: str
    version: int
    ai_assisted: bool
    source_draft_id: str | None = None
    signed_by_user_id: str | None = None
    signed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class ClinicalNoteAmendWrite(StrictModel):
    subjective: str | None = Field(default=None, max_length=8000)
    objective: str | None = Field(default=None, max_length=8000)
    assessment: str | None = Field(default=None, max_length=8000)
    plan: str | None = Field(default=None, max_length=8000)
    change_reason: str = Field(min_length=2, max_length=200)
    expected_version: int


class FollowUpPlanWrite(StrictModel):
    patient_id: str = Field(min_length=36, max_length=36)
    session_id: str | None = Field(default=None, min_length=36, max_length=36)
    appointment_id: str | None = Field(default=None, min_length=36, max_length=36)
    instructions: str = Field(default="", max_length=8000)
    tasks: list[dict[str, object]] = Field(default_factory=list)


class FollowUpPlanRead(StrictModel):
    plan_id: str
    patient_id: str
    provider_user_id: str
    session_id: str | None = None
    encounter_id: str | None = None
    appointment_id: str | None = None
    status: str
    instructions: str
    tasks: list[dict[str, object]]
    approved_by_user_id: str | None = None
    approved_at: datetime | None = None
    published_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class ClinicalDraftCreate(StrictModel):
    patient_id: str = Field(min_length=36, max_length=36)
    session_id: str | None = Field(default=None, min_length=36, max_length=36)


class ClinicalDraftRead(StrictModel):
    draft_id: str
    patient_id: str
    draft_type: str
    status: str
    title: str
    content: dict[str, object]
    source_links: list[dict[str, object]]
    session_id: str | None = None
    encounter_id: str | None = None
    approved_resource_id: str | None = None
    created_at: datetime
    approved_at: datetime | None = None


class ClinicalDraftApproveWrite(StrictModel):
    edited_content: dict[str, object] | None = None
    edited_title: str | None = Field(default=None, max_length=200)


class DemoSeedRead(StrictModel):
    tenant_id: str
    tenant_name: str
    slug: str
    created: bool
    clinic_patient_id: str
    patient_user_id: str
    provider_user_id: str
    location_id: str
    document_id: str
    open_availability_slots: int
    personas: dict[str, str]


class TimelineEventRead(StrictModel):
    event_id: str
    kind: str
    title: str
    summary: str
    status: str
    occurred_at: datetime
    resource_type: str
    resource_id: str
    source_document_id: str | None = None
    href_hint: str = ""


class TimelineRead(StrictModel):
    patient_user_id: str
    events: list[TimelineEventRead]


class WorkboardAppointment(StrictModel):
    appointment_id: str
    clinic_patient_id: str
    chart_number: str = ""
    starts_at: datetime
    ends_at: datetime
    provider_user_id: str
    provider_name: str = ""
    location_name: str = ""
    timezone: str = "UTC"
    status: str = "booked"
    appointment_type: str = "Visit"


class WorkboardSession(StrictModel):
    session_id: str
    clinic_patient_id: str
    status: str
    appointment_id: str
    provider_user_id: str
    created_at: datetime


class WorkboardExtraction(StrictModel):
    extraction_id: str
    document_id: str
    patient_user_id: str
    clinic_patient_id: str | None = None
    field_count: int
    created_at: datetime


class WorkboardDraft(StrictModel):
    draft_id: str
    draft_type: str
    patient_id: str
    title: str
    session_id: str | None = None
    created_at: datetime


class WorkboardCounts(StrictModel):
    today_appointments: int
    waiting_sessions: int
    pending_extractions: int
    pending_drafts: int


class ClinicalWorkboardRead(StrictModel):
    today_appointments: list[WorkboardAppointment]
    waiting_sessions: list[WorkboardSession]
    pending_extractions: list[WorkboardExtraction]
    pending_drafts: list[WorkboardDraft]
    counts: WorkboardCounts


# --- V1.5 AI Clinical Copilot ---


class AiGenerationRead(StrictModel):
    model_config = ConfigDict(
        extra="forbid", str_strip_whitespace=True, protected_namespaces=()
    )

    generation_id: str
    module: str
    model_identifier: str
    prompt_version: str
    status: str
    source_references: list[dict[str, object]]
    output_reference: str | None = None
    usage_metadata: dict[str, object]
    created_at: datetime


class ScribeStartWrite(StrictModel):
    patient_id: str = Field(min_length=36, max_length=36)
    mode: str = Field(default="manual", pattern="^(manual|ambient)$")
    appointment_id: str | None = Field(default=None, min_length=36, max_length=36)
    session_id: str | None = Field(default=None, min_length=36, max_length=36)
    visit_reason: str = Field(default="", max_length=2000)
    clinician_notes: str = Field(default="", max_length=8000)


class ScribeSessionRead(StrictModel):
    scribe_session_id: str
    patient_id: str
    mode: str
    status: str
    speech_provider: str
    consent_grant_id: str | None = None
    started_at: datetime | None = None
    stopped_at: datetime | None = None
    created_at: datetime


class TranscriptSegmentRead(StrictModel):
    segment_id: str
    speaker_label: str
    start_offset_ms: int
    end_offset_ms: int
    transcript_text: str
    confidence_metadata: dict[str, object]


class ScribeGenerateNoteWrite(StrictModel):
    visit_reason: str = Field(default="", max_length=2000)
    clinician_notes: str = Field(default="", max_length=8000)


class SoapDraftRead(StrictModel):
    generation_id: str
    draft_id: str | None = None
    subjective: str
    objective: str
    assessment: str
    plan: str
    source_links: list[dict[str, object]]
    disclaimer: str


class QualityFindingRead(StrictModel):
    finding_id: str
    clinical_note_id: str
    note_version: int
    finding_type: str
    severity: str
    description: str
    source_reference: str
    suggested_action: str
    review_status: str
    created_at: datetime


class QualityFindingReviewWrite(StrictModel):
    action: str = Field(pattern="^(accept|dismiss)$")
    dismiss_reason: str = Field(default="", max_length=200)


class AiMessageDraftCreate(StrictModel):
    source_message_id: str | None = Field(default=None, min_length=36, max_length=36)


class AiMessageDraftRead(StrictModel):
    draft_id: str
    thread_id: str
    category: str
    generated_content: str
    edited_content: str
    status: str
    sent_message_id: str | None = None
    created_at: datetime


class AiMessageDraftEditWrite(StrictModel):
    edited_content: str = Field(min_length=1, max_length=8000)


class AiMessageDraftSendWrite(StrictModel):
    idempotency_key: str = Field(min_length=8, max_length=128)
    body: str | None = Field(default=None, max_length=8000)


class PatientEducationAskWrite(StrictModel):
    question: str = Field(min_length=3, max_length=2000)


class PatientEducationRead(StrictModel):
    education_id: str
    topic: str
    question: str
    answer: str
    source_references: list[dict[str, object]]
    escalated: bool
    status: str
    created_at: datetime


class CareTaskSuggestRead(StrictModel):
    suggestions: list[dict[str, object]]
    generation_id: str


class CareTaskCreateWrite(StrictModel):
    description: str = Field(min_length=2, max_length=800)
    task_category: str = Field(default="follow_up", max_length=64)
    assigned_role: str = Field(default="patient", max_length=32)
    idempotency_key: str | None = Field(default=None, max_length=128)


class CareTaskRead(StrictModel):
    task_id: str
    follow_up_plan_id: str
    patient_id: str
    task_category: str
    description: str
    assigned_role: str
    status: str
    due_at: datetime | None = None
    created_at: datetime
    completed_at: datetime | None = None


class CareTaskPatchWrite(StrictModel):
    status: str = Field(pattern="^(open|in_progress|completed|cancelled)$")


class WorkflowAnalyticsRead(StrictModel):
    documentation: dict[str, object]
    ai_scribe: dict[str, object]
    messaging: dict[str, object]
    care_coordination: dict[str, object]
    ai_operations: dict[str, object]


# --- V1.6 RCM & SaaS ---


class InsurancePayerWrite(StrictModel):
    name: str = Field(default="Sandbox Payer", max_length=200)
    payer_identifier: str = Field(default="", max_length=64)


class InsurancePayerRead(StrictModel):
    payer_id: str
    name: str
    payer_identifier: str
    status: str


class InsurancePolicyWrite(StrictModel):
    patient_id: str = Field(min_length=36, max_length=36)
    payer_id: str = Field(min_length=36, max_length=36)
    plan_name: str = Field(default="", max_length=200)
    member_identifier: str = Field(min_length=2, max_length=64)
    group_identifier: str = Field(default="", max_length=64)
    subscriber_name: str = Field(default="", max_length=200)
    subscriber_relationship: str = Field(default="self", max_length=32)
    coverage_order: int = Field(default=1, ge=1, le=3)
    effective_date: date | None = None
    termination_date: date | None = None


class InsurancePolicyRead(StrictModel):
    policy_id: str
    patient_id: str
    payer_id: str
    plan_name: str
    member_identifier: str
    group_identifier: str
    coverage_order: int
    status: str
    effective_date: date | None = None
    termination_date: date | None = None


class EligibilityVerifyWrite(StrictModel):
    appointment_id: str | None = Field(default=None, min_length=36, max_length=36)


class EligibilityCheckRead(StrictModel):
    eligibility_id: str
    patient_id: str
    insurance_policy_id: str
    coverage_status: str
    financial_readiness: str
    benefits_summary: dict[str, object]
    disclaimer: str
    request_reference: str
    response_reference: str
    checked_at: datetime


class ChargeWrite(StrictModel):
    encounter_id: str = Field(min_length=8, max_length=36)
    patient_id: str = Field(min_length=36, max_length=36)
    provider_user_id: str = Field(min_length=36, max_length=36)
    service_date: date
    service_code: str = Field(min_length=2, max_length=32)
    service_code_system: str = Field(default="CPT", max_length=16)
    diagnosis_codes: list[str] = Field(default_factory=list)
    units: int = Field(default=1, ge=1, le=99)
    charge_amount_cents: int = Field(ge=0, le=10_000_000)
    documentation_references: list[str] = Field(default_factory=list)


class ChargeRead(StrictModel):
    charge_id: str
    encounter_id: str
    patient_id: str
    service_code: str
    diagnosis_codes: list[str]
    units: int
    charge_amount_cents: int
    status: str
    ai_suggested: bool
    ai_rationale: str
    created_at: datetime


class ClaimCreateWrite(StrictModel):
    patient_id: str = Field(min_length=36, max_length=36)
    encounter_id: str = Field(min_length=8, max_length=36)
    payer_id: str = Field(min_length=36, max_length=36)
    insurance_policy_id: str | None = Field(default=None, min_length=36, max_length=36)
    rendering_provider_user_id: str = Field(min_length=36, max_length=36)
    charge_ids: list[str] = Field(min_length=1)
    diagnosis_codes: list[str] = Field(default_factory=list)


class ClaimRead(StrictModel):
    claim_id: str
    claim_number: str
    patient_id: str
    encounter_id: str
    payer_id: str
    status: str
    total_charge_cents: int
    payer_claim_reference: str
    clearinghouse_reference: str
    created_at: datetime


class ClaimSubmitWrite(StrictModel):
    idempotency_key: str = Field(min_length=8, max_length=128)
    force_reject: bool = False


class ClaimSubmissionRead(StrictModel):
    submission_id: str
    claim_id: str
    clearinghouse_reference: str
    submission_status: str
    acknowledgment_code: str
    submitted_at: datetime


class DenialRead(StrictModel):
    denial_id: str
    claim_id: str
    denial_code: str
    denial_category: str
    denied_amount_cents: int
    status: str
    assigned_to_user_id: str | None = None
    created_at: datetime


class DenialAssignWrite(StrictModel):
    assigned_to_user_id: str = Field(min_length=36, max_length=36)


class DenialResolveWrite(StrictModel):
    resolution_notes: str = Field(min_length=2, max_length=2000)


class RemittanceImportWrite(StrictModel):
    claim_id: str = Field(min_length=36, max_length=36)
    deny: bool = False


class RemittanceRead(StrictModel):
    remittance_id: str
    remittance_reference: str
    total_amount_cents: int
    status: str
    payment_date: date


class PatientBillingRead(StrictModel):
    patient_id: str
    balance_cents: int
    transactions: list[dict[str, object]]


class RcmAnalyticsRead(StrictModel):
    overview: dict[str, object]
    ar_aging: dict[str, object]
    denials: dict[str, object]
    collections: dict[str, object]
    notes: list[str]


class SubscriptionPlanRead(StrictModel):
    plan_id: str
    plan_code: str
    name: str
    billing_model: str
    feature_codes: list[str]
    status: str


class SubscriptionActivateWrite(StrictModel):
    plan_code: str = Field(min_length=2, max_length=64)


class OrganizationSubscriptionRead(StrictModel):
    subscription_id: str
    tenant_id: str
    plan_code: str
    status: str
    payment_provider_reference: str
    billing_period_start: date | None = None
    billing_period_end: date | None = None


class EntitlementRead(StrictModel):
    feature_code: str
    enabled: bool
    limit_value: int | None = None


class UsageMeterWrite(StrictModel):
    meter_type: str = Field(min_length=2, max_length=64)
    quantity: int = Field(ge=1, le=1_000_000)
    source_event_id: str = Field(min_length=4, max_length=128)
    billing_period_reference: str = Field(default="", max_length=64)


class UsageMeterRead(StrictModel):
    meter_event_id: str
    meter_type: str
    quantity: int
    source_event_id: str
    occurred_at: datetime
