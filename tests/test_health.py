import psycopg
from fastapi.testclient import TestClient

from apps.api import main
from apps.api.db import get_connection

client = TestClient(main.app)


def test_liveness_does_not_require_database(monkeypatch):
    def unexpected_database_call():
        raise AssertionError("Liveness must not use database")

    monkeypatch.setattr(main, "check_database", unexpected_database_call)
    assert client.get("/health/live").json() == {"status": "ok"}


def test_readiness_success(monkeypatch):
    monkeypatch.setattr(main, "check_database", lambda: None)
    response = client.get("/health/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ready", "db": "ok"}


def test_database_failure_returns_503_without_credentials(monkeypatch):
    def unavailable():
        raise psycopg.OperationalError("postgresql://user:secret@localhost/demo")

    monkeypatch.setattr(main, "check_database", unavailable)
    response = client.get("/health/ready")
    assert response.status_code == 503
    assert response.json() == {"status": "unavailable", "db": "error"}
    assert "secret" not in response.text


def test_system_does_not_claim_inference_is_available():
    response = client.get("/api/v1/system")
    assert response.status_code == 200
    assert response.json()["mode"] == "local_demo"
    assert response.json()["pipeline_available"] is True
    assert response.json()["real_inference_available"] is False


def test_organizations_database_unavailable_does_not_expose_details():
    def unavailable():
        raise psycopg.OperationalError("postgresql://user:secret@localhost/demo")

    main.app.dependency_overrides[get_connection] = unavailable
    try:
        response = client.get("/api/v1/companies")
        assert response.status_code == 503
        assert response.json() == {"detail": "База временно недоступна"}
        assert "secret" not in response.text
    finally:
        main.app.dependency_overrides.pop(get_connection, None)
