"""classification producteur membre / non-membre

Ajoute `producers.type_producteur` : "membre" (on organise la recolte avec lui)
ou "non_membre" (on achete simplement sa production, bord champ). Les
producteurs existants sont consideres membres par defaut.

Voir app/db/models.py Producer.type_producteur.

Revision ID: 0007_producer_type
Revises: 0006_sync_operation_logs
Create Date: 2026-07-01
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0007_producer_type"
down_revision: Union[str, None] = "0006_sync_operation_logs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "producers",
        sa.Column(
            "type_producteur",
            sa.String(),
            nullable=False,
            server_default="membre",
        ),
    )
    op.create_index(
        "ix_producers_type_producteur", "producers", ["type_producteur"]
    )


def downgrade() -> None:
    op.drop_index("ix_producers_type_producteur", table_name="producers")
    op.drop_column("producers", "type_producteur")
