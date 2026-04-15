"""Tests for authentication routes."""

import pytest

from app.market_data.symbol_mapper import (
    get_default_symbol_mappings,
)


@pytest.fixture(autouse=True)
def clean_db(app):
    """Clean the users collection before each test."""
    with app.app_context():
        from app.extensions import mongo
        mongo.db.users.delete_many({})
        mongo.db.auth_refresh_sessions.delete_many({})
    yield


def _refresh_cookie_name(app):
    """Return the configured refresh-cookie name."""

    return app.config["AUTH_REFRESH_COOKIE_NAME"]


def _refresh_cookie_path(app):
    """Return the configured refresh-cookie path."""

    return app.config["AUTH_REFRESH_COOKIE_PATH"]


def test_register_success(client, app):
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
    assert data["user"]["market_data_mappings"] == {}
    assert data["user"]["whatif_target_r_multiple"] == 2.0
    assert (
        data["user"]["symbol_mappings"]
        == get_default_symbol_mappings()
    )
    assert response.headers.get("Set-Cookie")
    assert client.get_cookie(
        _refresh_cookie_name(app),
        path=_refresh_cookie_path(app),
    ) is not None


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


def test_login_success(client, app):
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
    assert data["user"]["market_data_mappings"] == {}
    assert data["user"]["whatif_target_r_multiple"] == 2.0
    assert (
        data["user"]["symbol_mappings"]
        == get_default_symbol_mappings()
    )
    assert client.get_cookie(
        _refresh_cookie_name(app),
        path=_refresh_cookie_path(app),
    ) is not None


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
    data = response.get_json()
    assert data["username"] == "testuser"
    assert data["market_data_mappings"] == {}
    assert data["whatif_target_r_multiple"] == 2.0
    assert data["symbol_mappings"] == get_default_symbol_mappings()


def test_me_without_token(client):
    """GET /me without token returns 401."""
    response = client.get("/api/auth/me")
    assert response.status_code == 401


def test_refresh_rotates_cookie_and_returns_new_access_token(
    client, app
):
    """POST /refresh rotates the persistent session cookie."""

    reg = client.post("/api/auth/register", json={
        "username": "testuser",
        "password": "testpass123",
        "timezone": "America/New_York",
    })
    initial_cookie = client.get_cookie(
        _refresh_cookie_name(app),
        path=_refresh_cookie_path(app),
    )

    response = client.post("/api/auth/refresh")

    assert response.status_code == 200
    assert "token" in response.get_json()
    rotated_cookie = client.get_cookie(
        _refresh_cookie_name(app),
        path=_refresh_cookie_path(app),
    )
    assert rotated_cookie is not None
    assert initial_cookie is not None
    assert rotated_cookie.value != initial_cookie.value


def test_refresh_without_cookie_returns_401_and_clears_cookie(
    client, app
):
    """POST /refresh fails cleanly without a refresh cookie."""

    response = client.post("/api/auth/refresh")

    assert response.status_code == 401
    assert (
        response.get_json()["error"]["message"]
        == "Session expired. Please log in again."
    )
    assert client.get_cookie(
        _refresh_cookie_name(app),
        path=_refresh_cookie_path(app),
    ) is None


def test_logout_clears_refresh_cookie(client, app):
    """POST /logout revokes the browser refresh session."""

    client.post("/api/auth/register", json={
        "username": "testuser",
        "password": "testpass123",
        "timezone": "America/New_York",
    })
    response = client.post("/api/auth/logout")

    assert response.status_code == 200
    assert client.get_cookie(
        _refresh_cookie_name(app),
        path=_refresh_cookie_path(app),
    ) is None


def test_refresh_fails_after_logout(client):
    """Logging out revokes the refresh session."""

    client.post("/api/auth/register", json={
        "username": "testuser",
        "password": "testpass123",
        "timezone": "America/New_York",
    })
    client.post("/api/auth/logout")

    response = client.post("/api/auth/refresh")

    assert response.status_code == 401


def test_change_password_revokes_refresh_sessions(client):
    """Password change invalidates persistent browser sessions."""

    reg = client.post("/api/auth/register", json={
        "username": "testuser",
        "password": "testpass123",
        "timezone": "America/New_York",
    })
    token = reg.get_json()["token"]
    change_response = client.post(
        "/api/auth/change-password",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "current_password": "testpass123",
            "new_password": "newpass456",
        },
    )

    assert change_response.status_code == 200

    refresh_response = client.post("/api/auth/refresh")

    assert refresh_response.status_code == 401


