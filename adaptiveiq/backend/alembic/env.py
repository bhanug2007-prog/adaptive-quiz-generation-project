"""Alembic environment: uses the app's settings and models."""
from logging.config import fileConfig

from alembic import context

import app.models  # noqa: F401  (registers every table)
from app.core.config import get_settings
from app.core.db import Base, make_engine

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def url() -> str:
    return config.attributes.get("database_url") or get_settings().database_url


def run_migrations_offline():
    context.configure(url=url(), target_metadata=target_metadata, literal_binds=True,
                      render_as_batch=url().startswith("sqlite"))
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    engine = make_engine(url())
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata,
                          render_as_batch=connection.dialect.name == "sqlite", compare_type=True)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
