"""Media attachment API routes."""

from flask import jsonify, request
from flask_jwt_extended import (
    get_jwt_identity,
    jwt_required,
)

from app.media import media_bp
from app.media.service import MediaService
from app.utils import upload_limits

media_service = MediaService()


def _media_file_too_large_message() -> str:
    """Return the current media oversize error message."""

    return (
        "File exceeds the "
        f"{upload_limits.format_upload_limit(upload_limits.MEDIA_MAX_FILE_SIZE)} "
        "limit."
    )


@media_bp.route(
    "/trades/<trade_id>/media", methods=["POST"]
)
@jwt_required()
def upload_media(trade_id: str):
    """
    Upload a media file for a trade.

    Expects multipart/form-data with a ``file`` part.
    """
    user_id = get_jwt_identity()
    file = request.files.get("file")
    if file and file.filename:
        upload_limits.enforce_upload_file_size(
            file,
            max_size_bytes=upload_limits.MEDIA_MAX_FILE_SIZE,
            error_message=_media_file_too_large_message(),
        )
    result = media_service.upload(
        user_id, trade_id, file
    )
    return jsonify({"media": result}), 201


@media_bp.route(
    "/trades/<trade_id>/media", methods=["GET"]
)
@jwt_required()
def list_media(trade_id: str):
    """List all media attachments for a trade."""
    user_id = get_jwt_identity()
    items = media_service.list_for_trade(
        user_id, trade_id
    )
    return jsonify({"media": items}), 200


@media_bp.route(
    "/media/<media_id>/url", methods=["GET"]
)
@jwt_required()
def get_media_url(media_id: str):
    """Return a presigned URL for downloading media."""
    user_id = get_jwt_identity()
    url = media_service.get_presigned_url(
        user_id, media_id
    )
    return jsonify({"url": url}), 200


@media_bp.route(
    "/media/<media_id>", methods=["DELETE"]
)
@jwt_required()
def delete_media(media_id: str):
    """Delete a media attachment."""
    user_id = get_jwt_identity()
    media_service.delete(user_id, media_id)
    return jsonify({"message": "Media deleted."}), 200
