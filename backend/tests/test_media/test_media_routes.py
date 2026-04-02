"""Tests for media attachment routes and service layer."""

from io import BytesIO
from uuid import uuid4

import pytest

import app.storage as storage_module
from app import create_app
from config import TestingConfig


# ── fixtures ─────────────────────────────────────────


@pytest.fixture
def app(patch_minio):
    """Create a test Flask application with shared MinIO stub."""
    application = create_app(TestingConfig)
    application._minio_mock = storage_module.get_client()
    application._public_minio_mock = (
        storage_module.get_public_client()
    )
    yield application


@pytest.fixture
def client(app):
    """Create a Flask test client."""
    return app.test_client()


@pytest.fixture(autouse=True)
def clean_db(app):
    """Clean relevant collections before each test."""
    with app.app_context():
        from app.extensions import mongo

        for col in [
            "users", "trades", "executions",
            "trade_accounts", "media",
        ]:
            mongo.db[col].delete_many({})
    yield


def _register_and_login(client):
    """Helper: register a user and return JWT token."""
    username = f"mediauser-{uuid4().hex[:8]}"
    client.post(
        "/api/auth/register",
        json={
            "username": username,
            "password": "TestPass123!",
            "timezone": "America/New_York",
        },
    )
    resp = client.post(
        "/api/auth/login",
        json={
            "username": username,
            "password": "TestPass123!",
        },
    )
    return resp.get_json()["token"]


def _auth(token):
    """Return an Authorization header dict."""
    return {"Authorization": f"Bearer {token}"}


def _create_trade(client, token):
    """Create a trade and return its ID."""
    resp = client.post(
        "/api/trades",
        json={
            "symbol": "MES",
            "side": "Long",
            "total_quantity": 1,
            "entry_price": 5000.0,
            "exit_price": 5010.0,
            "entry_time": "2026-01-01T10:00:00",
            "exit_time": "2026-01-01T10:05:00",
        },
        headers=_auth(token),
    )
    assert resp.status_code == 201
    return resp.get_json()["trade"]["id"]


def _upload_file(
    client,
    token,
    trade_id,
    filename="test.png",
    content_type="image/png",
    data=b"fakepngdata",
):
    """Upload a file via multipart and return response."""
    return client.post(
        f"/api/trades/{trade_id}/media",
        headers=_auth(token),
        data={
            "file": (BytesIO(data), filename, content_type),
        },
        content_type="multipart/form-data",
    )


# ── upload tests ─────────────────────────────────────


