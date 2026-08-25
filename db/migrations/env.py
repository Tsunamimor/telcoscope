"""Alembic environment configuration for telcoscope."""
from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from telcoscope.config import settings
from telcoscope.db.models import Base

config = context.config

# Point Alembic at our Settings-derived URL.
config.set_main_option("sqlalchemy.url", settings.postgres_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Metadata for autogenerate to compare against.
target_metadata = Base.metadata

# Include ALL schemas — Postgres searches only `public` by default, but we
# want Alembic to see everything in `raw`, `dims`, `analytics`, `marts`.
def include_name(name: str | None, type_: str, parent_names: dict) -> bool:
    if type_ == "schema":
        return name in {"raw", "dims", "analytics", "marts", "public"}
    return True


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_schemas=True,
        include_name=include_name,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_schemas=True,
            include_name=include_name,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()