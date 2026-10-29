"""V1.8 support tickets and launch readiness tracking."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.db import Base
from app.models import new_id, utcnow


class SupportTicket(Base):
    __tablename__ = "support_tickets"
    __table_args__ = (Index("ix_support_ticket_tenant_status", "tenant_id", "status", "created_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    tenant_id: Mapped[str | None] = mapped_column(
        ForeignKey("tenants.id", ondelete="SET NULL"), nullable=True
    )
    created_by_user_id: Mapped[str] = mapped_column(String(36), nullable=False)
    ticket_number: Mapped[str] = mapped_column(String(32), default="", nullable=False)
    category: Mapped[str] = mapped_column(String(64), nullable=False)
    # patient | clinic_admin | provider | billing | technical | security
    priority: Mapped[str] = mapped_column(String(16), default="normal", nullable=False)
    # open | triaged | assigned | in_progress | waiting_customer | waiting_vendor | escalated | resolved | closed
    status: Mapped[str] = mapped_column(String(24), default="open", nullable=False)
    subject: Mapped[str] = mapped_column(String(200), nullable=False)
    # Do not store clinical narrative / PHI dumps in tickets.
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    assigned_team: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    assigned_to_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    resolution_summary: Mapped[str] = mapped_column(Text, default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class LaunchReadinessCheck(Base):
    __tablename__ = "launch_readiness_checks"
    __table_args__ = (Index("ix_launch_gate", "gate", "status"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    gate: Mapped[str] = mapped_column(String(64), nullable=False)
    check_code: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    # pass | fail | conditional | not_assessed
    status: Mapped[str] = mapped_column(String(24), default="not_assessed", nullable=False)
    evidence_reference: Mapped[str] = mapped_column(String(256), default="", nullable=False)
    notes: Mapped[str] = mapped_column(Text, default="", nullable=False)
    assessed_by_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    assessed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
