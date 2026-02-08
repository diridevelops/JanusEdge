"""Tests for authentication routes."""

import pytest


@pytest.fixture(autouse=True)
def clean_db(app):
    """Clean the users collection before each test."""
    with app.app_context():
        from app.extensions import mongo
        mongo.db.users.delete_many({})
    yield


def test_register_success(client):
    """Register a new user returns 201 with token."""
    response = client.post("/api/auth/register", json={
        "username": "testuser",
        "password": "testpass123",
        "timezone": "America/New_York",
    })
    assert response.status_code == 201
    data = response.get_json()
    assert "token" in data
    assert data["user"]["username"] == "testuser"
    assert data["user"]["timezone"] == "America/New_York"


def test_register_duplicate_username(client):
    """Registering with existing username returns 400."""
    client.post("/api/auth/register", json={
        "username": "testuser",
        "password": "testpass123",
        "timezone": "America/New_York",
    })
    response = client.post("/api/auth/register", json={
        "username": "testuser",
        "password": "otherpass456",
        "timezone": "America/Chicago",
    })
    assert response.status_code == 400


def test_register_invalid_timezone(client):
    """Registering with invalid timezone returns 400."""
    response = client.post("/api/auth/register", json={
        "username": "testuser",
        "password": "testpass123",
        "timezone": "Invalid/Timezone",
    })
    assert response.status_code == 400


def test_register_missing_fields(client):
    """Registering without required fields returns 400."""
    response = client.post("/api/auth/register", json={
        "username": "testuser",
    })
    assert response.status_code == 400


def test_login_success(client):
    """Login with valid credentials returns token."""
    client.post("/api/auth/register", json={
        "username": "testuser",
        "password": "testpass123",
        "timezone": "America/New_York",
    })
    response = client.post("/api/auth/login", json={
        "username": "testuser",
        "password": "testpass123",
    })
    assert response.status_code == 200
    data = response.get_json()
    assert "token" in data
    assert data["user"]["username"] == "testuser"


def test_login_wrong_password(client):
    """Login with wrong password returns 401."""
    client.post("/api/auth/register", json={
        "username": "testuser",
        "password": "testpass123",
        "timezone": "America/New_York",
    })
    response = client.post("/api/auth/login", json={
        "username": "testuser",
        "password": "wrongpassword",
    })
    assert response.status_code == 401


def test_login_nonexistent_user(client):
    """Login with nonexistent user returns 401."""
    response = client.post("/api/auth/login", json={
        "username": "nouser",
        "password": "testpass123",
    })
    assert response.status_code == 401


def test_me_with_token(client):
    """GET /me with valid token returns user profile."""
    reg = client.post("/api/auth/register", json={
        "username": "testuser",
        "password": "testpass123",
        "timezone": "America/New_York",
    })
    token = reg.get_json()["token"]
    response = client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert response.get_json()["username"] == "testuser"


def test_me_without_token(client):
    """GET /me without token returns 401."""
    response = client.get("/api/auth/me")
    assert response.status_code == 401


def test_logout(client):
    """POST /logout with valid token returns 200."""
    reg = client.post("/api/auth/register", json={
        "username": "testuser",
        "password": "testpass123",
        "timezone": "America/New_York",
    })
    token = reg.get_json()["token"]
    response = client.post(
        "/api/auth/logout",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
