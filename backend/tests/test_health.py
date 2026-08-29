from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_root() -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert response.json()["message"] == "AI Receptionist API"


def test_health() -> None:
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert "app_name" in body


def test_readiness_ok_when_database_is_reachable(client) -> None:
    """Uses the `client` fixture (conftest.py) — its get_db() override
    points at the working in-memory SQLite test DB, unlike this file's
    bare TestClient(app) above, which would hit whatever DATABASE_URL is
    actually configured (no live Postgres in a test environment)."""
    response = client.get("/api/v1/health/ready")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["checks"] == [{"name": "database", "status": "ok", "detail": None}]


def test_check_database_catches_a_real_connection_failure() -> None:
    """Exercises the actual failure path (not a mocked-out check): a
    Session bound to a bad engine, so the SELECT 1 genuinely raises, and
    _check_database must turn that into a status="error" result rather
    than letting the exception escape the readiness endpoint."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from app.api.health import _check_database

    bad_engine = create_engine("sqlite:////nonexistent/path/does-not-exist.db")
    BadSession = sessionmaker(bind=bad_engine)
    result = _check_database(BadSession())
    assert result.status == "error"
    assert result.detail == "database unreachable"


def test_readiness_reports_error_status_without_leaking_exception_detail(client, monkeypatch) -> None:
    from app.api import health as health_module
    from app.schemas.health import ReadinessCheck

    monkeypatch.setattr(
        health_module, "_check_database",
        lambda db: ReadinessCheck(name="database", status="error", detail="database unreachable"),
    )

    response = client.get("/api/v1/health/ready")
    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "error"
    assert body["checks"][0]["detail"] == "database unreachable"
