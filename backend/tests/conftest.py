import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.rate_limit import login_rate_limiter, register_rate_limiter, telephony_webhook_rate_limiter
from app.database.session import get_db
from app.main import app
from app.models import Base
from app.models.workspace import Workspace


@pytest.fixture(autouse=True)
def _reset_rate_limiters():
    """The Phase 14 rate limiters (app.core.rate_limit) are process-global
    singletons — without resetting them, hit counts would accumulate
    across every test in the suite (all run in one process) and eventually
    trip a 429 in a later, unrelated test. Reset before every test so each
    one starts with a clean quota; a test that specifically exercises rate
    limiting does so entirely within its own budget."""
    for limiter in (login_rate_limiter, register_rate_limiter, telephony_webhook_rate_limiter):
        limiter._hits.clear()
    yield


@pytest.fixture()
def db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestingSessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False, future=True)

    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)
        engine.dispose()


@pytest.fixture()
def client(db_session):
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def register_and_login(
    client: TestClient,
    email: str,
    password: str = "correct-horse-1",
    full_name: str = "Test User",
) -> str:
    resp = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password, "full_name": full_name},
    )
    assert resp.status_code == 201, resp.text

    resp = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


def auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def create_workspace(
    client: TestClient, token: str, name: str, slug: str, *, onboarded: bool = True
) -> str:
    """Create a workspace and (by default) mark it onboarded.

    Onboarding is now a per-workspace flag (Workspace.is_onboarded) and the
    data routers gate on it server-side (app.api.deps
    .get_current_onboarded_tenant). Most tests exercise a set-up workspace,
    so flip the flag directly on the shared test session here — cheaper and
    clearer than driving the full clinic-setup flow. Tests that cover the
    pre-onboarding state pass ``onboarded=False``.
    """
    resp = client.post(
        "/api/v1/workspaces",
        json={"name": name, "slug": slug, "timezone": "UTC"},
        headers=auth_headers(token),
    )
    assert resp.status_code == 201, resp.text
    workspace_id = resp.json()["id"]

    if onboarded:
        gen = app.dependency_overrides.get(get_db, get_db)()
        db = next(gen)
        ws = db.get(Workspace, uuid.UUID(workspace_id))
        ws.is_onboarded = True
        db.add(ws)
        db.commit()

    return workspace_id
