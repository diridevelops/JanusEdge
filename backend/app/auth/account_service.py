"""Account-level destructive cleanup helpers."""

from collections.abc import Iterable

from bson import ObjectId

from app.extensions import mongo
from app.repositories.user_repo import UserRepository
from app.storage import get_bucket, get_client


class AccountDeletionService:
    """Delete all data owned by one application account."""

    USER_SCOPED_COLLECTIONS = (
        "media",
        "executions",
        "trades",
        "trade_accounts",
        "import_batches",
        "tags",
        "tag_categories",
        "audit_logs",
        "market_data_import_batches",
        "auth_refresh_sessions",
    )

    def __init__(self) -> None:
        self.user_repo = UserRepository()

    def delete_account(self, user_id: str) -> None:
        """Delete user-owned records and media, then delete the user."""

        user_object_id = ObjectId(user_id)
        media_object_keys = self._collect_media_object_keys(user_id)
        self._delete_media_objects(media_object_keys)

        for collection_name in self.USER_SCOPED_COLLECTIONS:
            mongo.db[collection_name].delete_many(
                {"user_id": user_object_id}
            )

        if self.user_repo.delete_one(user_id):
            return

        # A concurrent request may already have removed the user after the
        # owned collections were cleaned. Treat that state as an idempotent
        # success; an existing user means the final delete genuinely failed.
        if self.user_repo.find_by_id(user_id) is None:
            return
        raise RuntimeError("Account could not be deleted.")

    def _collect_media_object_keys(self, user_id: str) -> set[str]:
        """Collect known and orphaned media objects for the user."""

        bucket = get_bucket()
        client = get_client()
        object_keys: set[str] = set()

        media_documents = mongo.db.media.find(
            {"user_id": ObjectId(user_id)},
            {"object_key": 1},
        )
        object_keys.update(
            document["object_key"]
            for document in media_documents
            if document.get("object_key")
        )

        try:
            object_keys.update(
                object_name
                for object_name in self._list_user_media_objects(
                    client, bucket, user_id
                )
                if object_name
            )
        except Exception as exc:
            raise RuntimeError(
                "Account media could not be enumerated."
            ) from exc

        return object_keys

    @staticmethod
    def _list_user_media_objects(
        client, bucket: str, user_id: str
    ) -> Iterable[str]:
        """Yield every media object under the user's storage prefix."""

        prefix = f"{user_id}/"
        for item in client.list_objects(
            bucket,
            prefix=prefix,
            recursive=True,
        ):
            object_name = getattr(item, "object_name", None)
            if object_name is None and isinstance(item, dict):
                object_name = item.get("object_name")
            if object_name is not None:
                yield object_name

    @staticmethod
    def _delete_media_objects(object_keys: Iterable[str]) -> None:
        """Delete all collected media objects before MongoDB cleanup."""

        client = get_client()
        bucket = get_bucket()
        try:
            for object_key in object_keys:
                client.remove_object(bucket, object_key)
        except Exception as exc:
            raise RuntimeError(
                "Account media could not be deleted."
            ) from exc
