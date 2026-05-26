"""baseline schema - toutes les tables v1

Revision ID: 0001_baseline
Revises:
Create Date: 2026-03-27
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "0001_baseline"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "cooperatives",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("name", sa.String(), nullable=False, index=True),
        sa.Column("country", sa.String(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("email", sa.String(), unique=True, nullable=False, index=True),
        sa.Column("password_hash", sa.String(), nullable=False),
        sa.Column("role", sa.String(), nullable=False),
        sa.Column(
            "cooperative_id",
            sa.Integer(),
            sa.ForeignKey("cooperatives.id"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    op.create_table(
        "plantations",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("name", sa.String(), nullable=False, index=True),
        sa.Column("owner_name", sa.String(), nullable=False),
        sa.Column("country", sa.String(), nullable=False),
        sa.Column("region", sa.String(), nullable=True),
        sa.Column("latitude", sa.Float(), nullable=True),
        sa.Column("longitude", sa.Float(), nullable=True),
        sa.Column("hectares", sa.Float(), nullable=True),
        sa.Column(
            "cooperative_id",
            sa.Integer(),
            sa.ForeignKey("cooperatives.id"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    op.create_table(
        "diagnostics",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column(
            "plantation_id",
            sa.Integer(),
            sa.ForeignKey("plantations.id"),
            nullable=False,
        ),
        sa.Column("country", sa.String(), nullable=True, index=True),
        sa.Column("region", sa.String(), nullable=True),
        sa.Column("humidity_pct", sa.Float(), nullable=False),
        sa.Column("rainfall_mm_month", sa.Float(), nullable=False),
        sa.Column("avg_temp_c", sa.Float(), nullable=False),
        sa.Column("plantation_age_years", sa.Float(), nullable=True),
        sa.Column("shade_tree_density_pct", sa.Float(), nullable=True),
        sa.Column("global_score", sa.Float(), nullable=False),
        sa.Column("global_risk_level", sa.String(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_table("diagnostics")
    op.drop_table("plantations")
    op.drop_table("users")
    op.drop_table("cooperatives")
