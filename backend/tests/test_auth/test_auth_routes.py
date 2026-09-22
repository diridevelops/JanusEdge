"""Tests for authentication routes."""

import pytest

from app.market_data.symbol_mapper import (
    get_default_symbol_mappings,
)


@pytest.fixture(autouse=True)
def clean_db(app):
    """Clean auth-owned collections before each test."""
    with app.app_context():
        from app.extensions import mongo
        for collection_name in [
            "users",
            "auth_refresh_sessions",
            "trade_accounts",
            "import_batches",
            "executions",
            "trades",
            "tags",
            "tag_categories",
            "audit_logs",
            "market_data_import_batches",
            "media",
            "market_data_datasets",
        ]:
            mongo.db[collection_name].delete_many({})
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
    assert "whatif_target_r_multiple" not in data["user"]
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
    assert "whatif_target_r_multiple" not in data["user"]
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
    assert "whatif_target_r_multiple" not in data
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


def test_update_username_requires_password_and_keeps_session_active(
    client,
):
    """A username change updates login identity without revoking sessions."""
    reg = client.post("/api/auth/register", json={
        "username": "oldusername",
        "password": "testpass123",
        "timezone": "America/New_York",
    })
    token = reg.get_json()["token"]
    headers = {"Authorization": f"Bearer {token}"}

    response = client.put(
        "/api/auth/username",
        headers=headers,
        json={
            "username": "newusername",
            "current_password": "testpass123",
        },
    )

    assert response.status_code == 200
    assert response.get_json()["username"] == "newusername"
    assert client.get("/api/auth/me", headers=headers).status_code == 200
    refresh_response = client.post("/api/auth/refresh")
    assert refresh_response.status_code == 200
    assert refresh_response.get_json()["user"]["username"] == "newusername"

    old_login = client.post("/api/auth/login", json={
        "username": "oldusername",
        "password": "testpass123",
    })
    new_login = client.post("/api/auth/login", json={
        "username": "newusername",
        "password": "testpass123",
    })
    assert old_login.status_code == 401
    assert new_login.status_code == 200


def test_update_username_rejects_duplicate_and_wrong_password(client):
    """Username updates enforce uniqueness and current-password checks."""
    first = client.post("/api/auth/register", json={
        "username": "firstusername",
        "password": "testpass123",
        "timezone": "America/New_York",
    })
    client.post("/api/auth/register", json={
        "username": "secondusername",
        "password": "testpass123",
        "timezone": "America/New_York",
    })
    headers = {
        "Authorization": f"Bearer {first.get_json()['token']}"
    }

    duplicate = client.put(
        "/api/auth/username",
        headers=headers,
        json={
            "username": "secondusername",
            "current_password": "testpass123",
        },
    )
    wrong_password = client.put(
        "/api/auth/username",
        headers=headers,
        json={
            "username": "anotherusername",
            "current_password": "wrongpass",
        },
    )

    assert duplicate.status_code == 400
    assert wrong_password.status_code == 401

    invalid_length = client.put(
        "/api/auth/username",
        headers=headers,
        json={
            "username": "ab",
            "current_password": "testpass123",
        },
    )
    assert invalid_length.status_code == 400


def test_update_username_requires_authentication(client):
    """Username updates require an access token."""
    response = client.put(
        "/api/auth/username",
        json={
            "username": "newusername",
            "current_password": "testpass123",
        },
    )

    assert response.status_code == 401


