"""Integration tests for the authentication endpoints.

Each test uses a unique email/username (uuid4) so tests never collide, even
though `_clean_tables` truncates tables between tests anyway.
"""

from uuid import uuid4

from app.models.user import User


async def _register(client, email=None, username=None, password="supersecret123"):
    email = email or f"user-{uuid4()}@example.com"
    username = username or f"user_{uuid4().hex[:16]}"
    resp = await client.post(
        "/auth/register",
        json={"email": email, "username": username, "password": password},
    )
    assert resp.status_code == 201, resp.text
    return resp.json(), email, username, password


async def _login(client, email, password):
    resp = await client.post("/auth/login", json={"email": email, "password": password})
    return resp


async def test_register_creates_user_and_hashes_password(client, db):
    body, email, username, password = await _register(client)

    assert body["email"] == email
    assert body["username"] == username
    assert "id" in body

    user = await db.get(User, body["id"])
    assert user is not None
    # The password must never be stored in plaintext.
    assert user.hashed_password != password
    assert user.hashed_password.startswith("$argon2")


async def test_register_duplicate_email_returns_409(client):
    _, email, _, _ = await _register(client)

    resp = await client.post(
        "/auth/register",
        json={
            "email": email,
            "username": f"other_{uuid4().hex[:16]}",
            "password": "supersecret123",
        },
    )

    assert resp.status_code == 409


async def test_login_returns_tokens(client):
    _, email, _, password = await _register(client)

    resp = await _login(client, email, password)

    assert resp.status_code == 200
    body = resp.json()
    assert body["access_token"]
    assert body["refresh_token"]
    assert body["token_type"] == "bearer"


async def test_login_wrong_password_returns_401(client):
    _, email, _, _ = await _register(client)

    resp = await _login(client, email, "wrong-password")

    assert resp.status_code == 401


async def test_me_returns_current_user(client):
    _, email, _, password = await _register(client)
    login = (await _login(client, email, password)).json()

    resp = await client.get(
        "/auth/me", headers={"Authorization": f"Bearer {login['access_token']}"}
    )

    assert resp.status_code == 200
    assert resp.json()["email"] == email


async def test_me_without_token_returns_401(client):
    resp = await client.get("/auth/me")

    assert resp.status_code == 401


async def test_refresh_rotates_token(client):
    _, email, _, password = await _register(client)
    login = (await _login(client, email, password)).json()
    old_refresh = login["refresh_token"]

    first = await client.post("/auth/refresh", json={"refresh_token": old_refresh})
    assert first.status_code == 200
    new_tokens = first.json()
    assert new_tokens["access_token"]
    assert new_tokens["refresh_token"]
    assert new_tokens["refresh_token"] != old_refresh

    # Reusing the OLD refresh token after rotation must be rejected (revoked).
    second = await client.post("/auth/refresh", json={"refresh_token": old_refresh})
    assert second.status_code == 401


async def test_refresh_invalid_token_returns_401(client):
    resp = await client.post("/auth/refresh", json={"refresh_token": "not-a-token"})

    assert resp.status_code == 401


async def test_logout_revokes_refresh(client):
    _, email, _, password = await _register(client)
    login = (await _login(client, email, password)).json()
    refresh_token = login["refresh_token"]

    logout = await client.post("/auth/logout", json={"refresh_token": refresh_token})
    assert logout.status_code == 204

    # The now-revoked refresh token must no longer mint new tokens.
    resp = await client.post("/auth/refresh", json={"refresh_token": refresh_token})
    assert resp.status_code == 401
