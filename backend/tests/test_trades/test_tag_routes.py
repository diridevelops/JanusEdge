"""Tests for tag API routes."""

import pytest

from app import create_app
from config import TestingConfig


@pytest.fixture
def app(patch_minio):
    application = create_app(TestingConfig)
    yield application


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture(autouse=True)
def clean_db(app):
    """Clean all collections before each test."""
    with app.app_context():
        from app.extensions import mongo

        for col in ["users", "tags", "trades"]:
            mongo.db[col].delete_many({})
    yield


def _register_and_login(client):
    client.post(
        "/api/auth/register",
        json={
            "username": "taguser",
            "password": "TestPass123!",
            "timezone": "America/New_York",
        },
    )
    resp = client.post(
        "/api/auth/login",
        json={
            "username": "taguser",
            "password": "TestPass123!",
        },
    )
    return resp.get_json()["token"]


def _auth_header(token):
    return {"Authorization": f"Bearer {token}"}


def test_create_tag(client):
    token = _register_and_login(client)
    resp = client.post(
        "/api/tags",
        json={"name": "Breakout", "color": "#FF0000"},
        headers=_auth_header(token),
    )
    assert resp.status_code == 201
    tag = resp.get_json()["tag"]
    assert tag["name"] == "Breakout"
    assert tag["color"] == "#FF0000"


def test_list_tags(client):
    token = _register_and_login(client)
    client.post(
        "/api/tags",
        json={"name": "Tag1"},
        headers=_auth_header(token),
    )
    client.post(
        "/api/tags",
        json={"name": "Tag2"},
        headers=_auth_header(token),
    )
    resp = client.get(
        "/api/tags",
        headers=_auth_header(token),
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert len(data["tags"]) == 2


def test_duplicate_tag_rejected(client):
    token = _register_and_login(client)
    client.post(
        "/api/tags",
        json={"name": "Duplicate"},
        headers=_auth_header(token),
    )
    resp = client.post(
        "/api/tags",
        json={"name": "Duplicate"},
        headers=_auth_header(token),
    )
    assert resp.status_code == 400


def test_delete_tag(client):
    token = _register_and_login(client)
    resp = client.post(
        "/api/tags",
        json={"name": "ToDelete"},
        headers=_auth_header(token),
    )
    tag_id = resp.get_json()["tag"]["id"]
    resp = client.delete(
        f"/api/tags/{tag_id}",
        headers=_auth_header(token),
    )
    assert resp.status_code == 200


def test_delete_tag_removes_it_from_owned_trades_only(client, app):
    """Deleting a tag pulls it from every current-user trade."""
    from bson import ObjectId
    from app.extensions import mongo

    token = _register_and_login(client)
    headers = _auth_header(token)
    deleted_tag = client.post(
        "/api/tags", json={"name": "Delete me"}, headers=headers
    ).get_json()["tag"]
    retained_tag = client.post(
        "/api/tags", json={"name": "Keep me"}, headers=headers
    ).get_json()["tag"]

    other_registration = client.post(
        "/api/auth/register",
        json={
            "username": "otheruser",
            "password": "TestPass123!",
            "timezone": "America/New_York",
        },
    )
    assert other_registration.status_code == 201

    with app.app_context():
        owner = mongo.db.users.find_one({"username": "taguser"})
        other = mongo.db.users.find_one({"username": "otheruser"})
        deleted_tag_id = ObjectId(deleted_tag["id"])
        retained_tag_id = ObjectId(retained_tag["id"])
        mongo.db.trades.insert_many([
            {
                "user_id": owner["_id"],
                "tag_ids": [deleted_tag_id, retained_tag_id],
            },
            {
                "user_id": owner["_id"],
                "tag_ids": [deleted_tag_id],
            },
            {
                "user_id": other["_id"],
                "tag_ids": [deleted_tag_id],
            },
        ])

    response = client.delete(
        f"/api/tags/{deleted_tag['id']}", headers=headers
    )
    assert response.status_code == 200
    assert response.get_json()["trades_updated"] == 2

    with app.app_context():
        owner_trades = list(
            mongo.db.trades.find({"user_id": owner["_id"]})
        )
        assert owner_trades[0]["tag_ids"] == [retained_tag_id]
        assert owner_trades[1]["tag_ids"] == []
        other_trade = mongo.db.trades.find_one(
            {"user_id": other["_id"]}
        )
        assert other_trade["tag_ids"] == [deleted_tag_id]
        assert mongo.db.tags.find_one({"_id": deleted_tag_id}) is None
