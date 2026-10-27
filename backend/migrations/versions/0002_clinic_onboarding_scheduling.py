"""Clinic onboarding, availability, transactional appointments, and outbox.

Revision ID: 0002_clinic_onboarding_scheduling
Revises: 0001_phase1_foundation
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_clinic_onboarding_scheduling"
down_revision: str | None = "0001_phase1_foundation"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("tenant_memberships") as batch:
        batch.drop_constraint("ck_membership_role", type_="check")
        batch.create_check_constraint(
            "ck_membership_role",
            "role IN ('tenant_admin', 'staff', 'patient', 'provider', 'auditor')",
        )

    with op.batch_alter_table("clinic_patients") as batch:
        batch.create_unique_constraint(
            "uq_clinic_patient_tenant_id", ["tenant_id", "id"]
        )
        batch.create_unique_constraint(
            "uq_clinic_patient_tenant_id_user",
            ["tenant_id", "id", "patient_user_id"],
        )

    op.create_table(
        "clinic_locations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "tenant_id",
            sa.String(36),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("timezone", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "id", name="uq_clinic_location_tenant_id"),
        sa.UniqueConstraint("tenant_id", "name", name="uq_clinic_location_name"),
        sa.CheckConstraint(
            "status IN ('active', 'inactive')", name="ck_clinic_location_status"
        ),
    )
    op.create_table(
        "clinic_invitations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "tenant_id",
            sa.String(36),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("role", sa.String(24), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column(
            "created_by_user_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "accepted_by_user_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "role IN ('staff', 'patient', 'provider')", name="ck_clinic_invitation_role"
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'accepted', 'revoked', 'expired')",
            name="ck_clinic_invitation_status",
        ),
    )
    op.create_index(
        "ix_clinic_invitation_tenant_status",
        "clinic_invitations",
        ["tenant_id", "status"],
    )
    op.create_table(
        "provider_availability",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "tenant_id",
            sa.String(36),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("provider_user_id", sa.String(36), nullable=False),
        sa.Column("location_id", sa.String(36), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "id", name="uq_availability_tenant_id"),
        sa.UniqueConstraint(
            "tenant_id",
            "provider_user_id",
            "starts_at",
            name="uq_availability_provider_start",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "provider_user_id"],
            ["tenant_memberships.tenant_id", "tenant_memberships.user_id"],
            ondelete="CASCADE",
            name="fk_availability_provider_membership",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "location_id"],
            ["clinic_locations.tenant_id", "clinic_locations.id"],
            ondelete="CASCADE",
            name="fk_availability_tenant_location",
        ),
        sa.CheckConstraint(
            "status IN ('open', 'booked')", name="ck_availability_status"
        ),
        sa.CheckConstraint("ends_at > starts_at", name="ck_availability_time_order"),
    )
    op.create_index(
        "ix_availability_tenant_start_status",
        "provider_availability",
        ["tenant_id", "starts_at", "status"],
    )
    op.create_table(
        "appointments",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "tenant_id",
            sa.String(36),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("clinic_patient_id", sa.String(36), nullable=False),
        sa.Column(
            "patient_user_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("availability_id", sa.String(36), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "id", name="uq_appointment_tenant_id"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "clinic_patient_id", "patient_user_id"],
            [
                "clinic_patients.tenant_id",
                "clinic_patients.id",
                "clinic_patients.patient_user_id",
            ],
            ondelete="CASCADE",
            name="fk_appointment_tenant_patient",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "availability_id"],
            ["provider_availability.tenant_id", "provider_availability.id"],
            ondelete="RESTRICT",
            name="fk_appointment_tenant_availability",
        ),
        sa.CheckConstraint(
            "status IN ('booked', 'cancelled')", name="ck_appointment_status"
        ),
    )
    op.create_index(
        "uq_appointment_active_slot",
        "appointments",
        ["tenant_id", "availability_id"],
        unique=True,
        sqlite_where=sa.text("status = 'booked'"),
        postgresql_where=sa.text("status = 'booked'"),
    )
    op.create_index(
        "uq_appointment_patient_idempotency",
        "appointments",
        ["tenant_id", "patient_user_id", "idempotency_key"],
        unique=True,
    )
    op.create_index(
        "ix_appointment_tenant_patient",
        "appointments",
        ["tenant_id", "patient_user_id", "created_at"],
    )
    op.create_table(
        "notification_outbox",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "tenant_id",
            sa.String(36),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "appointment_id",
            sa.String(36),
            sa.ForeignKey("appointments.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "recipient_user_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("event_type", sa.String(40), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "event_type IN ('appointment.booked', 'appointment.cancelled', "
            "'appointment.rescheduled')",
            name="ck_notification_event_type",
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'delivered', 'failed')",
            name="ck_notification_status",
        ),
    )
    op.create_index(
        "ix_notification_outbox_pending",
        "notification_outbox",
        ["status", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_notification_outbox_pending", table_name="notification_outbox")
    op.drop_table("notification_outbox")
    op.drop_index("ix_appointment_tenant_patient", table_name="appointments")
    op.drop_index("uq_appointment_patient_idempotency", table_name="appointments")
    op.drop_index("uq_appointment_active_slot", table_name="appointments")
    op.drop_table("appointments")
    op.drop_index(
        "ix_availability_tenant_start_status", table_name="provider_availability"
    )
    op.drop_table("provider_availability")
    op.drop_index(
        "ix_clinic_invitation_tenant_status", table_name="clinic_invitations"
    )
    op.drop_table("clinic_invitations")
    op.drop_table("clinic_locations")

    with op.batch_alter_table("clinic_patients") as batch:
        batch.drop_constraint("uq_clinic_patient_tenant_id_user", type_="unique")
        batch.drop_constraint("uq_clinic_patient_tenant_id", type_="unique")
    with op.batch_alter_table("tenant_memberships") as batch:
        batch.drop_constraint("ck_membership_role", type_="check")
        batch.create_check_constraint(
            "ck_membership_role",
            "role IN ('tenant_admin', 'patient', 'provider', 'auditor')",
        )
