"""Tag category persistence helpers."""

from bson import ObjectId

from app.repositories.base import BaseRepository


class TagCategoryRepository(BaseRepository):
    collection_name = "tag_categories"

    def find_by_user(self, user_id: str):
        return self.find_many({"user_id": ObjectId(user_id)}, sort=[("name", 1)])

    def find_by_system_key(self, user_id: str, system_key: str):
        return self.find_one({"user_id": ObjectId(user_id), "system_key": system_key})
