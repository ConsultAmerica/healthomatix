"""V1.7 interoperability hub, identity links, terminology, import/export."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.db import Base
from app.models import new_id, utcnow


class IntegrationConnection(Base):
    __tablename__ = "integration_connections"
    __table_args__ = (Index("ix_int_conn_tenant", "tenant_id", "status"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    connection_name: Mapped[str] = mapped_column(String(120), nullable=False)
    # fhir_ehr | hl7_lab | file_import
    integration_type: Mapped[str] = mapped_column(String(32), nullable=False)
    external_system: Mapped[str] = mapped_column(String(120), nullable=False)
    base_url: Mapped[str] = mapped_column(String(512), default="", nullable=False)
    fhir_version: Mapped[str] = mapped_column(String(16), default="4.0.1", nullable=False)
    authentication_type: Mapped[str] = mapped_column(String(32), default="sandbox", nullable=False)
    # Secrets stay out of this row; reference only.
    secret_reference: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    authorized_scopes: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    status: Mapped[str] = mapped_column(String(24), default="configured", nullable=False)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str] = mapped_column(Text, default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )


class IntegrationTransaction(Base):
    __tablename__ = "integration_transactions"
    __table_args__ = (
        Index("ix_int_txn_tenant_status", "tenant_id", "status", "received_at"),
        UniqueConstraint(
            "tenant_id", "connection_id", "external_message_id", name="uq_int_txn_external"
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    connection_id: Mapped[str] = mapped_column(
        ForeignKey("integration_connections.id", ondelete="CASCADE"), nullable=False
    )
    direction: Mapped[str] = mapped_column(String(16), nullable=False)
    message_type: Mapped[str] = mapped_column(String(64), nullable=False)
    external_message_id: Mapped[str] = mapped_column(String(128), nullable=False)
    correlation_id: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    # received | validating | validated | mapping | awaiting_review | processed | rejected | failed | retrying
    status: Mapped[str] = mapped_column(String(24), default="received", nullable=False)
    payload_reference: Mapped[str] = mapped_column(String(256), default="", nullable=False)
    payload_summary: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    error_code: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    error_summary: Mapped[str] = mapped_column(Text, default="", nullable=False)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class IntegrationJob(Base):
    __tablename__ = "integration_jobs"
    __table_args__ = (Index("ix_int_job_status", "tenant_id", "status", "next_retry_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    transaction_id: Mapped[str] = mapped_column(
        ForeignKey("integration_transactions.id", ondelete="CASCADE"), nullable=False
    )
    job_type: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="queued", nullable=False)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ExternalResourceReference(Base):
    __tablename__ = "external_resource_references"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "connection_id",
            "resource_type",
            "external_resource_id",
            name="uq_ext_resource",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    connection_id: Mapped[str] = mapped_column(
        ForeignKey("integration_connections.id", ondelete="CASCADE"), nullable=False
    )
    resource_type: Mapped[str] = mapped_column(String(64), nullable=False)
    external_resource_id: Mapped[str] = mapped_column(String(128), nullable=False)
    local_entity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    local_entity_id: Mapped[str] = mapped_column(String(36), nullable=False)
    version_reference: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    last_synced_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )


class PatientIdentityLink(Base):
    __tablename__ = "patient_identity_links"
    __table_args__ = (
        Index("ix_pil_tenant_patient", "tenant_id", "patient_id"),
        UniqueConstraint(
            "tenant_id",
            "external_system",
            "external_identifier",
            "assigning_authority",
            name="uq_pil_external",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    patient_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    external_system: Mapped[str] = mapped_column(String(120), nullable=False)
    external_identifier: Mapped[str] = mapped_column(String(128), nullable=False)
    assigning_authority: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    # confirmed | possible | no_match | conflict | manual_review
    verification_status: Mapped[str] = mapped_column(String(32), default="manual_review", nullable=False)
    match_evidence: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    verified_by_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )


class TerminologyMapping(Base):
    __tablename__ = "terminology_mappings"
    __table_args__ = (
        UniqueConstraint(
            "source_system",
            "source_code",
            "target_system",
            "mapping_version",
            name="uq_term_map",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    source_system: Mapped[str] = mapped_column(String(120), nullable=False)
    source_code: Mapped[str] = mapped_column(String(64), nullable=False)
    source_display: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    target_system: Mapped[str] = mapped_column(String(120), nullable=False)
    target_code: Mapped[str] = mapped_column(String(64), nullable=False)
    mapping_version: Mapped[str] = mapped_column(String(32), default="1", nullable=False)
    # proposed | pending_review | approved | rejected | deprecated
    status: Mapped[str] = mapped_column(String(24), default="proposed", nullable=False)
    reviewed_by_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )


class ClinicalImportBatch(Base):
    __tablename__ = "clinical_import_batches"
    __table_args__ = (Index("ix_import_batch_tenant", "tenant_id", "status"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    source_connection_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    import_type: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="preview", nullable=False)
    requested_by_user_id: Mapped[str] = mapped_column(String(36), nullable=False)
    approved_by_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    summary: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ClinicalImportItem(Base):
    __tablename__ = "clinical_import_items"
    __table_args__ = (Index("ix_import_item_batch", "tenant_id", "batch_id", "import_status"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    batch_id: Mapped[str] = mapped_column(
        ForeignKey("clinical_import_batches.id", ondelete="CASCADE"), nullable=False
    )
    resource_type: Mapped[str] = mapped_column(String(64), nullable=False)
    external_identifier: Mapped[str] = mapped_column(String(128), nullable=False)
    mapping_status: Mapped[str] = mapped_column(String(24), default="pending", nullable=False)
    validation_status: Mapped[str] = mapped_column(String(24), default="pending", nullable=False)
    import_status: Mapped[str] = mapped_column(String(24), default="pending", nullable=False)
    local_entity_reference: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    resource_preview: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    error_summary: Mapped[str] = mapped_column(Text, default="", nullable=False)


class PatientDataExport(Base):
    __tablename__ = "patient_data_exports"
    __table_args__ = (Index("ix_export_tenant_patient", "tenant_id", "patient_id", "created_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    patient_id: Mapped[str] = mapped_column(String(36), nullable=False)
    requested_by_user_id: Mapped[str] = mapped_column(String(36), nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="ready", nullable=False)
    format: Mapped[str] = mapped_column(String(32), default="fhir_r4_bundle", nullable=False)
    bundle_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )


class DataExchangeAuditEvent(Base):
    __tablename__ = "data_exchange_audit_events"
    __table_args__ = (Index("ix_dea_tenant_time", "tenant_id", "occurred_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    actor_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    patient_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    connection_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    resource_reference: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    outcome: Mapped[str] = mapped_column(String(24), default="success", nullable=False)
    purpose_reference: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
