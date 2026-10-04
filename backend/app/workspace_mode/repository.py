"""Persistence for a user's active workspace mode."""

from bson import ObjectId

from app.repositories.base import BaseRepository
from app.utils.datetime_utils import utc_now


class WorkspaceModeRepository(BaseRepository):
    """Store one workspace-mode document per user."""

    collection_name = "workspace_modes"

    def find_by_user(self, user_id: str) -> dict | None:
        """Return the user's mode document, if one has been saved."""
        return self.find_one({"_id": ObjectId(user_id)})

    def save_for_user(self, user_id: str, active_mode: str) -> None:
        """Persist the selected mode under the authenticated user's id."""
        user_oid = ObjectId(user_id)
        now = utc_now()
        self.collection.update_one(
            {"_id": user_oid},
            {
                "$set": {
                    "user_id": user_oid,
                    "active_mode": active_mode,
                    "updated_at": now,
                },
                "$setOnInsert": {"created_at": now},
            },
            upsert=True,
        )
