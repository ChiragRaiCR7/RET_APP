"""Add token-rotation columns to login_sessions

Revision ID: 0004
Revises: 0003
Create Date: 2025-01-01 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = '0004'
down_revision = '0003'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'login_sessions',
        sa.Column('token_family', sa.String(64), nullable=True),
    )
    op.add_column(
        'login_sessions',
        sa.Column('replaced_by_id', sa.Integer, nullable=True),
    )
    op.add_column(
        'login_sessions',
        sa.Column('revoked', sa.Boolean, nullable=False, server_default='0'),
    )
    op.create_index('ix_login_session_family', 'login_sessions', ['token_family'])


def downgrade() -> None:
    op.drop_index('ix_login_session_family', table_name='login_sessions')
    op.drop_column('login_sessions', 'revoked')
    op.drop_column('login_sessions', 'replaced_by_id')
    op.drop_column('login_sessions', 'token_family')