class TestUploadMedia:
    """Tests for POST /api/trades/<id>/media."""

    def test_upload_image_png(self, client, app):
        """Upload a PNG image succeeds."""
        token = _register_and_login(client)
        trade_id = _create_trade(client, token)

        resp = _upload_file(
            client, token, trade_id,
            filename="chart.png",
            content_type="image/png",
        )
        assert resp.status_code == 201
        media = resp.get_json()["media"]
        assert media["original_filename"] == "chart.png"
        assert media["content_type"] == "image/png"
        assert media["media_type"] == "image"
        assert media["trade_id"] == trade_id
        assert "id" in media

        # Verify MinIO put_object was called
        app._minio_mock.put_object.assert_called_once()

    def test_upload_image_jpeg(self, client, app):
        """Upload a JPEG image succeeds."""
        token = _register_and_login(client)
        trade_id = _create_trade(client, token)

        resp = _upload_file(
            client, token, trade_id,
            filename="photo.jpg",
            content_type="image/jpeg",
        )
        assert resp.status_code == 201
        assert resp.get_json()["media"]["media_type"] \
            == "image"

    def test_upload_image_gif(self, client, app):
        """Upload a GIF image succeeds."""
        token = _register_and_login(client)
        trade_id = _create_trade(client, token)

        resp = _upload_file(
            client, token, trade_id,
            filename="anim.gif",
            content_type="image/gif",
        )
        assert resp.status_code == 201
        assert resp.get_json()["media"]["media_type"] \
            == "image"

    def test_upload_image_webp(self, client, app):
        """Upload a WebP image succeeds."""
        token = _register_and_login(client)
        trade_id = _create_trade(client, token)

        resp = _upload_file(
            client, token, trade_id,
            filename="img.webp",
            content_type="image/webp",
        )
        assert resp.status_code == 201
        assert resp.get_json()["media"]["media_type"] \
            == "image"

    def test_upload_video_mp4(self, client, app):
        """Upload an MP4 video succeeds."""
        token = _register_and_login(client)
        trade_id = _create_trade(client, token)

        resp = _upload_file(
            client, token, trade_id,
            filename="replay.mp4",
            content_type="video/mp4",
        )
        assert resp.status_code == 201
        media = resp.get_json()["media"]
        assert media["media_type"] == "video"
        assert media["content_type"] == "video/mp4"

    def test_upload_video_webm(self, client, app):
        """Upload a WebM video succeeds."""
        token = _register_and_login(client)
        trade_id = _create_trade(client, token)

        resp = _upload_file(
            client, token, trade_id,
            filename="clip.webm",
            content_type="video/webm",
        )
        assert resp.status_code == 201
        assert resp.get_json()["media"]["media_type"] \
            == "video"

    def test_upload_video_quicktime(self, client, app):
        """Upload a QuickTime/MOV video succeeds."""
        token = _register_and_login(client)
        trade_id = _create_trade(client, token)

        resp = _upload_file(
            client, token, trade_id,
            filename="screen.mov",
            content_type="video/quicktime",
        )
        assert resp.status_code == 201
        assert resp.get_json()["media"]["media_type"] \
            == "video"

    def test_upload_video_mkv_rejected(self, client):
        """MKV files are not supported and return 400."""
        token = _register_and_login(client)
        trade_id = _create_trade(client, token)

        resp = _upload_file(
            client, token, trade_id,
            filename="recording.mkv",
            content_type="video/x-matroska",
        )
        assert resp.status_code == 400
        body = resp.get_json()
        assert "Unsupported file type" \
            in body["error"]["message"]

    def test_upload_unsupported_type_rejected(
        self, client
    ):
        """Unsupported MIME type returns 400."""
        token = _register_and_login(client)
        trade_id = _create_trade(client, token)

        resp = _upload_file(
            client, token, trade_id,
            filename="doc.pdf",
            content_type="application/pdf",
        )
        assert resp.status_code == 400
        body = resp.get_json()
        assert "Unsupported file type" \
            in body["error"]["message"]

    def test_upload_no_file_returns_400(self, client):
        """Missing file part returns 400."""
        token = _register_and_login(client)
        trade_id = _create_trade(client, token)

        resp = client.post(
            f"/api/trades/{trade_id}/media",
            headers=_auth(token),
            data={},
            content_type="multipart/form-data",
        )
        assert resp.status_code == 400

    def test_upload_requires_auth(self, client):
        """Upload without token returns 401."""
        resp = client.post(
            "/api/trades/fakeid/media",
            data={},
            content_type="multipart/form-data",
        )
        assert resp.status_code == 401

    def test_upload_wrong_trade_returns_404(
        self, client
    ):
        """Upload to non-existent trade returns 404."""
        token = _register_and_login(client)
        from bson import ObjectId

        fake_id = str(ObjectId())
        resp = _upload_file(
            client, token, fake_id,
        )
        assert resp.status_code == 404

    def test_upload_stores_correct_size(
        self, client, app
    ):
        """File size is stored correctly in metadata."""
        token = _register_and_login(client)
        trade_id = _create_trade(client, token)

        payload = b"x" * 1024
        resp = _upload_file(
            client, token, trade_id,
            data=payload,
        )
        assert resp.status_code == 201
        assert resp.get_json()["media"]["size_bytes"] \
            == 1024


# ── list tests ───────────────────────────────────────


