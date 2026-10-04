"""Use an isolated in-memory MongoDB for workspace-mode tests."""

import mongomock
import pytest
import flask_pymongo

from app import create_app
from config import TestingConfig


@pytest.fixture
def app(patch_minio, monkeypatch):
    """Create the test app with mongomock instead of a local server."""
    monkeypatch.setattr(flask_pymongo, "MongoClient", mongomock.MongoClient)
    application = create_app(TestingConfig)
    yield application


@pytest.fixture
def client(app):
    """Return the Flask test client."""
    return app.test_client()
