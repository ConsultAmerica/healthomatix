from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    UniqueConstraint,
    event,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def new_id() -> str:
    return str(uuid4())


def utcnow() -> datetime:
    return datetime.now(UTC)


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("issuer", "subject", name="uq_users_issuer_subject"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    issuer: Mapped[str] = mapped_column(String(512), nullable=False)
    subject: Mapped[str] = mapped_column(String(512), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )


class Tenant(Base):
    __tablename__ = "tenants"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    slug: Mapped[str] = mapped_column(String(96), nullable=False, unique=True)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="active", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )


class TenantMembership(Base):
    __tablename__ = "tenant_memberships"
    __table_args__ = (
        UniqueConstraint("tenant_id", "user_id", name="uq_membership_tenant_user"),
        CheckConstraint(
            "role IN ('tenant_admin', 'staff', 'patient', 'provider', 'auditor')",
            name="ck_membership_role",
        ),
        CheckConstraint(
            "status IN ('active', 'inactive', 'revoked')",
            name="ck_membership_status",
        ),
        Index("ix_membership_user_status", "user_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str] = mapped_column(String(24), nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="active", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )


class PatientProfile(Base):
    __tablename__ = "patient_profiles"

    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    preferred_name: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    legal_name: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    phone: Mapped[str] = mapped_column(String(40), default="", nullable=False)
    preferred_language: Mapped[str] = mapped_column(String(32), default="en", nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )


class ClinicPatient(Base):
    __tablename__ = "clinic_patients"
    __table_args__ = (
        UniqueConstraint("tenant_id", "patient_user_id", name="uq_clinic_patient_identity"),
        UniqueConstraint("tenant_id", "id", name="uq_clinic_patient_tenant_id"),
        UniqueConstraint(
            "tenant_id",
            "id",
            "patient_user_id",
            name="uq_clinic_patient_tenant_id_user",
        ),
        UniqueConstraint("tenant_id", "chart_number", name="uq_clinic_patient_chart_number"),
        CheckConstraint(
            "status IN ('active', 'inactive', 'merged')",
            name="ck_clinic_patient_status",
        ),
        Index("ix_clinic_patient_tenant_status", "tenant_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    patient_user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    chart_number: Mapped[str | None] = mapped_column(String(96))
    status: Mapped[str] = mapped_column(String(16), default="active", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )


class ProviderProfile(Base):
    __tablename__ = "provider_profiles"
    __table_args__ = (
        CheckConstraint(
            "profile_status IN ('draft', 'pending', 'active', 'suspended')",
            name="ck_provider_profile_status",
        ),
    )

    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    display_name: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    specialty: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    profile_status: Mapped[str] = mapped_column(
        String(16), default="draft", nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )


class ProviderCredential(Base):
    __tablename__ = "provider_credentials"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'verified', 'rejected', 'revoked')",
            name="ck_provider_credential_status",
        ),
        Index("ix_provider_credential_tenant_status", "tenant_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    provider_user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    jurisdiction: Mapped[str] = mapped_column(String(32), nullable=False)
    credential_type: Mapped[str] = mapped_column(String(96), nullable=False)
    regulator: Mapped[str] = mapped_column(String(200), nullable=False)
    verification_reference: Mapped[str] = mapped_column(
        String(512), default="", nullable=False
    )
    status: Mapped[str] = mapped_column(String(16), default="pending", nullable=False)
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    reviewed_by_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    review_source: Mapped[str] = mapped_column(String(512), default="", nullable=False)


class ConsentGrant(Base):
    __tablename__ = "consent_grants"
    __table_args__ = (
        Index(
            "ix_consent_grant_patient_scope",
            "tenant_id",
            "patient_user_id",
            "purpose",
            "scope",
            "granted_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    patient_user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    granted_by_user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    purpose: Mapped[str] = mapped_column(String(96), nullable=False)
    scope: Mapped[str] = mapped_column(String(128), nullable=False)
    policy_version: Mapped[str] = mapped_column(String(64), nullable=False)
    granted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ConsentWithdrawal(Base):
    __tablename__ = "consent_withdrawals"
    __table_args__ = (UniqueConstraint("grant_id", name="uq_consent_withdrawal_grant"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    grant_id: Mapped[str] = mapped_column(
        ForeignKey("consent_grants.id", ondelete="RESTRICT"), nullable=False
    )
    actor_user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    reason_code: Mapped[str] = mapped_column(String(64), nullable=False)
    withdrawn_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )


class MedicalDocument(Base):
    __tablename__ = "medical_documents"
    __table_args__ = (
        CheckConstraint(
            "lifecycle_state IN ('reserved', 'stored', 'quarantined', 'deleted')",
            name="ck_medical_document_lifecycle",
        ),
        Index("ix_medical_document_patient_created", "tenant_id", "patient_user_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    patient_user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    uploaded_by_user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    storage_key: Mapped[str] = mapped_column(String(1024), nullable=False, unique=True)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(128), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    lifecycle_state: Mapped[str] = mapped_column(
        String(16), default="reserved", nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )


class AuditEvent(Base):
    __tablename__ = "audit_events"
    __table_args__ = (
        Index("ix_audit_events_tenant_time", "tenant_id", "created_at"),
        CheckConstraint(
            "length(action) BETWEEN 1 AND 128",
            name="ck_audit_event_action_length",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    tenant_id: Mapped[str | None] = mapped_column(
        ForeignKey("tenants.id", ondelete="SET NULL"), nullable=True
    )
    actor_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    action: Mapped[str] = mapped_column(String(128), nullable=False)
    subject_type: Mapped[str] = mapped_column(String(64), nullable=False)
    subject_id: Mapped[str] = mapped_column(String(128), nullable=False)
    request_id: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )


class ClinicLocation(Base):
    __tablename__ = "clinic_locations"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_clinic_location_tenant_id"),
        UniqueConstraint("tenant_id", "name", name="uq_clinic_location_name"),
        CheckConstraint(
            "status IN ('active', 'inactive')",
            name="ck_clinic_location_status",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="active", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )


class ClinicInvitation(Base):
    __tablename__ = "clinic_invitations"
    __table_args__ = (
        CheckConstraint(
            "role IN ('staff', 'patient', 'provider')",
            name="ck_clinic_invitation_role",
        ),
        CheckConstraint(
            "status IN ('pending', 'accepted', 'revoked', 'expired')",
            name="ck_clinic_invitation_status",
        ),
        Index("ix_clinic_invitation_tenant_status", "tenant_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    role: Mapped[str] = mapped_column(String(24), nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="pending", nullable=False)
    created_by_user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    accepted_by_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ProviderAvailability(Base):
    __tablename__ = "provider_availability"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_availability_tenant_id"),
        UniqueConstraint(
            "tenant_id",
            "provider_user_id",
            "starts_at",
            name="uq_availability_provider_start",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "provider_user_id"],
            ["tenant_memberships.tenant_id", "tenant_memberships.user_id"],
            ondelete="CASCADE",
            name="fk_availability_provider_membership",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "location_id"],
            ["clinic_locations.tenant_id", "clinic_locations.id"],
            ondelete="CASCADE",
            name="fk_availability_tenant_location",
        ),
        CheckConstraint("status IN ('open', 'booked')", name="ck_availability_status"),
        CheckConstraint("ends_at > starts_at", name="ck_availability_time_order"),
        Index("ix_availability_tenant_start_status", "tenant_id", "starts_at", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    provider_user_id: Mapped[str] = mapped_column(String(36), nullable=False)
    location_id: Mapped[str] = mapped_column(String(36), nullable=False)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="open", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )


class Appointment(Base):
    __tablename__ = "appointments"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_appointment_tenant_id"),
        ForeignKeyConstraint(
            ["tenant_id", "clinic_patient_id", "patient_user_id"],
            [
                "clinic_patients.tenant_id",
                "clinic_patients.id",
                "clinic_patients.patient_user_id",
            ],
            ondelete="CASCADE",
            name="fk_appointment_tenant_patient",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "availability_id"],
            ["provider_availability.tenant_id", "provider_availability.id"],
            ondelete="RESTRICT",
            name="fk_appointment_tenant_availability",
        ),
        CheckConstraint("status IN ('booked', 'cancelled')", name="ck_appointment_status"),
        Index(
            "uq_appointment_active_slot",
            "tenant_id",
            "availability_id",
            unique=True,
            sqlite_where=text("status = 'booked'"),
            postgresql_where=text("status = 'booked'"),
        ),
        Index(
            "uq_appointment_patient_idempotency",
            "tenant_id",
            "patient_user_id",
            "idempotency_key",
            unique=True,
        ),
        Index("ix_appointment_tenant_patient", "tenant_id", "patient_user_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    clinic_patient_id: Mapped[str] = mapped_column(String(36), nullable=False)
    patient_user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    availability_id: Mapped[str] = mapped_column(String(36), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="booked", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )


class NotificationOutbox(Base):
    __tablename__ = "notification_outbox"
    __table_args__ = (
        CheckConstraint(
            "event_type IN ('appointment.booked', 'appointment.cancelled', "
            "'appointment.rescheduled')",
            name="ck_notification_event_type",
        ),
        CheckConstraint(
            "status IN ('pending', 'delivered', 'failed')",
            name="ck_notification_status",
        ),
        Index("ix_notification_outbox_pending", "status", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    appointment_id: Mapped[str] = mapped_column(
        ForeignKey("appointments.id", ondelete="CASCADE"), nullable=False
    )
    recipient_user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    event_type: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="pending", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )


class SupportAccessRequest(Base):
    __tablename__ = "support_access_requests"
    __table_args__ = (
        CheckConstraint(
            "purpose IN ('account_configuration', 'billing_support', "
            "'security_investigation', 'service_availability')",
            name="ck_support_access_purpose",
        ),
        CheckConstraint(
            "status = 'pending'",
            name="ck_support_access_status",
        ),
        Index("ix_support_access_status_created", "status", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    requested_by_user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    ticket_reference: Mapped[str] = mapped_column(String(128), nullable=False)
    purpose: Mapped[str] = mapped_column(String(32), nullable=False)
    requested_until: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    status: Mapped[str] = mapped_column(String(16), default="pending", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )


@event.listens_for(AuditEvent, "before_update")
@event.listens_for(AuditEvent, "before_delete")
def _audit_is_append_only(*_args: object) -> None:
    raise ValueError("Audit events are append-only.")


@event.listens_for(ConsentGrant, "before_update")
@event.listens_for(ConsentGrant, "before_delete")
def _consent_grant_is_immutable(*_args: object) -> None:
    raise ValueError("Consent grants are immutable; withdrawal creates a separate event.")


@event.listens_for(ConsentWithdrawal, "before_update")
@event.listens_for(ConsentWithdrawal, "before_delete")
def _consent_withdrawal_is_immutable(*_args: object) -> None:
    raise ValueError("Consent withdrawals are append-only.")
