"""sync operation logs

Cree la table `sync_operation_logs` pour l'idempotence des operations
synchronisees depuis un client offline. Voir app/db/models_social.py
SyncOperationLog et app/api/sync_routes.py.

Revision ID: 0005_sync_operation_logs
Revises: 0004_ssrte_forms
Create Date: 2026-05-27

Note : revision 0005 partagee avec 0005_notifications (branche soeur).
Lors du merge des deux PR, generer une migration de merge :
    alembic merge -m "merge notifications + sync" 0005_notifications 0005_sync_operation_logs
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0005_sync_operation_logs"
down_revision: Union[str, None] = "0004_ssrte_forms"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "sync_operation_logs",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("op_id", sa.String(length=64), nullable=False),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("op_type", sa.String(length=50), nullable=False),
        sa.Column("entity_type", sa.String(length=50), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("server_entity_id", sa.Integer(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("client_timestamp", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "applied_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=True,
        ),
        sa.UniqueConstraint("op_id", name="uq_sync_operation_logs_op_id"),
    )
    op.create_index("ix_sync_operation_logs_op_id", "sync_operation_logs", ["op_id"])
    op.create_index("ix_sync_operation_logs_user_id", "sync_operation_logs", ["user_id"])
    op.create_index("ix_sync_operation_logs_op_type", "sync_operation_logs", ["op_type"])
    op.create_index("ix_sync_operation_logs_entity_type", "sync_operation_logs", ["entity_type"])
    op.create_index("ix_sync_operation_logs_status", "sync_operation_logs", ["status"])
    op.create_index(
        "ix_sync_operation_logs_server_entity_id",
        "sync_operation_logs",
        ["server_entity_id"],
    )
    op.create_index("ix_sync_operation_logs_applied_at", "sync_operation_logs", ["applied_at"])


def downgrade() -> None:
    op.drop_index("ix_sync_operation_logs_applied_at", table_name="sync_operation_logs")
    op.drop_index("ix_sync_operation_logs_server_entity_id", table_name="sync_operation_logs")
    op.drop_index("ix_sync_operation_logs_status", table_name="sync_operation_logs")
    op.drop_index("ix_sync_operation_logs_entity_type", table_name="sync_operation_logs")
    op.drop_index("ix_sync_operation_logs_op_type", table_name="sync_operation_logs")
    op.drop_index("ix_sync_operation_logs_user_id", table_name="sync_operation_logs")
    op.drop_index("ix_sync_operation_logs_op_id", table_name="sync_operation_logs")
    op.drop_table("sync_operation_logs")
