"""Add is_active column to users table

Revision ID: 0003
Revises: 0002_add_jobs_table
Create Date: 2024-01-15 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0003'
down_revision = '0002_add_jobs_table'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 0001 already creates users.is_active (nullable), so a fresh database must not add it
    # again; older databases created without it still get the column. sa.true() renders as
    # 1 on SQLite and TRUE on PostgreSQL (the string 'true' is stored as text on SQLite and
    # never matches `is_active = 1`).
    bind = op.get_bind()
    cols = {c["name"] for c in sa.inspect(bind).get_columns("users")}
    if "is_active" not in cols:
        op.add_column(
            'users',
            sa.Column('is_active', sa.Boolean, nullable=False, server_default=sa.true())
        )
    else:
        op.execute(sa.text("UPDATE users SET is_active = :t WHERE is_active IS NULL").bindparams(
            sa.bindparam("t", True, type_=sa.Boolean)))


def downgrade() -> None:
    # Remove is_active column if we roll back
    op.drop_column('users', 'is_active')