class TestListMedia:
    """Tests for GET /api/trades/<id>/media."""

    def test_list_empty(self, client):
        """Empty trade returns empty list."""
        token = _register_and_login(client)
        trade_id = _create_trade(client, token)

        resp = client.get(
            f"/api/trades/{trade_id}/media",
            headers=_auth(token),
        )
        assert resp.status_code == 200
        assert resp.get_json()["media"] == []

    def test_list_after_upload(self, client, app):
        """Uploaded items appear in the list."""
        token = _register_and_login(client)
        trade_id = _create_trade(client, token)

        _upload_file(
            client, token, trade_id,
            filename="a.png", content_type="image/png",
        )
        _upload_file(
            client, token, trade_id,
            filename="b.mp4", content_type="video/mp4",
        )

        resp = client.get(
            f"/api/trades/{trade_id}/media",
            headers=_auth(token),
        )
        assert resp.status_code == 200
        items = resp.get_json()["media"]
        assert len(items) == 2
        names = {m["original_filename"] for m in items}
        assert names == {"a.png", "b.mp4"}

    def test_list_requires_auth(self, client):
        """Listing without token returns 401."""
        resp = client.get(
            "/api/trades/fakeid/media",
        )
        assert resp.status_code == 401

    def test_list_wrong_trade_returns_404(self, client):
        """Listing for non-existent trade returns 404."""
        token = _register_and_login(client)
        from bson import ObjectId

        fake_id = str(ObjectId())
        resp = client.get(
            f"/api/trades/{fake_id}/media",
            headers=_auth(token),
        )
        assert resp.status_code == 404


# ── presigned URL tests ──────────────────────────────


class TestGetMediaUrl:
    """Tests for GET /api/media/<id>/url."""

    def test_get_url_returns_presigned(
        self, client, app
    ):
        """Get URL uses the public MinIO client for browser access."""
        app._public_minio_mock.presigned_get_object.side_effect = (
            lambda *args, **kwargs: (
                "http://localhost:9000/signed"
                "?X-Amz-Signature=testsig"
            )
        )

        token = _register_and_login(client)
        trade_id = _create_trade(client, token)

        upload_resp = _upload_file(
            client, token, trade_id,
        )
        media_id = upload_resp.get_json()["media"]["id"]

        resp = client.get(
            f"/api/media/{media_id}/url",
            headers=_auth(token),
        )
        assert resp.status_code == 200
        assert resp.get_json()["url"] \
            == (
                "http://localhost:9000/signed"
                "?X-Amz-Signature=testsig"
            )

    def test_get_url_preserves_original_when_public_url_invalid(
        self, client, app
    ):
        """Invalid public URL falls back to the internal client."""
        storage_module._public_client = app._minio_mock
        app._minio_mock.presigned_get_object.side_effect = (
            lambda *args, **kwargs: (
                "http://minio:9000/signed"
                "?X-Amz-Signature=testsig"
            )
        )

        token = _register_and_login(client)
        trade_id = _create_trade(client, token)

        upload_resp = _upload_file(
            client, token, trade_id,
        )
        media_id = upload_resp.get_json()["media"]["id"]

        resp = client.get(
            f"/api/media/{media_id}/url",
            headers=_auth(token),
        )
        assert resp.status_code == 200
        assert resp.get_json()["url"] \
            == (
                "http://minio:9000/signed"
                "?X-Amz-Signature=testsig"
            )

    def test_get_url_nonexistent_returns_404(
        self, client
    ):
        """Requesting URL for unknown media returns 404."""
        token = _register_and_login(client)
        from bson import ObjectId

        fake_id = str(ObjectId())
        resp = client.get(
            f"/api/media/{fake_id}/url",
            headers=_auth(token),
        )
        assert resp.status_code == 404

    def test_get_url_requires_auth(self, client):
        """URL request without token returns 401."""
        resp = client.get("/api/media/fakeid/url")
        assert resp.status_code == 401


# ── delete tests ─────────────────────────────────────


