"""Link documents to clinic patients and add messaging tables.

Revision ID: 0004_documents_messaging_patient_link
Revises: 0003_platform_admin_foundation
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_documents_messaging_patient_link"
down_revision: str | None = "0003_platform_admin_foundation"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("medical_documents") as batch:
        batch.add_column(sa.Column("clinic_patient_id", sa.String(36), nullable=True))
        batch.create_foreign_key(
            "fk_medical_document_clinic_patient",
            "clinic_patients",
            ["clinic_patient_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch.create_index(
            "ix_medical_document_clinic_patient",
            ["tenant_id", "clinic_patient_id", "created_at"],
        )

    op.create_table(
        "message_threads",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "tenant_id",
            sa.String(36),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "clinic_patient_id",
            sa.String(36),
            sa.ForeignKey("clinic_patients.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("subject", sa.String(200), nullable=False),
        sa.Column(
            "created_by_user_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('open', 'closed')",
            name="ck_message_thread_status",
        ),
        sa.UniqueConstraint("tenant_id", "id", name="uq_message_thread_tenant_id"),
    )
    op.create_index(
        "ix_message_thread_tenant_patient",
        "message_threads",
        ["tenant_id", "clinic_patient_id", "updated_at"],
    )

    op.create_table(
        "messages",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "tenant_id",
            sa.String(36),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "thread_id",
            sa.String(36),
            sa.ForeignKey("message_threads.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "sender_user_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("body", sa.String(4000), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id", "thread_id"],
            ["message_threads.tenant_id", "message_threads.id"],
            name="fk_message_thread_tenant",
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_message_thread_created",
        "messages",
        ["thread_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_message_thread_created", table_name="messages")
    op.drop_table("messages")
    op.drop_index("ix_message_thread_tenant_patient", table_name="message_threads")
    op.drop_table("message_threads")
    with op.batch_alter_table("medical_documents") as batch:
        batch.drop_index("ix_medical_document_clinic_patient")
        batch.drop_constraint("fk_medical_document_clinic_patient", type_="foreignkey")
        batch.drop_column("clinic_patient_id")
