"""Explicit, repeatable seed: python -m apps.api.seed. Never overwrites names."""

from uuid import UUID

import psycopg

from apps.api.settings import get_settings

COMPANIES = [
    (UUID("00000000-0000-4000-8000-000000000001"), "ООО Ромашка"),
    (UUID("00000000-0000-4000-8000-000000000002"), "ООО Вектор"),
]


def seed(connection: psycopg.Connection) -> None:
    for index, (company_id, name) in enumerate(COMPANIES, start=1):
        connection.execute(
            "INSERT INTO companies (id, name) VALUES (%s, %s) ON CONFLICT (id) DO NOTHING",
            (company_id, name),
        )
        for number in (1, 2):
            employee_id = UUID(f"00000000-0000-4000-8000-{index * 100 + number:012d}")
            connection.execute(
                "INSERT INTO employees (id, company_id, display_name) VALUES (%s, %s, %s) "
                "ON CONFLICT (id) DO NOTHING",
                (employee_id, company_id, f"Агент {number}"),
            )


if __name__ == "__main__":
    with psycopg.connect(get_settings().database_url) as connection:
        seed(connection)
    print("Demo seed ready: 2 companies, 2 employees per company. Existing names preserved.")
