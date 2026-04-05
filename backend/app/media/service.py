"""Media attachment service - business logic."""

import logging
import uuid
from datetime import timedelta
from io import BytesIO
from typing import Dict, List

from bson import ObjectId

from app.models.media import create_media_doc
from app.repositories.media_repo import MediaRepository
from app.repositories.trade_repo import TradeRepository
from app.storage import (
    get_bucket,
    get_client,
    get_public_client,
)
from app.utils.errors import NotFoundError, ValidationError

logger = logging.getLogger(__name__)

MEDIA_ACCEPTED_EXTENSIONS = (
    ".jpg",
    ".jpeg",
    ".png",
    ".gif",
    ".webp",
    ".mp4",
    ".webm",
    ".mov",
)

# Allowed MIME types and the category they map to.
ALLOWED_TYPES: Dict[str, str] = {
    "image/jpeg": "image",
    "image/png": "image",
    "image/gif": "image",
    "image/webp": "image",
    "video/mp4": "video",
    "video/webm": "video",
    "video/quicktime": "video",
}
MEDIA_ACCEPTED_MIME_TYPES = tuple(ALLOWED_TYPES.keys())

MAX_FILE_SIZE = 500 * 1024 * 1024  # 500 MB
MAX_ATTACHMENTS_PER_TRADE = 20
PRESIGNED_URL_EXPIRY = timedelta(hours=1)


class MediaService:
    """Handles upload, listing, presigned URLs, and deletion."""

    def __init__(self) -> None:
        self.media_repo = MediaRepository()
        self.trade_repo = TradeRepository()

    def _verify_trade_ownership(
        self, user_id: str, trade_id: str
    ) -> Dict:
        """
        Ensure the trade exists and belongs to the user.

        Parameters:
            user_id: Owning user ObjectId string.
            trade_id: Trade ObjectId string.

        Returns:
            The trade document.

        Raises:
            NotFoundError: If not found / not owned.
        """

        trade = self.trade_repo.find_one(
            {
                "_id": ObjectId(trade_id),
                "user_id": ObjectId(user_id),
            }
        )
        if not trade:
            raise NotFoundError("Trade not found.")
        return trade

    @staticmethod
    def _object_key(
        user_id: str, trade_id: str, filename: str
    ) -> str:
        """
        Build a unique object key in the bucket.

        Format: ``<user_id>/<trade_id>/<uuid>_<filename>``.
        """

        safe = filename.replace("/", "_").replace(
            "\\", "_"
        )
        uid = uuid.uuid4().hex[:12]
        return f"{user_id}/{trade_id}/{uid}_{safe}"

    def upload(
        self,
        user_id: str,
        trade_id: str,
        file_storage,
    ) -> Dict:
        """
        Upload a media file to MinIO and record it in the DB.

        Parameters:
            user_id: Owning user ObjectId string.
            trade_id: Trade ObjectId string.
            file_storage: Werkzeug ``FileStorage`` from
                the request.

        Returns:
            Serialized media document.

        Raises:
            ValidationError: On bad input.
            NotFoundError: If trade not owned.
        """

        self._verify_trade_ownership(user_id, trade_id)

        if not file_storage or not file_storage.filename:
            raise ValidationError("No file provided.")

        content_type = (
            file_storage.content_type or ""
        ).lower()
        media_type = ALLOWED_TYPES.get(content_type)
        if not media_type:
            raise ValidationError(
                f"Unsupported file type: {content_type}. "
                "Allowed: "
                + ", ".join(sorted(ALLOWED_TYPES))
            )

        data = file_storage.read()
        size = len(data)
        if size > MAX_FILE_SIZE:
            raise ValidationError(
                "File exceeds the 500 MB limit."
            )

        existing = self.media_repo.count_for_trade(
            user_id, trade_id
        )
        if existing >= MAX_ATTACHMENTS_PER_TRADE:
            raise ValidationError(
                f"Maximum {MAX_ATTACHMENTS_PER_TRADE} "
                "attachments per trade."
            )

        key = self._object_key(
            user_id, trade_id, file_storage.filename
        )

        client = get_client()
        bucket = get_bucket()
        client.put_object(
            bucket,
            key,
            BytesIO(data),
            length=size,
            content_type=content_type,
        )

        doc = create_media_doc(
            user_id=ObjectId(user_id),
            trade_id=ObjectId(trade_id),
            object_key=key,
            original_filename=file_storage.filename,
            content_type=content_type,
            size_bytes=size,
            media_type=media_type,
        )
        doc_id = self.media_repo.insert_one(doc)
        doc["_id"] = ObjectId(doc_id)

        return self.media_repo.serialize_doc(doc)

    def list_for_trade(
        self, user_id: str, trade_id: str
    ) -> List[Dict]:
        """
        List all media attachments for a trade.

        Parameters:
            user_id: Owning user ObjectId string.
            trade_id: Trade ObjectId string.

        Returns:
            List of serialized media documents.
        """

        self._verify_trade_ownership(user_id, trade_id)
        docs = self.media_repo.find_by_trade(
            user_id, trade_id
        )
        return [
            self.media_repo.serialize_doc(d) for d in docs
        ]

    def get_presigned_url(
        self, user_id: str, media_id: str
    ) -> str:
        """
        Generate a presigned GET URL for a media object.

        Parameters:
            user_id: Owning user ObjectId string.
            media_id: Media document ObjectId string.

        Returns:
            Presigned URL string.

        Raises:
            NotFoundError: If not found / not owned.
        """

        doc = self.media_repo.find_owned(
            user_id, media_id
        )
        if not doc:
            raise NotFoundError(
                "Media attachment not found."
            )

        client = get_public_client()
        bucket = get_bucket()
        return client.presigned_get_object(
            bucket,
            doc["object_key"],
            expires=PRESIGNED_URL_EXPIRY,
        )

    def delete(
        self, user_id: str, media_id: str
    ) -> None:
        """
        Delete a media attachment from MinIO and the DB.

        Parameters:
            user_id: Owning user ObjectId string.
            media_id: Media document ObjectId string.

        Raises:
            NotFoundError: If not found / not owned.
        """

        doc = self.media_repo.find_owned(
            user_id, media_id
        )
        if not doc:
            raise NotFoundError(
                "Media attachment not found."
            )

        try:
            client = get_client()
            bucket = get_bucket()
            client.remove_object(
                bucket, doc["object_key"]
            )
        except Exception:
            logger.warning(
                "Failed to remove object %s from MinIO",
                doc["object_key"],
                exc_info=True,
            )

        self.media_repo.delete_one(str(doc["_id"]))
