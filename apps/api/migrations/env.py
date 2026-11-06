from alembic import context
from sqlalchemy import create_engine, pool

from apps.api.settings import get_settings

url = get_settings().database_url.replace("postgresql://", "postgresql+psycopg://", 1)


def run_migrations(connection):
    context.configure(connection=connection)
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    context.configure(url=url, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()
elif context.config.attributes.get("connection") is not None:
    run_migrations(context.config.attributes["connection"])
else:
    engine = create_engine(url, poolclass=pool.NullPool)
    with engine.connect() as connection:
        run_migrations(connection)
    engine.dispose()
