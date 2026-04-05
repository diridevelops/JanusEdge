"""Tests for public client-config routes."""

from app.client_config.service import build_client_config
from app.imports.config import (
    TRADE_IMPORT_ACCEPTED_EXTENSIONS,
    TRADE_IMPORT_ACCEPTED_MIME_TYPES,
)
from app.market_data.config import (
    MARKET_DATA_ACCEPTED_EXTENSIONS,
    MARKET_DATA_ACCEPTED_MIME_TYPES,
)
from app.media.service import (
    MEDIA_ACCEPTED_EXTENSIONS,
    MEDIA_ACCEPTED_MIME_TYPES,
)
from app.utils import upload_limits


def test_get_client_config_is_public(client):
    """The client-config endpoint is available without auth."""

    response = client.get("/api/client-config")

    assert response.status_code == 200


def test_get_client_config_returns_backend_upload_rules(
    client,
):
    """The endpoint reports the backend upload limits and formats."""

    response = client.get("/api/client-config")

    assert response.status_code == 200
    payload = response.get_json()
    uploads = payload["uploads"]

    assert payload == build_client_config()
    assert uploads["market_data"] == {
        "max_size_bytes": upload_limits.MARKET_DATA_MAX_FILE_SIZE,
        "max_size_label": upload_limits.format_upload_limit(
            upload_limits.MARKET_DATA_MAX_FILE_SIZE
        ),
        "accepted_extensions": list(
            MARKET_DATA_ACCEPTED_EXTENSIONS
        ),
        "accepted_mime_types": list(
            MARKET_DATA_ACCEPTED_MIME_TYPES
        ),
    }
    assert uploads["trade_import"] == {
        "max_size_bytes": upload_limits.CSV_IMPORT_MAX_FILE_SIZE,
        "max_size_label": upload_limits.format_upload_limit(
            upload_limits.CSV_IMPORT_MAX_FILE_SIZE
        ),
        "accepted_extensions": list(
            TRADE_IMPORT_ACCEPTED_EXTENSIONS
        ),
        "accepted_mime_types": list(
            TRADE_IMPORT_ACCEPTED_MIME_TYPES
        ),
    }
    assert uploads["media"] == {
        "max_size_bytes": upload_limits.MEDIA_MAX_FILE_SIZE,
        "max_size_label": upload_limits.format_upload_limit(
            upload_limits.MEDIA_MAX_FILE_SIZE
        ),
        "accepted_extensions": list(
            MEDIA_ACCEPTED_EXTENSIONS
        ),
        "accepted_mime_types": list(
            MEDIA_ACCEPTED_MIME_TYPES
        ),
    }
