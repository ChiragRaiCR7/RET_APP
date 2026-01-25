from alembic import op
import sqlalchemy as sa

revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    op.create_table(
        "users",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("username", sa.String(120), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("role", sa.String(32)),
        sa.Column("is_active", sa.Boolean, default=True),
        sa.Column("is_locked", sa.Boolean, default=False),
        sa.Column("created_at", sa.DateTime),
        sa.Column("updated_at", sa.DateTime),
    )
    op.create_index("ix_users_username", "users", ["username"], unique=True)

    op.create_table(
        "login_sessions",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer, nullable=False),
        sa.Column("refresh_token_hash", sa.String(255), nullable=False),
        sa.Column("ip_address", sa.String(64)),
        sa.Column("user_agent", sa.Text),
        sa.Column("created_at", sa.DateTime),
        sa.Column("last_used_at", sa.DateTime),
        sa.Column("expires_at", sa.DateTime),
    )

    op.create_table(
        "password_reset_tokens",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer, nullable=False),
        sa.Column("token_hash", sa.String(255), nullable=False),
        sa.Column("expires_at", sa.DateTime),
        sa.Column("used", sa.Boolean, default=False),
        sa.Column("created_at", sa.DateTime),
    )

    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("username", sa.String(120)),
        sa.Column("action", sa.String(255)),
        sa.Column("area", sa.String(64)),
        sa.Column("corr_id", sa.String(64)),
        sa.Column("message", sa.Text),
        sa.Column("details", sa.JSON),
        sa.Column("created_at", sa.DateTime),
    )


def downgrade():
    op.drop_table("audit_logs")
    op.drop_table("password_reset_tokens")
    op.drop_table("login_sessions")
    op.drop_table("users")
