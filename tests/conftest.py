import os
from uuid import uuid4

import psycopg
import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from psycopg import sql
from psycopg.rows import dict_row
from sqlalchemy import create_engine

from apps.api.db import get_connection
from apps.api.main import app


@pytest.fixture
def database():
    dsn = os.environ.get("TEST_DATABASE_URL")
    if not dsn:
        pytest.skip("Set TEST_DATABASE_URL to run PostgreSQL integration tests")
    schema = "test_" + uuid4().hex
    with psycopg.connect(dsn, autocommit=True) as admin:
        admin.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
    engine = create_engine(
        dsn.replace("postgresql://", "postgresql+psycopg://", 1),
        connect_args={"options": f"-csearch_path={schema}"},
    )

    def migrate(target, downgrade=False):
        config = Config("alembic.ini")
        with engine.begin() as connection:
            config.attributes["connection"] = connection
            (command.downgrade if downgrade else command.upgrade)(config, target)

    def connect():
        return psycopg.connect(dsn, options=f"-csearch_path={schema}", row_factory=dict_row)

    try:
        migrate("head")
        yield connect, migrate
    finally:
        engine.dispose()
        with psycopg.connect(dsn, autocommit=True) as admin:
            # Only this test's freshly generated schema, never public/application data.
            admin.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))


@pytest.fixture
def client(database):
    connect, _ = database

    def isolated_connection():
        with connect() as connection:
            yield connection

    app.dependency_overrides[get_connection] = isolated_connection
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.pop(get_connection, None)
