"""farmforce annual assessments

Revision ID: 0003_farmforce_assessments
Revises: 0002_cacaoguard_privacy_access_logs
Create Date: 2026-05-26
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0003_farmforce_assessments"
down_revision: Union[str, None] = "0002_cacaoguard_privacy_access_logs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "farmforce_assessments",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("producer_id", sa.Integer(), nullable=False),
        sa.Column("campagne_id", sa.Integer(), nullable=True),
        sa.Column("campaign_label", sa.String(), nullable=False),
        sa.Column("localite", sa.String(), nullable=True),
        sa.Column("pr_code", sa.String(), nullable=True),
        sa.Column("household_members", sa.JSON(), nullable=True),
        sa.Column("parcels", sa.JSON(), nullable=True),
        sa.Column("revenue_items", sa.JSON(), nullable=True),
        sa.Column("cost_items", sa.JSON(), nullable=True),
        sa.Column("family_labor_items", sa.JSON(), nullable=True),
        sa.Column("hired_labor_items", sa.JSON(), nullable=True),
        sa.Column("food_security_items", sa.JSON(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("total_revenue_cfa", sa.Float(), nullable=False, server_default="0"),
        sa.Column("total_cost_cfa", sa.Float(), nullable=False, server_default="0"),
        sa.Column("profit_cfa", sa.Float(), nullable=False, server_default="0"),
        sa.Column("family_labor_days", sa.Float(), nullable=False, server_default="0"),
        sa.Column("hired_labor_days", sa.Float(), nullable=False, server_default="0"),
        sa.Column("return_per_family_day_cfa", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
    )
    op.create_index("ix_farmforce_assessments_producer_id", "farmforce_assessments", ["producer_id"])
    op.create_index("ix_farmforce_assessments_campagne_id", "farmforce_assessments", ["campagne_id"])
    op.create_index("ix_farmforce_assessments_campaign_label", "farmforce_assessments", ["campaign_label"])


def downgrade() -> None:
    op.drop_index("ix_farmforce_assessments_campaign_label", table_name="farmforce_assessments")
    op.drop_index("ix_farmforce_assessments_campagne_id", table_name="farmforce_assessments")
    op.drop_index("ix_farmforce_assessments_producer_id", table_name="farmforce_assessments")
    op.drop_table("farmforce_assessments")
