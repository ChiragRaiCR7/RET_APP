"""Reconcile the schema with the ORM models (SQLite is now the only database)

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-29

Migrations 0001-0005 lagged the models: five tables and several columns, indexes,
NOT NULL constraints and foreign keys only ever existed through create_all() in
development. This revision brings any database at 0005 to the model schema.

It is idempotent so it works on both paths that exist in the wild:
  - a database built purely by `alembic upgrade head`, and
  - a development database that create_all() already filled in.

Definitions are frozen here on purpose; never import the live models into a migration.
Downgrade is a no-op: this revision only adds structure, and dropping it would destroy
data. Restore a backup to go back.
"""
import sqlalchemy as sa

from alembic import op

revision = '0006'
down_revision = '0005'
branch_labels = None
depends_on = None

REQUEST_STATUS = sa.Enum('PENDING', 'APPROVED', 'REJECTED', name='requeststatus')
JOB_TYPE = sa.Enum('CONVERSION', 'COMPARISON', 'INDEXING', 'XLSX_EXPORT', 'AUTO_INDEX', name='jobtype')
JOB_STATUS = sa.Enum('PENDING', 'RUNNING', 'SUCCESS', 'FAILED', 'CANCELLED', name='jobstatus')


def _inspector():
    return sa.inspect(op.get_bind())


def _columns(table: str) -> dict[str, dict]:
    return {c["name"]: c for c in _inspector().get_columns(table)}


def _indexes(table: str) -> set[str]:
    return {i["name"] for i in _inspector().get_indexes(table)}


def _has_fk(table: str, column: str) -> bool:
    return any(column in fk["constrained_columns"] for fk in _inspector().get_foreign_keys(table))


def _create_missing_tables() -> None:
    existing = set(_inspector().get_table_names())
    if 'error_events' not in existing:
        op.create_table(
            'error_events',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('username', sa.String(120)),
            sa.Column('session_id', sa.String(128)),
            sa.Column('phase', sa.String(64)),
            sa.Column('path', sa.Text()),
            sa.Column('error_type', sa.String(128)),
            sa.Column('message', sa.Text()),
            sa.Column('corr_id', sa.String(64)),
            sa.Column('created_at', sa.DateTime(), nullable=False),
        )
    if 'ops_logs' not in existing:
        op.create_table(
            'ops_logs',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('level', sa.String(16)),
            sa.Column('area', sa.String(64)),
            sa.Column('action', sa.String(255)),
            sa.Column('username', sa.String(120)),
            sa.Column('session_id', sa.String(128)),
            sa.Column('corr_id', sa.String(64)),
            sa.Column('message', sa.Text()),
            sa.Column('details', sa.JSON()),
            sa.Column('created_at', sa.DateTime(), nullable=False),
        )
    if 'password_reset_requests' not in existing:
        op.create_table(
            'password_reset_requests',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('username', sa.String(120), nullable=False),
            sa.Column('reason', sa.Text()),
            sa.Column('status', REQUEST_STATUS, nullable=False),
            sa.Column('action_by', sa.String(120)),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.Column('decided_at', sa.DateTime()),
        )
    if 'limit_increase_requests' not in existing:
        op.create_table(
            'limit_increase_requests',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
            sa.Column('requested_max_upload_mb', sa.Integer()),
            sa.Column('requested_max_files', sa.Integer()),
            sa.Column('requested_max_nested_depth', sa.Integer()),
            sa.Column('reason', sa.Text()),
            sa.Column('status', REQUEST_STATUS, nullable=False),
            sa.Column('action_by', sa.String(120)),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.Column('decided_at', sa.DateTime()),
        )
    if 'user_limits' not in existing:
        op.create_table(
            'user_limits',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
            sa.Column('max_sessions', sa.Integer(), nullable=False),
            sa.Column('max_upload_mb', sa.Integer(), nullable=False),
            sa.Column('max_files', sa.Integer(), nullable=False),
            sa.Column('max_nested_depth', sa.Integer(), nullable=False),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.Column('updated_at', sa.DateTime(), nullable=False),
            sa.UniqueConstraint('user_id', name='uq_user_limits_user'),
        )


def _add_missing_columns() -> None:
    users = _columns('users')
    with op.batch_alter_table('users') as batch:
        if 'is_deleted' not in users:
            batch.add_column(sa.Column('is_deleted', sa.Boolean(), nullable=False,
                                       server_default=sa.false()))
        if 'failed_login_attempts' not in users:
            batch.add_column(sa.Column('failed_login_attempts', sa.Integer(), nullable=False,
                                       server_default='0'))
        if 'locked_until' not in users:
            batch.add_column(sa.Column('locked_until', sa.DateTime()))
    jobs = _columns('jobs')
    with op.batch_alter_table('jobs') as batch:
        if 'user_id' not in jobs:
            batch.add_column(sa.Column('user_id', sa.Integer()))
        if 'session_id' not in jobs:
            batch.add_column(sa.Column('session_id', sa.String(128)))
        if 'started_at' not in jobs:
            batch.add_column(sa.Column('started_at', sa.DateTime()))
        if 'completed_at' not in jobs:
            batch.add_column(sa.Column('completed_at', sa.DateTime()))


