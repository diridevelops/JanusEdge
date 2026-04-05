"""Build app config payloads consumed by the frontend."""

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


def _build_upload_rule(
    *,
    max_size_bytes: int,
    accepted_extensions: tuple[str, ...],
    accepted_mime_types: tuple[str, ...],
) -> dict:
    """Return one upload-rule payload."""

    return {
        "max_size_bytes": max_size_bytes,
        "max_size_label": upload_limits.format_upload_limit(
            max_size_bytes
        ),
        "accepted_extensions": list(accepted_extensions),
        "accepted_mime_types": list(accepted_mime_types),
    }


def build_client_config() -> dict:
    """Return the public client config payload."""

    return {
        "uploads": {
            "market_data": _build_upload_rule(
                max_size_bytes=upload_limits.MARKET_DATA_MAX_FILE_SIZE,
                accepted_extensions=MARKET_DATA_ACCEPTED_EXTENSIONS,
                accepted_mime_types=MARKET_DATA_ACCEPTED_MIME_TYPES,
            ),
            "trade_import": _build_upload_rule(
                max_size_bytes=upload_limits.CSV_IMPORT_MAX_FILE_SIZE,
                accepted_extensions=TRADE_IMPORT_ACCEPTED_EXTENSIONS,
                accepted_mime_types=TRADE_IMPORT_ACCEPTED_MIME_TYPES,
            ),
            "media": _build_upload_rule(
                max_size_bytes=upload_limits.MEDIA_MAX_FILE_SIZE,
                accepted_extensions=MEDIA_ACCEPTED_EXTENSIONS,
                accepted_mime_types=MEDIA_ACCEPTED_MIME_TYPES,
            ),
        }
    }
