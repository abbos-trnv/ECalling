from collections.abc import Iterator

import psycopg
from psycopg.rows import dict_row

from apps.api.settings import get_settings


def get_connection() -> Iterator[psycopg.Connection]:
    with psycopg.connect(
        get_settings().database_url, row_factory=dict_row, connect_timeout=3
    ) as connection:
        yield connection
