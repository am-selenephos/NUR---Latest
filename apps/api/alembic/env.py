import asyncio
import os

from alembic import context
from sqlalchemy.ext.asyncio import create_async_engine

from app.models import Base  # imports all models

config = context.config
target_metadata = Base.metadata


def _url() -> str:
    """Resolve the migration target, or refuse to run.

    This used to fall back to a hardcoded `localhost:5432`. That default is not
    the database this project runs on — the container publishes 15432 — so
    invoking alembic from a shell that had not exported either variable
    migrated a *different* database and reported success while doing it. The
    application stayed on an old revision and nothing said so.

    A migration tool that silently picks its own target is worse than one that
    stops, so an unset environment is now a hard error naming both variables.
    """
    url = os.environ.get("ALEMBIC_DATABASE_URL") or os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError(
            "No migration target: set ALEMBIC_DATABASE_URL (preferred, schema-owner "
            "role) or DATABASE_URL. Refusing to guess — the previous default "
            "pointed at localhost:5432, which is not the database this project "
            "runs on, and migrating it silently left the app on an old revision."
        )
    return url


def run_migrations_offline() -> None:
    context.configure(url=_url(), target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def _do_run_migrations(connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    engine = create_async_engine(_url())
    async with engine.connect() as connection:
        await connection.run_sync(_do_run_migrations)
    await engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
