"""security audit log table

Revision ID: 0002_security_audit_log
Revises: 0001_initial
Create Date: 2026-09-07 00:00:00.000000

7a-5 安全加固：新增 security_audit_logs 表，
记录 API 请求的审计轨迹（tenant_id + actor + action + resource）。
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0002_security_audit_log"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "security_audit_logs",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("tenant_id", sa.String(length=32), nullable=False),
        sa.Column("actor", sa.String(length=64), nullable=False),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("resource", sa.String(length=512), nullable=True),
        sa.Column("method", sa.String(length=10), nullable=True),
        sa.Column("status_code", sa.Integer(), nullable=True),
        sa.Column("ip", sa.String(length=64), nullable=True),
        sa.Column("detail", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_security_audit_logs_tenant_id", "security_audit_logs", ["tenant_id"])
    op.create_index("ix_security_audit_logs_actor", "security_audit_logs", ["actor"])
    op.create_index("ix_security_audit_logs_action", "security_audit_logs", ["action"])
    op.create_index("ix_security_audit_logs_created_at", "security_audit_logs", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_security_audit_logs_created_at", table_name="security_audit_logs")
    op.drop_index("ix_security_audit_logs_action", table_name="security_audit_logs")
    op.drop_index("ix_security_audit_logs_actor", table_name="security_audit_logs")
    op.drop_index("ix_security_audit_logs_tenant_id", table_name="security_audit_logs")
    op.drop_table("security_audit_logs")
