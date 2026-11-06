from uuid import uuid4

import psycopg
import pytest

from apps.api.seed import seed

pytestmark = pytest.mark.integration


def company(client, name="Компания A"):
    response = client.post("/api/v1/companies", json={"name": name})
    assert response.status_code == 201
    return response.json()["id"]


def test_crud_and_company_scoping(client):
    first = company(client, "  Компания A  ")
    second = company(client, "Компания B")
    assert client.get("/api/v1/companies").json()[0]["name"] == "Компания A"
    path = f"/api/v1/companies/{first}/employees"
    response = client.post(path, json={"display_name": "  Агент A  "})
    assert response.status_code == 201
    employee = response.json()
    assert employee["display_name"] == "Агент A"
    assert client.get(f"/api/v1/companies/{second}/employees").json() == []
    wrong_path = f"/api/v1/companies/{second}/employees/{employee['id']}"
    assert client.put(wrong_path, json={"display_name": "Чужое изменение"}).status_code == 404
    assert client.delete(wrong_path).status_code == 404
    assert client.get(path).json()[0]["display_name"] == "Агент A"
    assert client.delete(f"/api/v1/companies/{first}").status_code == 409
    employee_path = f"{path}/{employee['id']}"
    assert client.put(employee_path, json={"display_name": "Новое имя"}).status_code == 200
    assert client.delete(employee_path).status_code == 204
    assert client.delete(employee_path).status_code == 404
    assert (
        client.put(f"/api/v1/companies/{first}", json={"name": "Новое название"}).status_code == 200
    )
    assert client.delete(f"/api/v1/companies/{first}").status_code == 204


@pytest.mark.parametrize("name", ["", "   ", "x" * 201, None])
def test_invalid_names_are_rejected(client, name):
    assert client.post("/api/v1/companies", json={"name": name}).status_code == 422
    identifier = company(client)
    path = f"/api/v1/companies/{identifier}/employees"
    assert client.post(path, json={"display_name": name}).status_code == 422
    assert client.get(path).json() == []


def test_missing_company_invalid_uuid_and_pagination(client):
    path = f"/api/v1/companies/{uuid4()}/employees"
    assert client.get(path).status_code == 404
    assert client.post(path, json={"display_name": "Агент"}).status_code == 404
    assert client.get("/api/v1/companies/not-a-uuid/employees").status_code == 422
    assert client.get("/api/v1/companies?limit=101").status_code == 422
    assert client.get("/api/v1/companies?offset=-1").status_code == 422
    first = company(client, "Первая")
    second = company(client, "Вторая")
    assert client.get("/api/v1/companies?limit=1").json()[0]["id"] == first
    assert client.get("/api/v1/companies?limit=1&offset=1").json()[0]["id"] == second
    employee_path = f"/api/v1/companies/{first}/employees"
    for number in range(3):
        client.post(employee_path, json={"display_name": f"Агент {number}"})
    assert client.get(f"{employee_path}?limit=1&offset=1").json()[0]["display_name"] == "Агент 1"
    assert (
        client.post("/api/v1/companies", json={"name": "A", "id": str(uuid4())}).status_code == 422
    )


def test_seed_is_repeatable_and_does_not_overwrite(database):
    connect, _ = database
    with connect() as connection:
        seed(connection)
        original = connection.execute("SELECT id FROM companies ORDER BY id LIMIT 1").fetchone()
        connection.execute(
            "UPDATE companies SET name = %s WHERE id = %s", ("Изменено", original["id"])
        )
        seed(connection)
        assert connection.execute("SELECT count(*) AS n FROM companies").fetchone()["n"] == 2
        assert connection.execute("SELECT count(*) AS n FROM employees").fetchone()["n"] == 4
        assert (
            connection.execute(
                "SELECT name FROM companies WHERE id = %s", (original["id"],)
            ).fetchone()["name"]
            == "Изменено"
        )


def test_database_constraints_and_migration_roundtrip(database):
    connect, migrate = database
    with connect() as connection:
        with pytest.raises(psycopg.errors.ForeignKeyViolation), connection.transaction():
            connection.execute(
                "INSERT INTO employees (id, company_id, display_name) VALUES (%s, %s, %s)",
                (uuid4(), uuid4(), "Без компании"),
            )
        with pytest.raises(psycopg.errors.CheckViolation), connection.transaction():
            connection.execute("INSERT INTO companies (id, name) VALUES (%s, %s)", (uuid4(), "  "))
    migrate("base", downgrade=True)
    with connect() as connection:
        assert (
            connection.execute("SELECT to_regclass('companies') AS name").fetchone()["name"] is None
        )
    migrate("head")
    with connect() as connection:
        assert connection.execute("SELECT count(*) AS n FROM companies").fetchone()["n"] == 0
