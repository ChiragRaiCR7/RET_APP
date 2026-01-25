"""add jobs table

Revision ID: 0002_add_jobs_table
Revises: 0001_initial_schema
Create Date: 2026-01-24 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = "0002_add_jobs_table"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "jobs",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("job_type", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="PENDING"),
        sa.Column("progress", sa.Integer, nullable=False, server_default="0"),
        sa.Column("result", sa.JSON, nullable=True),
        sa.Column("error", sa.String(1024), nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=True),
        sa.Column("updated_at", sa.DateTime, nullable=True),
    )


def downgrade():
    op.drop_table("jobs")