class TestDeleteMedia:
    """Tests for DELETE /api/media/<id>."""

    def test_delete_removes_from_db(self, client, app):
        """Delete removes the media record."""
        token = _register_and_login(client)
        trade_id = _create_trade(client, token)

        upload_resp = _upload_file(
            client, token, trade_id,
        )
        media_id = upload_resp.get_json()["media"]["id"]

        resp = client.delete(
            f"/api/media/{media_id}",
            headers=_auth(token),
        )
        assert resp.status_code == 200
        assert "deleted" in resp.get_json()["message"]\
            .lower()

        # Verify MinIO remove_object was called
        app._minio_mock.remove_object.assert_called_once()

        # Listing should now be empty
        list_resp = client.get(
            f"/api/trades/{trade_id}/media",
            headers=_auth(token),
        )
        assert list_resp.get_json()["media"] == []

    def test_delete_nonexistent_returns_404(
        self, client
    ):
        """Deleting unknown media returns 404."""
        token = _register_and_login(client)
        from bson import ObjectId

        fake_id = str(ObjectId())
        resp = client.delete(
            f"/api/media/{fake_id}",
            headers=_auth(token),
        )
        assert resp.status_code == 404

    def test_delete_requires_auth(self, client):
        """Delete without token returns 401."""
        resp = client.delete("/api/media/fakeid")
        assert resp.status_code == 401


# ── cross-user isolation ─────────────────────────────


class TestMediaIsolation:
    """Ensure one user cannot access another's media."""

    def _register_user(self, client, username):
        """Register and login a unique user."""
        client.post(
            "/api/auth/register",
            json={
                "username": username,
                "password": "TestPass123!",
                "timezone": "UTC",
            },
        )
        resp = client.post(
            "/api/auth/login",
            json={
                "username": username,
                "password": "TestPass123!",
            },
        )
        return resp.get_json()["token"]

    def test_cannot_list_others_media(
        self, client, app
    ):
        """User B cannot list media on User A's trade."""
        token_a = self._register_user(
            client, "userA"
        )
        token_b = self._register_user(
            client, "userB"
        )

        trade_id = _create_trade(client, token_a)
        _upload_file(client, token_a, trade_id)

        # User B tries to list media on A's trade
        resp = client.get(
            f"/api/trades/{trade_id}/media",
            headers=_auth(token_b),
        )
        assert resp.status_code == 404

    def test_cannot_delete_others_media(
        self, client, app
    ):
        """User B cannot delete User A's attachment."""
        token_a = self._register_user(
            client, "userC"
        )
        token_b = self._register_user(
            client, "userD"
        )

        trade_id = _create_trade(client, token_a)
        upload_resp = _upload_file(
            client, token_a, trade_id,
        )
        media_id = upload_resp.get_json()["media"]["id"]

        resp = client.delete(
            f"/api/media/{media_id}",
            headers=_auth(token_b),
        )
        assert resp.status_code == 404


# ── service unit tests ───────────────────────────────


class TestMediaServiceUnit:
    """Unit tests for the MediaService class."""

    def test_object_key_format(self, app):
        """Object key follows the expected pattern."""
        with app.app_context():
            from app.media.service import MediaService

            svc = MediaService()
            key = svc._object_key(
                "uid1", "tid2", "my file.png",
            )
            assert key.startswith("uid1/tid2/")
            assert "my file.png" in key

    def test_object_key_sanitises_slashes(self, app):
        """Forward and back slashes in filenames are
        replaced with underscores."""
        with app.app_context():
            from app.media.service import MediaService

            svc = MediaService()
            key = svc._object_key(
                "u", "t", "path/to\\file.jpg",
            )
            assert "/" not in key.split("/", 2)[2] \
                or "_" in key
            # The filename portion should not contain
            # raw slashes
            fname_part = key.split("/", 2)[2]
            # After the uuid_ prefix, check the filename
            after_uuid = fname_part.split("_", 1)[1]
            assert "\\" not in after_uuid
            assert "/" not in after_uuid

    def test_allowed_types_excludes_mkv(self, app):
        """ALLOWED_TYPES dict does not include MKV."""
        with app.app_context():
            from app.media.service import ALLOWED_TYPES

            assert "video/x-matroska" not in ALLOWED_TYPES

    def test_allowed_types_count(self, app):
        """All 7 expected MIME types are present."""
        with app.app_context():
            from app.media.service import ALLOWED_TYPES

            assert len(ALLOWED_TYPES) == 7
            expected = {
                "image/jpeg", "image/png", "image/gif",
                "image/webp", "video/mp4", "video/webm",
                "video/quicktime",
            }
            assert set(ALLOWED_TYPES.keys()) == expected
