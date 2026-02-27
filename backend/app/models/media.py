"""Media attachment model definition."""

from app.utils.datetime_utils import utc_now


def create_media_doc(
    user_id,
    trade_id,
    object_key: str,
    original_filename: str,
    content_type: str,
    size_bytes: int,
    media_type: str,
) -> dict:
    """
    Create a media-attachment document for MongoDB.

    Parameters:
        user_id: ObjectId of the owning user.
        trade_id: ObjectId of the related trade.
        object_key: Key (path) in the MinIO bucket.
        original_filename: Name of the uploaded file.
        content_type: MIME type (e.g. image/png).
        size_bytes: File size in bytes.
        media_type: 'image' or 'video'.

    Returns:
        Dict ready for MongoDB insert.
    """
    now = utc_now()
    return {
        "user_id": user_id,
        "trade_id": trade_id,
        "object_key": object_key,
        "original_filename": original_filename,
        "content_type": content_type,
        "size_bytes": size_bytes,
        "media_type": media_type,
        "created_at": now,
    }
