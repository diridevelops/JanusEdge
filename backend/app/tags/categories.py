"""Category initialization and legacy tag migration."""

from bson import ObjectId

from app.models.tag_category import DEFAULT_TAG_CATEGORIES, create_tag_category_doc
from app.repositories.tag_category_repo import TagCategoryRepository
from app.extensions import mongo


def ensure_tag_categories(user_id: str) -> dict[str, dict]:
    repo = TagCategoryRepository()
    categories = {c.get("system_key"): c for c in repo.find_by_user(user_id) if c.get("system_key")}
    for system_key, name, color in DEFAULT_TAG_CATEGORIES:
        if system_key not in categories:
            category_id = repo.insert_one(create_tag_category_doc(ObjectId(user_id), name, color, system_key))
            categories[system_key] = repo.find_by_id(category_id)

    for tag in mongo.db.tags.find({"user_id": ObjectId(user_id), "category_id": {"$exists": False}}):
        system_key = "mistakes" if tag.get("name", "").lower() == "wicked-out" else "general"
        mongo.db.tags.update_one({"_id": tag["_id"]}, {"$set": {"category_id": categories[system_key]["_id"]}})
    return categories
