import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.dialects.postgresql import TSVECTOR

from app.core.config import settings
from app.db.base import Base  # noqa: F401 — imports all models
from app.models.feeder import TSVector

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

DB_URL = settings.DATABASE_URL


def render_item(type_, obj, autogen_context):
    """Teach Alembic how to render custom types."""
    if isinstance(obj, TSVector):
        autogen_context.imports.add("from sqlalchemy.dialects.postgresql import TSVECTOR")
        return "TSVECTOR()"
    return False


# PostGIS system tables to exclude from migrations
POSTGIS_TABLES = {"spatial_ref_sys", "geometry_columns", "geography_columns", "raster_columns", "raster_overviews"}


def include_object(object, name, type_, reflected, compare_to):
    """Exclude PostGIS system tables from autogenerate."""
    if type_ == "table" and name in POSTGIS_TABLES:
        return False
    return True


def run_migrations_offline():
    context.configure(
        url=DB_URL,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection):
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        render_item=render_item,
        include_object=include_object,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online():
    engine = create_async_engine(DB_URL)
    async with engine.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
