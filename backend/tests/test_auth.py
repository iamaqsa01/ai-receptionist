from tests.conftest import auth_headers, register_and_login


def test_register_hashes_password_and_never_returns_it(client, db_session):
    resp = client.post(
        "/api/v1/auth/register",
        json={"email": "alice@example.com", "password": "correct-horse-1", "full_name": "Alice"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert "password" not in body
    assert "hashed_password" not in body

    from app.models.user import User

    user = db_session.query(User).filter_by(email="alice@example.com").one()
    assert user.hashed_password != "correct-horse-1"
    assert user.hashed_password.startswith("$2b$")


def test_duplicate_registration_is_rejected(client):
    payload = {"email": "dup@example.com", "password": "correct-horse-1", "full_name": "Dup"}
    assert client.post("/api/v1/auth/register", json=payload).status_code == 201
    resp = client.post("/api/v1/auth/register", json=payload)
    assert resp.status_code == 409


def test_login_success_returns_token(client):
    register_and_login(client, "bob@example.com")


def test_login_wrong_password_rejected(client):
    client.post(
        "/api/v1/auth/register",
        json={"email": "carol@example.com", "password": "correct-horse-1", "full_name": "Carol"},
    )
    resp = client.post(
        "/api/v1/auth/login", json={"email": "carol@example.com", "password": "wrong-password"}
    )
    assert resp.status_code == 401


def test_login_unknown_email_rejected(client):
    resp = client.post(
        "/api/v1/auth/login", json={"email": "nobody@example.com", "password": "whatever123"}
    )
    assert resp.status_code == 401


def test_protected_route_requires_token(client):
    resp = client.get("/api/v1/auth/me")
    assert resp.status_code == 401


def test_protected_route_rejects_garbage_token(client):
    resp = client.get("/api/v1/auth/me", headers=auth_headers("not-a-real-token"))
    assert resp.status_code == 401


def test_me_returns_current_user_and_memberships(client):
    token = register_and_login(client, "dana@example.com")
    resp = client.get("/api/v1/auth/me", headers=auth_headers(token))
    assert resp.status_code == 200
    body = resp.json()
    assert body["email"] == "dana@example.com"
    assert body["memberships"] == []


def test_logout_revokes_token(client):
    token = register_and_login(client, "erin@example.com")

    resp = client.get("/api/v1/auth/me", headers=auth_headers(token))
    assert resp.status_code == 200

    resp = client.post("/api/v1/auth/logout", headers=auth_headers(token))
    assert resp.status_code == 204

    resp = client.get("/api/v1/auth/me", headers=auth_headers(token))
    assert resp.status_code == 401


def test_logout_twice_is_safe(client):
    token = register_and_login(client, "frank@example.com")
    assert client.post("/api/v1/auth/logout", headers=auth_headers(token)).status_code == 204
    # Second logout: token is already revoked, so auth itself now fails (401),
    # not a server error.
    assert client.post("/api/v1/auth/logout", headers=auth_headers(token)).status_code == 401