def test_delete_account_removes_owned_data_and_media(
    client, app
):
    """Account deletion cascades owned data but preserves shared data."""
    from datetime import datetime
    from io import BytesIO

    from bson import ObjectId

    from app.extensions import mongo

    reg = client.post("/api/auth/register", json={
        "username": "deleteaccount",
        "password": "testpass123",
        "timezone": "America/New_York",
    })
    token = reg.get_json()["token"]
    user_id = ObjectId(reg.get_json()["user"]["id"])
    headers = {"Authorization": f"Bearer {token}"}

    other_client = app.test_client()
    other_reg = other_client.post("/api/auth/register", json={
        "username": "keepaccount",
        "password": "testpass123",
        "timezone": "America/New_York",
    })
    other_user_id = ObjectId(other_reg.get_json()["user"]["id"])

    media_key = f"{user_id}/trade/media.png"
    orphan_media_key = f"{user_id}/orphan/orphan.png"
    other_media_key = f"{other_user_id}/trade/media.png"
    shared_symbol = f"SHARED-{user_id}"
    shared_object_key = f"{shared_symbol}/ticks/2026/01/01.parquet"
    with app.app_context():
        from app.storage import (
            get_bucket,
            get_client,
            get_market_data_bucket,
        )

        object_store = get_client()
        bucket = get_bucket()
        market_data_bucket = get_market_data_bucket()
        object_store.put_object(
            bucket,
            media_key,
            BytesIO(b"owned"),
            length=5,
            content_type="image/png",
        )
        object_store.put_object(
            bucket,
            orphan_media_key,
            BytesIO(b"orphan"),
            length=6,
            content_type="image/png",
        )
        object_store.put_object(
            bucket,
            other_media_key,
            BytesIO(b"other"),
            length=5,
            content_type="image/png",
        )
        object_store.put_object(
            market_data_bucket,
            shared_object_key,
            BytesIO(b"shared"),
            length=6,
            content_type="application/octet-stream",
        )

        for collection_name in [
            "trade_accounts",
            "import_batches",
            "executions",
            "trades",
            "tags",
            "tag_categories",
            "audit_logs",
            "market_data_import_batches",
            "media",
        ]:
            owned_doc = {
                "user_id": user_id,
                "marker": "owned",
            }
            other_doc = {
                "user_id": other_user_id,
                "marker": "other",
            }
            if collection_name == "media":
                owned_doc["object_key"] = media_key
                other_doc["object_key"] = other_media_key
            mongo.db[collection_name].insert_one(owned_doc)
            mongo.db[collection_name].insert_one(other_doc)

        mongo.db.market_data_datasets.insert_one({
            "symbol": shared_symbol,
            "dataset_type": "ticks",
            "timeframe": None,
            "date": datetime(2026, 1, 1),
            "object_key": shared_object_key,
        })

    response = client.delete(
        "/api/auth/account",
        headers=headers,
        json={
            "current_password": "testpass123",
            "username_confirmation": "deleteaccount",
        },
    )

    assert response.status_code == 200
    assert response.get_json()["message"] == "Account deleted successfully."
    assert client.get_cookie(
        _refresh_cookie_name(app),
        path=_refresh_cookie_path(app),
    ) is None

    with app.app_context():
        assert mongo.db.users.count_documents(
            {"_id": user_id}
        ) == 0
        for collection_name in [
            "auth_refresh_sessions",
            "trade_accounts",
            "import_batches",
            "executions",
            "trades",
            "tags",
            "tag_categories",
            "audit_logs",
            "market_data_import_batches",
            "media",
        ]:
            assert mongo.db[collection_name].count_documents(
                {"user_id": user_id}
            ) == 0

        assert mongo.db.users.count_documents(
            {"_id": other_user_id}
        ) == 1
        assert mongo.db.media.count_documents(
            {"user_id": other_user_id}
        ) == 1
        assert mongo.db.market_data_datasets.count_documents(
            {"symbol": shared_symbol}
        ) == 1

        from app.storage import (
            get_bucket,
            get_client,
            get_market_data_bucket,
        )

        object_store = get_client()
        bucket = get_bucket()
        assert (bucket, media_key) not in object_store.objects
        assert (bucket, orphan_media_key) not in object_store.objects
        assert (bucket, other_media_key) in object_store.objects
        assert (get_market_data_bucket(), shared_object_key) in object_store.objects


