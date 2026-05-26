"""cacaoguard privacy access logs

Revision ID: 0002_cacaoguard_privacy_access_logs
Revises: 0001_baseline
Create Date: 2026-05-26
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0002_cacaoguard_privacy_access_logs"
down_revision: Union[str, None] = "0001_baseline"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "privacy_access_logs",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("user_role", sa.String(length=50), nullable=True),
        sa.Column("action", sa.String(length=80), nullable=False),
        sa.Column("source_entity", sa.String(length=80), nullable=False),
        sa.Column("source_id", sa.Integer(), nullable=True),
        sa.Column("redacted", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=True,
        ),
    )
    op.create_index("ix_privacy_access_logs_user_id", "privacy_access_logs", ["user_id"])
    op.create_index("ix_privacy_access_logs_user_role", "privacy_access_logs", ["user_role"])
    op.create_index("ix_privacy_access_logs_action", "privacy_access_logs", ["action"])
    op.create_index(
        "ix_privacy_access_logs_source_entity",
        "privacy_access_logs",
        ["source_entity"],
    )
    op.create_index(
        "ix_privacy_access_logs_source_id",
        "privacy_access_logs",
        ["source_id"],
    )
    op.create_index(
        "ix_privacy_access_logs_created_at",
        "privacy_access_logs",
        ["created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_privacy_access_logs_created_at", table_name="privacy_access_logs")
    op.drop_index("ix_privacy_access_logs_source_id", table_name="privacy_access_logs")
    op.drop_index("ix_privacy_access_logs_source_entity", table_name="privacy_access_logs")
    op.drop_index("ix_privacy_access_logs_action", table_name="privacy_access_logs")
    op.drop_index("ix_privacy_access_logs_user_role", table_name="privacy_access_logs")
    op.drop_index("ix_privacy_access_logs_user_id", table_name="privacy_access_logs")
    op.drop_table("privacy_access_logs")
