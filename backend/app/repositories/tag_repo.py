"""Tag repository for database operations."""

from typing import List

from bson import ObjectId

from app.repositories.base import BaseRepository


class TagRepository(BaseRepository):
    """Repository for tags collection."""

    collection_name = "tags"

    def find_by_user(
        self, user_id: str
    ) -> List[dict]:
        """Find all tags for a user."""
        return self.find_many(
            {"user_id": ObjectId(user_id)},
            sort=[("name", 1)],
        )

    def find_by_name(
        self, user_id: str, name: str
    ):
        """Find a tag by user and name."""
        return self.find_one({
            "user_id": ObjectId(user_id),
            "name": name,
        })
