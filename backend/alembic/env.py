import sys
from pathlib import Path

# --- MUST BE FIRST ---
BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR))

from logging.config import fileConfig
from sqlalchemy import engine_from_config, pool
from alembic import context

from api.core.database import Base
import api.models  # noqa: E402, F401  registers every model on Base.metadata for autogenerate
from api.core.config import settings
# import api.models.user  # noqa: F401  (force model import)

config = context.config

# --- type-safe logging config ---
if config.config_file_name:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

# Alembic uses a *sync* driver.  Convert async DSNs so migrations work:
#   postgresql+asyncpg://  →  postgresql+psycopg2://
#   sqlite+aiosqlite://    →  sqlite:///
_raw_url = settings.DATABASE_URL or "sqlite:///./test.db"
# Migrations run synchronously through the stdlib sqlite3 driver.
_sync_url = _raw_url.replace("sqlite+aiosqlite:///", "sqlite:///")
config.set_main_option("sqlalchemy.url", _sync_url)


def run_migrations_offline():
    context.configure(
        url=settings.DATABASE_URL,
        target_metadata=target_metadata,
        literal_binds=True,
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    section = config.get_section(config.config_ini_section)
    if section is None:
        raise RuntimeError("Alembic config section missing")

    connectable = engine_from_config(
        section,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            # SQLite cannot ALTER most column properties; batch mode rebuilds the table instead.
            render_as_batch=connection.dialect.name == "sqlite",
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
