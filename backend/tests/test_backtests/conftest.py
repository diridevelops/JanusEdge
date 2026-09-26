"""Isolated MongoDB fixtures for backtest tests."""

import flask_pymongo
import mongomock
import pytest

from app import create_app
from config import TestingConfig


@pytest.fixture
def app(patch_minio, monkeypatch):
    """Create the test app with an in-memory MongoDB instance."""
    monkeypatch.setattr(
        flask_pymongo, "MongoClient", mongomock.MongoClient
    )
    return create_app(TestingConfig)


@pytest.fixture
def client(app):
    """Return a Flask test client."""
    return app.test_client()


@pytest.fixture(autouse=True)
def clean_backtest_collections(app):
    """Keep backtest and auth records isolated between tests."""
    from app.extensions import mongo

    with app.app_context():
        for name in (
            "users",
            "auth_refresh_sessions",
            "backtest_runs",
            "backtest_chart_tabs",
            "backtest_chart_workspaces",
            "backtest_preparation_jobs",
            "backtest_notices",
            "trade_accounts",
        ):
            mongo.db[name].delete_many({})
