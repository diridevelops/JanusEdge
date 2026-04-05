"""Shared upload size limits and helpers."""

from __future__ import annotations

import os

from werkzeug.datastructures import FileStorage

from app.utils.errors import ValidationError

MB = 1024 * 1024
GB = 1024 * MB

CSV_IMPORT_MAX_FILE_SIZE = 500 * MB
MEDIA_MAX_FILE_SIZE = 500 * MB
MARKET_DATA_MAX_FILE_SIZE = 1 * GB
GLOBAL_MAX_REQUEST_SIZE = MARKET_DATA_MAX_FILE_SIZE


def format_upload_limit(size_bytes: int) -> str:
    """Return a human-readable upload limit label."""

    if size_bytes % GB == 0:
        return f"{size_bytes // GB} GB"

    return f"{size_bytes // MB} MB"


def get_uploaded_file_size(
    file_storage: FileStorage,
) -> int | None:
    """Return the exact uploaded file size when the stream is seekable."""

    stream = getattr(file_storage, "stream", None)
    if stream is not None:
        try:
            current_position = stream.tell()
            stream.seek(0, os.SEEK_END)
            size_bytes = int(stream.tell())
            stream.seek(current_position, os.SEEK_SET)
            return size_bytes
        except (AttributeError, OSError, ValueError):
            pass

    content_length = getattr(file_storage, "content_length", None)
    if isinstance(content_length, int) and content_length >= 0:
        return content_length

    return None


def enforce_upload_file_size(
    file_storage: FileStorage,
    *,
    max_size_bytes: int,
    error_message: str,
) -> None:
    """Raise when an uploaded file exceeds the given size limit."""

    size_bytes = get_uploaded_file_size(file_storage)
    if size_bytes is not None and size_bytes > max_size_bytes:
        raise ValidationError(error_message)
