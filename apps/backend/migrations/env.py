"""Alembic environment (sync, SQLAlchemy 2.0).

- Connection URL kaynak koda gömülmez: önce `config`'e programatik set edilmiş
  `sqlalchemy.url` (testler bunu override eder), yoksa `MIGRATION_DATABASE_URL`
  (flowpilot_migrator rolü) kullanılır.
- Module-owned metadata'lar burada toplanır (identity + organization).
- Import sırasında hiçbir database bağlantısı açılmaz; engine yalnız
  `run_migrations_online` içinde oluşturulur.
"""

from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from flowpilot.config.settings import get_settings
from flowpilot.modules.identity.infrastructure.persistence.tables import (
    metadata as identity_metadata,
)
from flowpilot.modules.organization.infrastructure.persistence.tables import (
    metadata as organization_metadata,
)

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Hand-written migration'lar için; autogenerate ileride bu listeyi kullanır.
target_metadata = [identity_metadata, organization_metadata]


def _resolve_url() -> str:
    configured = config.get_main_option("sqlalchemy.url")
    if configured:
        return configured
    return get_settings().require_migration_database_url()


def run_migrations_offline() -> None:
    context.configure(
        url=_resolve_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    section = config.get_section(config.config_ini_section, {})
    section["sqlalchemy.url"] = _resolve_url()
    connectable = engine_from_config(
        section,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()
    connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
