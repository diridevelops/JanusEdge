"""Fixtures for market data tests."""

import pytest

from app import create_app
from config import TestingConfig


@pytest.fixture
def app():
    application = create_app(TestingConfig)
    yield application


@pytest.fixture(autouse=True)
def clean_db(app):
    with app.app_context():
        from app.extensions import mongo

        mongo.db.market_data_cache.delete_many({})
    yield
