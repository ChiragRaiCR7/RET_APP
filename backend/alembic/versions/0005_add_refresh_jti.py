"""Add refresh_jti column to login_sessions

Revision ID: 0005
Revises: 0004
Create Date: 2026-03-12 00:00:00.000000

refresh_jti was added to the LoginSession model in Phase 6 (token rotation)
but was inadvertently omitted from migration 0004.  This migration adds the
column plus its index so existing PostgreSQL databases can be upgraded.
"""
from alembic import op
import sqlalchemy as sa

revision = '0005'
down_revision = '0004'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Use a raw connection to skip gracefully if the column was already added
    # by SQLAlchemy create_all() on a fresh database.
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    cols = [c["name"] for c in inspector.get_columns("login_sessions")]
    if "refresh_jti" not in cols:
        op.add_column(
            'login_sessions',
            sa.Column('refresh_jti', sa.String(64), nullable=True),
        )
    # Create index only if it does not already exist
    indexes = [i["name"] for i in inspector.get_indexes("login_sessions")]
    if "ix_login_session_refresh_jti" not in indexes:
        op.create_index('ix_login_session_refresh_jti', 'login_sessions', ['refresh_jti'])


def downgrade() -> None:
    op.drop_index('ix_login_session_refresh_jti', table_name='login_sessions')
    op.drop_column('login_sessions', 'refresh_jti')