def test_delete_account_rejects_invalid_confirmation_without_deleting(
    client
):
    """Deletion requires exact username confirmation and password."""
    reg = client.post("/api/auth/register", json={
        "username": "protectedaccount",
        "password": "testpass123",
        "timezone": "America/New_York",
    })
    token = reg.get_json()["token"]
    headers = {"Authorization": f"Bearer {token}"}

    wrong_confirmation = client.delete(
        "/api/auth/account",
        headers=headers,
        json={
            "current_password": "testpass123",
            "username_confirmation": "wrongaccount",
        },
    )
    wrong_password = client.delete(
        "/api/auth/account",
        headers=headers,
        json={
            "current_password": "wrongpass",
            "username_confirmation": "protectedaccount",
        },
    )

    assert wrong_confirmation.status_code == 400
    assert wrong_password.status_code == 401
    assert client.post("/api/auth/refresh").status_code == 200


def test_deleted_username_can_be_registered_again(client):
    """A deleted username is released by account deletion."""
    reg = client.post("/api/auth/register", json={
        "username": "reusableaccount",
        "password": "testpass123",
        "timezone": "America/New_York",
    })
    client.delete(
        "/api/auth/account",
        headers={
            "Authorization": f"Bearer {reg.get_json()['token']}"
        },
        json={
            "current_password": "testpass123",
            "username_confirmation": "reusableaccount",
        },
    )

    response = client.post("/api/auth/register", json={
        "username": "reusableaccount",
        "password": "testpass123",
        "timezone": "America/New_York",
    })

    assert response.status_code == 201


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


def test_update_risk_breakeven_persists_to_profile(client):
    """Risk-based breakeven defaults off and persists when enabled."""
    reg = client.post("/api/auth/register", json={
        "username": "riskbreakevenuser",
        "password": "testpass123",
        "timezone": "America/New_York",
    })
    token = reg.get_json()["token"]
    headers = {"Authorization": f"Bearer {token}"}

    profile_response = client.get(
        "/api/auth/me", headers=headers
    )
    assert profile_response.get_json()["risk_breakeven_enabled"] is False
    assert profile_response.get_json()["risk_breakeven_r_threshold"] == 0.05

    response = client.put(
        "/api/auth/risk-breakeven",
        json={
            "risk_breakeven_enabled": True,
            "risk_breakeven_r_threshold": 0.1,
        },
        headers=headers,
    )
    assert response.status_code == 200
    assert response.get_json()["risk_breakeven_enabled"] is True
    assert response.get_json()["risk_breakeven_r_threshold"] == 0.1

    profile_response = client.get(
        "/api/auth/me", headers=headers
    )
    assert profile_response.get_json()["risk_breakeven_enabled"] is True
    assert profile_response.get_json()["risk_breakeven_r_threshold"] == 0.1


def test_update_risk_breakeven_rejects_negative_threshold(client):
    """Risk breakeven thresholds cannot be negative."""
    reg = client.post("/api/auth/register", json={
        "username": "riskbreakevenvalidation",
        "password": "testpass123",
        "timezone": "America/New_York",
    })
    headers = {"Authorization": f"Bearer {reg.get_json()['token']}"}

    response = client.put(
        "/api/auth/risk-breakeven",
        json={
            "risk_breakeven_enabled": True,
            "risk_breakeven_r_threshold": -0.01,
        },
        headers=headers,
    )
    assert response.status_code == 400


def test_legacy_profile_defaults_to_disabled_threshold(app, client):
    """Profiles without the new threshold use safe legacy defaults."""
    reg = client.post("/api/auth/register", json={
        "username": "legacyriskbreakeven",
        "password": "testpass123",
        "timezone": "America/New_York",
    })
    token = reg.get_json()["token"]
    headers = {"Authorization": f"Bearer {token}"}

    with app.app_context():
        from app.extensions import mongo

        mongo.db.users.update_one(
            {"username": "legacyriskbreakeven"},
            {"$unset": {"risk_breakeven_r_threshold": ""}},
        )

    profile = client.get("/api/auth/me", headers=headers).get_json()
    assert profile["risk_breakeven_enabled"] is False
    assert profile["risk_breakeven_r_threshold"] == 0.05
