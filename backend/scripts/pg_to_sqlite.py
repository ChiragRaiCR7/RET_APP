"""Copy an existing RET database (PostgreSQL) into the SQLite file the app now uses.

Usage (from backend/, with the app stopped):
    uv run alembic upgrade head            # create the target schema first
    uv run --with "psycopg[binary]" python -m scripts.pg_to_sqlite \\
        --source "postgresql+psycopg://user:pass@host:5432/retdb" \\
        --target ./runtime/ret.db

Copies every model table in foreign-key order, only the columns both sides share,
in batches, inside one SQLite transaction, then verifies row counts per table.
The source is only read. The target tables must be empty unless --replace is given.
"""

import argparse
import sys

import sqlalchemy as sa

import api.models  # noqa: F401  registers every table on Base.metadata
from api.core.database import Base

BATCH_ROWS = 1000


def copy(source_url: str, target_path: str, replace: bool) -> dict[str, int]:
    source = sa.create_engine(source_url)
    target = sa.create_engine(f"sqlite:///{target_path}")
    src_meta = sa.MetaData()
    src_meta.reflect(source)
    copied: dict[str, int] = {}
    with source.connect() as src, target.begin() as dst:
        dst.exec_driver_sql("PRAGMA foreign_keys=OFF")
        for table in Base.metadata.sorted_tables:
            if table.name not in src_meta.tables:
                print(f"skip {table.name}: not in source")
                continue
            src_table = src_meta.tables[table.name]
            shared = [c.name for c in table.columns if c.name in src_table.columns]
            existing = dst.execute(sa.select(sa.func.count()).select_from(table)).scalar_one()
            if existing and not replace:
                raise SystemExit(f"{table.name} already has {existing} rows; use --replace")
            if replace:
                dst.execute(table.delete())
            result = src.execution_options(stream_results=True).execute(
                sa.select(*(src_table.c[name] for name in shared)))
            total = 0
            while rows := result.fetchmany(BATCH_ROWS):
                dst.execute(table.insert(), [dict(zip(shared, row, strict=True)) for row in rows])
                total += len(rows)
            copied[table.name] = total
            print(f"{table.name}: {total} rows")
        violations = dst.exec_driver_sql("PRAGMA foreign_key_check").fetchall()
        if violations:
            raise SystemExit(f"foreign key violations after copy (rolled back): {violations[:5]}")
    with target.connect() as dst:
        for name, expected in copied.items():
            actual = dst.execute(sa.text(f'SELECT COUNT(*) FROM "{name}"')).scalar_one()
            if actual != expected:
                raise SystemExit(f"{name}: copied {expected} rows but target has {actual}")
    return copied


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--source", required=True, help="SQLAlchemy URL of the old database")
    parser.add_argument("--target", required=True, help="SQLite file migrated to alembic head")
    parser.add_argument("--replace", action="store_true", help="empty target tables first")
    args = parser.parse_args()
    copied = copy(args.source, args.target, args.replace)
    print(f"done: {sum(copied.values())} rows in {len(copied)} tables")


if __name__ == "__main__":
    sys.exit(main())
