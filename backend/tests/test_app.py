"""Tests for application startup and health."""


def test_app_creates(app):
    """The app factory creates without error."""
    assert app is not None


def test_health_check(client):
    """The auth health endpoint responds."""
    response = client.get("/api/auth/health")
    assert response.status_code == 200
    assert response.json["status"] == "ok"
