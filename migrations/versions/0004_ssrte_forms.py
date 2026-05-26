"""ssrte forms

Revision ID: 0004_ssrte_forms
Revises: 0003_farmforce_assessments
Create Date: 2026-05-26
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0004_ssrte_forms"
down_revision: Union[str, None] = "0003_farmforce_assessments"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ssrte_community_profiles",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("locality", sa.String(length=200), nullable=False),
        sa.Column("section", sa.String(length=100), nullable=True),
        sa.Column("cooperative_id", sa.Integer(), nullable=True),
        sa.Column("interview_date", sa.Date(), nullable=False),
        sa.Column("respondent_name", sa.String(length=200), nullable=True),
        sa.Column("respondent_role", sa.String(length=100), nullable=True),
        sa.Column("school_available", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("nearest_school_distance_km", sa.Numeric(6, 2), nullable=True),
        sa.Column("has_child_protection_committee", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("committee_members", sa.JSON(), nullable=True),
        sa.Column("risks_identified", sa.JSON(), nullable=True),
        sa.Column("services_available", sa.JSON(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_ssrte_community_profiles_locality", "ssrte_community_profiles", ["locality"])
    op.create_index("ix_ssrte_community_profiles_section", "ssrte_community_profiles", ["section"])

    op.create_table(
        "ssrte_household_profiles",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("producer_id", sa.Integer(), nullable=False),
        sa.Column("interview_date", sa.Date(), nullable=False),
        sa.Column("interviewer_name", sa.String(length=200), nullable=True),
        sa.Column("household_size", sa.Integer(), nullable=True),
        sa.Column("children_count", sa.Integer(), nullable=True),
        sa.Column("school_age_children_count", sa.Integer(), nullable=True),
        sa.Column("enrolled_children_count", sa.Integer(), nullable=True),
        sa.Column("household_members", sa.JSON(), nullable=True),
        sa.Column("vulnerabilities", sa.JSON(), nullable=True),
        sa.Column("child_work_declarations", sa.JSON(), nullable=True),
        sa.Column("school_constraints", sa.JSON(), nullable=True),
        sa.Column("risk_score", sa.Numeric(5, 2), nullable=False, server_default="0"),
        sa.Column("risk_level", sa.String(length=8), nullable=False, server_default="none"),
        sa.Column("consent_given", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("signature_data", sa.JSON(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_ssrte_household_profiles_producer_id", "ssrte_household_profiles", ["producer_id"])
    op.create_index("ix_ssrte_household_profiles_risk_level", "ssrte_household_profiles", ["risk_level"])

    op.create_table(
        "ssrte_plantation_visits",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("plantation_id", sa.Integer(), nullable=False),
        sa.Column("producer_id", sa.Integer(), nullable=True),
        sa.Column("visit_date", sa.Date(), nullable=False),
        sa.Column("interviewer_name", sa.String(length=200), nullable=True),
        sa.Column("gps_location", sa.String(length=255), nullable=True),
        sa.Column("gps_accuracy", sa.Float(), nullable=True),
        sa.Column("checklist_data", sa.JSON(), nullable=True),
        sa.Column("children_observed", sa.JSON(), nullable=True),
        sa.Column("dangerous_tasks_observed", sa.JSON(), nullable=True),
        sa.Column("suspected_child_labor", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("immediate_actions_taken", sa.Text(), nullable=True),
        sa.Column("photos", sa.JSON(), nullable=True),
        sa.Column("consent_given", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("producer_signature_data", sa.JSON(), nullable=True),
        sa.Column("assessor_signature_data", sa.JSON(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_ssrte_plantation_visits_plantation_id", "ssrte_plantation_visits", ["plantation_id"])
    op.create_index("ix_ssrte_plantation_visits_producer_id", "ssrte_plantation_visits", ["producer_id"])
    op.create_index("ix_ssrte_plantation_visits_suspected_child_labor", "ssrte_plantation_visits", ["suspected_child_labor"])


def downgrade() -> None:
    op.drop_index("ix_ssrte_plantation_visits_suspected_child_labor", table_name="ssrte_plantation_visits")
    op.drop_index("ix_ssrte_plantation_visits_producer_id", table_name="ssrte_plantation_visits")
    op.drop_index("ix_ssrte_plantation_visits_plantation_id", table_name="ssrte_plantation_visits")
    op.drop_table("ssrte_plantation_visits")
    op.drop_index("ix_ssrte_household_profiles_risk_level", table_name="ssrte_household_profiles")
    op.drop_index("ix_ssrte_household_profiles_producer_id", table_name="ssrte_household_profiles")
    op.drop_table("ssrte_household_profiles")
    op.drop_index("ix_ssrte_community_profiles_section", table_name="ssrte_community_profiles")
    op.drop_index("ix_ssrte_community_profiles_locality", table_name="ssrte_community_profiles")
    op.drop_table("ssrte_community_profiles")
