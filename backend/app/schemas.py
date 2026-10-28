from __future__ import annotations

from datetime import UTC, datetime, timedelta

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


class ThreadCreate(StrictModel):
    subject: str = Field(min_length=2, max_length=200)
    body: str = Field(min_length=1, max_length=4000)


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
    body: str
    created_at: datetime


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
    """Roster-safe detail. No chart PHI beyond clinic-assigned identifiers."""

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