# Values that make every row satisfy the model's NOT NULL constraints before tightening.
BACKFILL = {
    'users': {'role': "'user'", 'is_active': '1', 'is_locked': '0',
              'created_at': 'CURRENT_TIMESTAMP', 'updated_at': 'CURRENT_TIMESTAMP'},
    'audit_logs': {'created_at': 'CURRENT_TIMESTAMP'},
    'jobs': {'created_at': 'CURRENT_TIMESTAMP', 'updated_at': 'CURRENT_TIMESTAMP'},
    # A session with no expiry is treated as already expired.
    'login_sessions': {'created_at': 'CURRENT_TIMESTAMP', 'last_used_at': 'CURRENT_TIMESTAMP',
                       'expires_at': 'CURRENT_TIMESTAMP'},
    'password_reset_tokens': {'used': '1', 'created_at': 'CURRENT_TIMESTAMP',
                              'expires_at': 'CURRENT_TIMESTAMP'},
}


def _tighten(table: str, extra=None) -> None:
    """Backfills NULLs, then rebuilds the table with NOT NULL, indexes, FKs and types."""
    cols = _columns(table)
    for col, value in BACKFILL.get(table, {}).items():
        op.execute(sa.text(f"UPDATE {table} SET {col} = {value} WHERE {col} IS NULL"))
    with op.batch_alter_table(table) as batch:
        for col in BACKFILL.get(table, {}):
            if cols[col]["nullable"]:
                batch.alter_column(col, existing_type=cols[col]["type"], nullable=False)
        if extra:
            extra(batch)


def upgrade() -> None:
    _create_missing_tables()
    _add_missing_columns()

    def audit(batch):
        idx = _indexes('audit_logs')
        for name, col in (('ix_audit_area', 'area'), ('ix_audit_corr_id', 'corr_id'),
                          ('ix_audit_username', 'username')):
            if name not in idx:
                batch.create_index(name, [col])

    def jobs(batch):
        idx = _indexes('jobs')
        batch.alter_column('job_type', existing_type=sa.String(64), type_=JOB_TYPE,
                           existing_nullable=False)
        batch.alter_column('status', existing_type=sa.String(32), type_=JOB_STATUS,
                           existing_nullable=False, existing_server_default=sa.text("'PENDING'"))
        batch.alter_column('error', existing_type=sa.String(1024), type_=sa.String(2048))
        for name, col in (('ix_jobs_created', 'created_at'), ('ix_jobs_session', 'session_id'),
                          ('ix_jobs_status', 'status'), ('ix_jobs_user_id', 'user_id')):
            if name not in idx:
                batch.create_index(name, [col])
        if not _has_fk('jobs', 'user_id'):
            batch.create_foreign_key('fk_jobs_user_id', 'users', ['user_id'], ['id'])

    def sessions(batch):
        idx = _indexes('login_sessions')
        for name, col in (('ix_login_session_expires', 'expires_at'),
                          ('ix_login_session_user', 'user_id'),
                          ('ix_login_sessions_refresh_jti', 'refresh_jti'),
                          ('ix_login_sessions_token_family', 'token_family')):
            if name not in idx:
                batch.create_index(name, [col])
        if not _has_fk('login_sessions', 'user_id'):
            batch.create_foreign_key('fk_login_sessions_user_id', 'users', ['user_id'], ['id'])

    def reset_tokens(batch):
        idx = _indexes('password_reset_tokens')
        if 'ix_password_reset_tokens_token_hash' not in idx:
            batch.create_index('ix_password_reset_tokens_token_hash', ['token_hash'])
        if 'ix_reset_token_expires' not in idx:
            batch.create_index('ix_reset_token_expires', ['expires_at'])
        if not _has_fk('password_reset_tokens', 'user_id'):
            batch.create_foreign_key('fk_password_reset_tokens_user_id', 'users', ['user_id'], ['id'])

    _tighten('users')
    _tighten('audit_logs', audit)
    _tighten('jobs', jobs)
    _tighten('login_sessions', sessions)
    _tighten('password_reset_tokens', reset_tokens)

    for table, indexes in {
        'error_events': (('ix_error_corr_id', 'corr_id'), ('ix_error_session_id', 'session_id'),
                         ('ix_error_type', 'error_type')),
        'ops_logs': (('ix_ops_corr_id', 'corr_id'), ('ix_ops_session_id', 'session_id'),
                     ('ix_ops_username', 'username')),
        'password_reset_requests': (('ix_password_reset_requests_username', 'username'),),
        'limit_increase_requests': (('ix_limit_increase_requests_user_id', 'user_id'),),
    }.items():
        existing = _indexes(table)
        for name, col in indexes:
            if name not in existing:
                op.create_index(name, table, [col])


def downgrade() -> None:
    # Additive reconciliation; reversing it would drop tables and columns holding data.
    pass
