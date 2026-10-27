"""Add restricted platform support request records.

Revision ID: 0003_platform_admin_foundation
Revises: 0002_clinic_onboarding_scheduling
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_platform_admin_foundation"
down_revision: str | None = "0002_clinic_onboarding_scheduling"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "support_access_requests",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "tenant_id",
            sa.String(36),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "requested_by_user_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("ticket_reference", sa.String(128), nullable=False),
        sa.Column("purpose", sa.String(32), nullable=False),
        sa.Column("requested_until", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "purpose IN ('account_configuration', 'billing_support', "
            "'security_investigation', 'service_availability')",
            name="ck_support_access_purpose",
        ),
        sa.CheckConstraint(
            "status = 'pending'",
            name="ck_support_access_status",
        ),
    )
    op.create_index(
        "ix_support_access_status_created",
        "support_access_requests",
        ["status", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_support_access_status_created",
        table_name="support_access_requests",
    )
    op.drop_table("support_access_requests")
