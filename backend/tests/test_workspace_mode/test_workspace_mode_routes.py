"""Tests for the authenticated workspace-mode API."""

import pytest

from app.extensions import mongo


@pytest.fixture(autouse=True)
def clean_db(app):
    """Clear user and mode documents used by these tests."""
    with app.app_context():
        mongo.db.users.delete_many({})
        mongo.db.workspace_modes.delete_many({})


def _register(client, username):
    """Create a user and return an authorization header."""
    response = client.post(
        "/api/auth/register",
        json={
            "username": username,
            "password": "TestPass123!",
            "timezone": "America/New_York",
        },
    )
    assert response.status_code == 201
    login = client.post(
        "/api/auth/login",
        json={
            "username": username,
            "password": "TestPass123!",
        },
    )
    assert login.status_code == 200
    return {"Authorization": f"Bearer {login.json['token']}"}


def test_workspace_mode_requires_authentication(client):
    response = client.get("/api/workspace/mode")

    assert response.status_code == 401


def test_workspace_mode_defaults_to_real_and_persists_per_user(
    client,
):
    first_user = _register(client, "workspace-first")
    second_user = _register(client, "workspace-second")

    first_initial = client.get(
        "/api/workspace/mode", headers=first_user
    )
    second_initial = client.get(
        "/api/workspace/mode", headers=second_user
    )
    assert first_initial.status_code == 200
    assert first_initial.json == {"active_mode": "real"}
    assert second_initial.status_code == 200
    assert second_initial.json == {"active_mode": "real"}

    updated = client.put(
        "/api/workspace/mode",
        json={"active_mode": "backtest"},
        headers=first_user,
    )
    assert updated.status_code == 200
    assert updated.json == {"active_mode": "backtest"}

    first_reload = client.get(
        "/api/workspace/mode", headers=first_user
    )
    second_unchanged = client.get(
        "/api/workspace/mode", headers=second_user
    )
    assert first_reload.json == {"active_mode": "backtest"}
    assert second_unchanged.json == {"active_mode": "real"}


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"active_mode": "paper"},
        {"active_mode": "BACKTEST"},
        {"active_mode": None},
    ],
)
def test_workspace_mode_rejects_invalid_values(client, payload):
    headers = _register(client, "workspace-invalid")

    response = client.put(
        "/api/workspace/mode", json=payload, headers=headers
    )

    assert response.status_code == 400
    assert response.json["error"]["code"] == "VALIDATIONERROR"


def test_workspace_mode_uses_authenticated_owner_not_body_user_id(
    client,
    app,
):
    first_user = _register(client, "workspace-owner")
    second_user = _register(client, "workspace-other")
    with app.app_context():
        other_id = str(
            mongo.db.users.find_one(
                {"username": "workspace-other"}
            )["_id"]
        )

    response = client.put(
        "/api/workspace/mode",
        json={"active_mode": "backtest", "user_id": other_id},
        headers=first_user,
    )

    assert response.status_code == 200
    assert client.get(
        "/api/workspace/mode", headers=first_user
    ).json == {"active_mode": "backtest"}
    assert client.get(
        "/api/workspace/mode", headers=second_user
    ).json == {"active_mode": "real"}
