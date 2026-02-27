"""Media attachment repository."""

from typing import Dict, List

from bson import ObjectId

from app.repositories.base import BaseRepository


class MediaRepository(BaseRepository):
    """Repository for the ``media`` collection."""

    collection_name = "media"

    def find_by_trade(
        self, user_id: str, trade_id: str
    ) -> List[Dict]:
        """
        Return all media docs for a trade.

        Parameters:
            user_id: Owning user's ObjectId string.
            trade_id: Related trade's ObjectId string.

        Returns:
            List of media documents sorted by created_at.
        """
        return self.find_many(
            {
                "user_id": ObjectId(user_id),
                "trade_id": ObjectId(trade_id),
            },
            sort=[("created_at", 1)],
        )

    def find_owned(
        self, user_id: str, media_id: str
    ) -> Dict | None:
        """
        Fetch a single media doc owned by the user.

        Parameters:
            user_id: Owning user's ObjectId string.
            media_id: Media document's ObjectId string.

        Returns:
            The document dict or None.
        """
        return self.find_one(
            {
                "_id": ObjectId(media_id),
                "user_id": ObjectId(user_id),
            }
        )

    def count_for_trade(
        self, user_id: str, trade_id: str
    ) -> int:
        """
        Count how many attachments a trade already has.

        Parameters:
            user_id: Owning user's ObjectId string.
            trade_id: Related trade's ObjectId string.

        Returns:
            Attachment count.
        """
        return self.count(
            {
                "user_id": ObjectId(user_id),
                "trade_id": ObjectId(trade_id),
            }
        )
