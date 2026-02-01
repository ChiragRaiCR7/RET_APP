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
    # Add is_active column if it doesn't exist
    op.add_column(
        'users',
        sa.Column('is_active', sa.Boolean, nullable=False, server_default='true')
    )


def downgrade() -> None:
    # Remove is_active column if we roll back
    op.drop_column('users', 'is_active')
