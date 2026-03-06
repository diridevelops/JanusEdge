"""Tests for import API routes."""

from io import BytesIO
from pathlib import Path

import pytest

from app import create_app
from app.whatif.cache import _sim_cache
from config import TestingConfig


EXAMPLES_DIR = (
    Path(__file__).resolve().parents[3] / "trade_examples"
)


@pytest.fixture
def app():
    """Create a test Flask application."""
    application = create_app(TestingConfig)
    yield application


@pytest.fixture
def client(app):
    """Create a Flask test client."""
    return app.test_client()


@pytest.fixture(autouse=True)
def clean_db(app):
    """Clean all collections before each test."""
    with app.app_context():
        from app.extensions import mongo

        for col in [
            "users",
            "trades",
            "executions",
            "trade_accounts",
            "tags",
            "market_data_cache",
            "import_batches",
            "audit_logs",
            "media",
        ]:
            mongo.db[col].delete_many({})
    _sim_cache.clear()
    yield
    _sim_cache.clear()


def _register_and_login(client):
    """Register a test user and return its token."""
    client.post(
        "/api/auth/register",
        json={
            "username": "importuser",
            "password": "TestPass123!",
            "timezone": "America/New_York",
        },
    )
    resp = client.post(
        "/api/auth/login",
        json={
            "username": "importuser",
            "password": "TestPass123!",
        },
    )
    return resp.get_json()["token"]


def _auth(token):
    """Build auth headers."""
    return {"Authorization": f"Bearer {token}"}


def _load_example_bytes(filename: str) -> bytes:
    """Load a sample CSV used by import route tests."""
    path = EXAMPLES_DIR / "NinjaTrader" / filename
    return path.read_bytes()


def _upload_reconstruct_finalize(
    client, token, filename: str
):
    """Run the full import flow for one CSV file."""
    content = _load_example_bytes(filename)
    upload_resp = client.post(
        "/api/imports/upload",
        data={
            "file": (BytesIO(content), filename),
        },
        headers=_auth(token),
        content_type="multipart/form-data",
    )
    assert upload_resp.status_code == 200
    upload_data = upload_resp.get_json()

    reconstruct_resp = client.post(
        "/api/imports/reconstruct",
        json={
            "executions": upload_data["executions"],
            "method": "FIFO",
        },
        headers=_auth(token),
    )
    assert reconstruct_resp.status_code == 200
    trades = reconstruct_resp.get_json()["trades"]

    finalize_resp = client.post(
        "/api/imports/finalize",
        json={
            "file_hash": upload_data["file_hash"],
            "platform": upload_data["platform"],
            "file_name": upload_data["file_name"],
            "file_size": upload_data["file_size"],
            "reconstruction_method": "FIFO",
            "trades": [
                {
                    "index": trade["index"],
                    "fee": 0.0,
                    "initial_risk": 0.0,
                }
                for trade in trades
            ],
            "executions": upload_data["executions"],
            "column_mapping": upload_data["column_mapping"],
        },
        headers=_auth(token),
    )
    assert finalize_resp.status_code == 201
    return finalize_resp.get_json()


def test_finalize_clears_whatif_cache(client):
    """Import finalization invalidates stale What-if cache."""
    token = _register_and_login(client)
    _sim_cache["stale"] = (0.0, {"cached": True})

    _upload_reconstruct_finalize(
        client,
        token,
        "NinjaTrader Grid example1.csv",
    )

    assert _sim_cache == {}


def test_reimport_after_deleting_all_imported_trades(client):
    """A file can be re-imported after all of its trades are deleted."""
    token = _register_and_login(client)

    first = _upload_reconstruct_finalize(
        client,
        token,
        "NinjaTrader Grid example1.csv",
    )
    assert first["trades_imported"] > 0

    trades_resp = client.get(
        "/api/trades",
        headers=_auth(token),
    )
    trade_ids = [
        trade["id"]
        for trade in trades_resp.get_json()["trades"]
    ]
    assert trade_ids

    for trade_id in trade_ids:
        delete_resp = client.delete(
            f"/api/trades/{trade_id}",
            headers=_auth(token),
        )
        assert delete_resp.status_code == 200

    second = _upload_reconstruct_finalize(
        client,
        token,
        "NinjaTrader Grid example1.csv",
    )
    assert second["trades_imported"] == first["trades_imported"]