def test_update_symbol_mappings_persists_to_profile(client):
    """Updating symbol mappings returns and persists the new config."""
    reg = client.post("/api/auth/register", json={
        "username": "mappinguser",
        "password": "testpass123",
        "timezone": "America/New_York",
    })
    token = reg.get_json()["token"]
    symbol_mappings = get_default_symbol_mappings()
    symbol_mappings["MES"] = {
        "dollar_value_per_point": 8.0,
    }

    response = client.put(
        "/api/auth/symbol-mappings",
        headers={"Authorization": f"Bearer {token}"},
        json={"symbol_mappings": symbol_mappings},
    )

    assert response.status_code == 200
    assert response.get_json()["symbol_mappings"] == symbol_mappings

    me_response = client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert me_response.status_code == 200
    assert (
        me_response.get_json()["symbol_mappings"]
        == symbol_mappings
    )


def test_update_symbol_mappings_rejects_invalid_point_value(client):
    """Updating symbol mappings validates point values."""
    reg = client.post("/api/auth/register", json={
        "username": "invalidmappinguser",
        "password": "testpass123",
        "timezone": "America/New_York",
    })
    token = reg.get_json()["token"]
    symbol_mappings = get_default_symbol_mappings()
    symbol_mappings["MES"][
        "dollar_value_per_point"
    ] = -1

    response = client.put(
        "/api/auth/symbol-mappings",
        headers={"Authorization": f"Bearer {token}"},
        json={"symbol_mappings": symbol_mappings},
    )

    assert response.status_code == 400


def test_update_whatif_target_r_multiple_persists_to_profile(client):
    """Updating the default What-if target returns and persists it."""
    reg = client.post("/api/auth/register", json={
        "username": "whatiftargetuser",
        "password": "testpass123",
        "timezone": "America/New_York",
    })
    token = reg.get_json()["token"]

    response = client.put(
        "/api/auth/whatif-target-r-multiple",
        headers={"Authorization": f"Bearer {token}"},
        json={"whatif_target_r_multiple": 3.5},
    )

    assert response.status_code == 200
    assert response.get_json()["whatif_target_r_multiple"] == 3.5

    me_response = client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert me_response.status_code == 200
    assert me_response.get_json()["whatif_target_r_multiple"] == 3.5


def test_update_whatif_target_r_multiple_rejects_invalid_values(client):
    """Updating the What-if target validates positive numeric values."""
    reg = client.post("/api/auth/register", json={
        "username": "invalidwhatiftargetuser",
        "password": "testpass123",
        "timezone": "America/New_York",
    })
    token = reg.get_json()["token"]

    response = client.put(
        "/api/auth/whatif-target-r-multiple",
        headers={"Authorization": f"Bearer {token}"},
        json={"whatif_target_r_multiple": 0},
    )

    assert response.status_code == 400


def test_update_market_data_mappings_persists_to_profile(client):
    """Updating market-data mappings returns and persists the config."""
    reg = client.post("/api/auth/register", json={
        "username": "marketdatamappinguser",
        "password": "testpass123",
        "timezone": "America/New_York",
    })
    token = reg.get_json()["token"]
    market_data_mappings = {"MES": "ES"}

    response = client.put(
        "/api/auth/market-data-mappings",
        headers={"Authorization": f"Bearer {token}"},
        json={"market_data_mappings": market_data_mappings},
    )

    assert response.status_code == 200
    assert (
        response.get_json()["market_data_mappings"]
        == market_data_mappings
    )

    me_response = client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert me_response.status_code == 200
    assert (
        me_response.get_json()["market_data_mappings"]
        == market_data_mappings
    )


def test_update_market_data_mappings_rejects_invalid_values(client):
    """Updating market-data mappings validates mapping values."""
    reg = client.post("/api/auth/register", json={
        "username": "invalidmarketdatamappinguser",
        "password": "testpass123",
        "timezone": "America/New_York",
    })
    token = reg.get_json()["token"]

    response = client.put(
        "/api/auth/market-data-mappings",
        headers={"Authorization": f"Bearer {token}"},
        json={"market_data_mappings": {"MES": "   "}},
    )

    assert response.status_code == 400
