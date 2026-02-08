"""Pytest fixtures for TradeLogs tests."""

import pytest

from app import create_app
from config import TestingConfig


@pytest.fixture
def app():
    """Create a test Flask application."""
    application = create_app(TestingConfig)
    yield application


@pytest.fixture
def client(app):
    """Create a Flask test client."""
    return app.test_client()
