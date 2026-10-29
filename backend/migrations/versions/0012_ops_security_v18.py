"""Support tickets and launch readiness checks (V1.8).

Revision ID: 0012_ops_security_v18
Revises: 0011_interop_fhir_v17
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0012_ops_security_v18"
down_revision: str | None = "0011_interop_fhir_v17"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "support_tickets",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(36), sa.ForeignKey("tenants.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_by_user_id", sa.String(36), nullable=False),
        sa.Column("category", sa.String(64), nullable=False),
        sa.Column("priority", sa.String(16), nullable=False, server_default="normal"),
        sa.Column("status", sa.String(24), nullable=False, server_default="open"),
        sa.Column("subject", sa.String(200), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("assigned_to_user_id", sa.String(36), nullable=True),
        sa.Column("resolution_summary", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_support_ticket_tenant_status",
        "support_tickets",
        ["tenant_id", "status", "created_at"],
    )
    op.create_table(
        "launch_readiness_checks",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("gate", sa.String(64), nullable=False),
        sa.Column("check_code", sa.String(64), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="not_assessed"),
        sa.Column("evidence_reference", sa.String(256), nullable=False, server_default=""),
        sa.Column("notes", sa.Text(), nullable=False, server_default=""),
        sa.Column("assessed_by_user_id", sa.String(36), nullable=True),
        sa.Column("assessed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
    )
    op.create_index("ix_launch_gate", "launch_readiness_checks", ["gate", "status"])


def downgrade() -> None:
    op.drop_index("ix_launch_gate", table_name="launch_readiness_checks")
    op.drop_table("launch_readiness_checks")
    op.drop_index("ix_support_ticket_tenant_status", table_name="support_tickets")
    op.drop_table("support_tickets")
