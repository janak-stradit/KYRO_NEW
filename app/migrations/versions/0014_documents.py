"""documents — uploaded KYC documents, page text and extracted fields (Phase 11.1)

Revision ID: 0014
Revises: 0013
Create Date: 2026-10-08

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0014"
down_revision: Union[str, None] = "0013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = "app"
UUID = postgresql.UUID(as_uuid=True)
AUDIT_TYPES = (
    "'CUSTOMER','ACCOUNT','TRANSACTION','ALERT','RULE_CONFIG','OBLIGATION','OBLIGATION_MAPPING',"
    "'REGULATORY_CHANGE','RULE_CONFIG_CHANGE'"
)


def _set_audit_types(types: str) -> None:
    op.drop_constraint("chk_audit_entity_type", "audit_logs", schema=SCHEMA, type_="check")
    op.create_check_constraint("chk_audit_entity_type", "audit_logs", f"entity_type IN ({types})", schema=SCHEMA)


def upgrade() -> None:
    op.create_table(
        "documents",
        sa.Column("id", UUID, server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("customer_id", UUID, sa.ForeignKey(f"{SCHEMA}.customers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("alert_id", UUID, sa.ForeignKey(f"{SCHEMA}.alerts.id", ondelete="SET NULL")),
        sa.Column("doc_type", sa.String(30), nullable=False),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("content_type", sa.String(100), nullable=False),
        sa.Column("size_bytes", sa.Integer, nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("storage_key", sa.String(100), nullable=False),
        sa.Column("page_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("text_status", sa.String(20), nullable=False),
        sa.Column("extracted_at", sa.DateTime(timezone=True)),
        sa.Column("extracted_by", sa.String(30)),
        sa.Column("uploaded_by", UUID),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("retention_until", sa.Date),
        sa.CheckConstraint(
            "doc_type IN ('ID_DOCUMENT', 'PROOF_OF_ADDRESS', 'COMPANY_REGISTRY', 'FINANCIAL_STATEMENT', "
            "'SOURCE_OF_FUNDS', 'OTHER')",
            name="chk_document_type",
        ),
        sa.CheckConstraint(
            "text_status IN ('EXTRACTED', 'NEEDS_OCR', 'UNSUPPORTED', 'FAILED')", name="chk_document_text_status"
        ),
        schema=SCHEMA,
    )
    op.create_index("ix_app_documents_customer_id", "documents", ["customer_id"], schema=SCHEMA)
    op.create_index("ix_app_documents_alert_id", "documents", ["alert_id"], schema=SCHEMA)
    op.create_index("ix_app_documents_sha256", "documents", ["sha256"], schema=SCHEMA)

    op.create_table(
        "document_pages",
        sa.Column("id", UUID, server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("document_id", UUID, sa.ForeignKey(f"{SCHEMA}.documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("page_number", sa.Integer, nullable=False),
        sa.Column("text", sa.Text, nullable=False),
        sa.UniqueConstraint("document_id", "page_number", name="uq_document_page_number"),
        schema=SCHEMA,
    )
    op.create_index("ix_app_document_pages_document_id", "document_pages", ["document_id"], schema=SCHEMA)

    op.create_table(
        "document_extractions",
        sa.Column("id", UUID, server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("document_id", UUID, sa.ForeignKey(f"{SCHEMA}.documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("field", sa.String(50), nullable=False),
        sa.Column("value", sa.Text, nullable=False),
        sa.Column("page_number", sa.Integer),
        sa.Column("source_quote", sa.Text),
        sa.Column("quote_verified", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("confidence", sa.Numeric(4, 2)),
        sa.Column("check_status", sa.String(20), nullable=False, server_default="NOT_CHECKED"),
        sa.Column("check_detail", sa.Text),
        sa.Column("record_value", sa.Text),
        sa.Column("status", sa.String(20), nullable=False, server_default="PROPOSED"),
        sa.Column("applied_to_record", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("extracted_by", sa.String(30), nullable=False),
        sa.Column("ai_interaction_id", UUID),
        sa.Column("reviewed_by", UUID),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "check_status IN ('MATCH', 'MISMATCH', 'NOT_ON_RECORD', 'EXPIRED', 'NOT_CHECKED')",
            name="chk_document_extraction_check",
        ),
        sa.CheckConstraint(
            "status IN ('PROPOSED', 'ACCEPTED', 'EDITED', 'REJECTED')", name="chk_document_extraction_status"
        ),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_app_document_extractions_document_id", "document_extractions", ["document_id"], schema=SCHEMA
    )
    _set_audit_types(f"{AUDIT_TYPES},'DOCUMENT'")


def downgrade() -> None:
    op.execute(f"DELETE FROM {SCHEMA}.audit_logs WHERE entity_type = 'DOCUMENT'")
    _set_audit_types(AUDIT_TYPES)
    op.drop_index("ix_app_document_extractions_document_id", table_name="document_extractions", schema=SCHEMA)
    op.drop_table("document_extractions", schema=SCHEMA)
    op.drop_index("ix_app_document_pages_document_id", table_name="document_pages", schema=SCHEMA)
    op.drop_table("document_pages", schema=SCHEMA)
    op.drop_index("ix_app_documents_sha256", table_name="documents", schema=SCHEMA)
    op.drop_index("ix_app_documents_alert_id", table_name="documents", schema=SCHEMA)
    op.drop_index("ix_app_documents_customer_id", table_name="documents", schema=SCHEMA)
    op.drop_table("documents", schema=SCHEMA)
