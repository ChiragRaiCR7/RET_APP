from logging.config import fileConfig

from alembic import context
from app.db import get_engine
from app.models import Base

if context.config.config_file_name is not None:
    fileConfig(context.config.config_file_name, disable_existing_loggers=False)


def run_migrations_online() -> None:
    with get_engine().connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=Base.metadata,
            render_as_batch=True,  # SQLite needs table rebuilds for most ALTERs
        )
        with context.begin_transaction():
            context.run_migrations()


run_migrations_online()
