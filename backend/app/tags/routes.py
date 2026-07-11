"""Tag API routes."""

from flask import jsonify, request
from flask_jwt_extended import (
    get_jwt_identity,
    jwt_required,
)
from bson import ObjectId

from app.tags import tags_bp
from app.models.tag import create_tag_doc
from app.models.tag_category import create_tag_category_doc
from app.extensions import mongo
from app.repositories.tag_category_repo import TagCategoryRepository
from app.repositories.tag_repo import TagRepository
from app.tags.categories import ensure_tag_categories
from app.utils.errors import (
    NotFoundError,
    ValidationError,
)
from app.utils.validators import is_valid_hex_color

tag_repo = TagRepository()
category_repo = TagCategoryRepository()


@tags_bp.route("", methods=["GET"])
@jwt_required()
def list_tags():
    """List all tags for the current user."""
    user_id = get_jwt_identity()
    ensure_tag_categories(user_id)
    categories = {
        category["_id"]: category
        for category in category_repo.find_by_user(user_id)
    }
    tags = tag_repo.find_by_user(user_id)
    return jsonify({
        "tags": [
            {
                **tag_repo.serialize_doc(t),
                "category_id": str(t.get("category_id", "")),
                "category_name": categories.get(t.get("category_id"), {}).get("name", "General"),
                "category_color": categories.get(t.get("category_id"), {}).get("color", "#6366F1"),
            } for t in tags
        ]
    }), 200


@tags_bp.route("", methods=["POST"])
@jwt_required()
def create_tag():
    """
    Create a new tag.

    Expects JSON: {name, category?, color?}
    """
    user_id = get_jwt_identity()
    categories = ensure_tag_categories(user_id)
    data = request.get_json()
    if not data:
        raise ValidationError("Request body is required.")

    name = data.get("name", "").strip()
    if not name:
        raise ValidationError("Tag name is required.")

    existing = tag_repo.find_by_name(user_id, name)
    if existing:
        raise ValidationError(
            f"Tag '{name}' already exists."
        )

    category_id = data.get("category_id") or str(categories["general"]["_id"])
    category = category_repo.find_by_id(category_id)
    if not category or str(category["user_id"]) != user_id:
        raise ValidationError("Invalid tag category.")
    color = data.get("color", "#6B7280")
    if not is_valid_hex_color(color):
        raise ValidationError("Invalid hex color.")

    doc = create_tag_doc(
        user_id=ObjectId(user_id),
        name=name,
        category_id=ObjectId(category_id),
        color=color,
    )
    tag_id = tag_repo.insert_one(doc)
    tag = tag_repo.find_by_id(tag_id)
    return jsonify({
        "tag": tag_repo.serialize_doc(tag)
    }), 201


@tags_bp.route("/<tag_id>", methods=["PUT"])
@jwt_required()
def update_tag(tag_id):
    """
    Update a tag.

    Expects JSON: {name?, category?, color?}
    """
    user_id = get_jwt_identity()
    tag = tag_repo.find_by_id(tag_id)

    if not tag:
        raise NotFoundError("Tag not found.")
    if str(tag["user_id"]) != user_id:
        raise NotFoundError("Tag not found.")

    data = request.get_json()
    if not data:
        raise ValidationError("Request body is required.")

    from app.utils.datetime_utils import utc_now

    updates = {}
    if "name" in data:
        updates["name"] = data["name"].strip()
    if "category" in data:
        updates["category"] = data["category"]
    if "category_id" in data:
        category = category_repo.find_by_id(data["category_id"])
        if not category or str(category["user_id"]) != user_id:
            raise ValidationError("Invalid tag category.")
        updates["category_id"] = category["_id"]
    if "color" in data:
        if not is_valid_hex_color(data["color"]):
            raise ValidationError("Invalid hex color.")
        updates["color"] = data["color"]

    if updates:
        tag_repo.update_one(
            tag_id, {"$set": updates}
        )

    tag = tag_repo.find_by_id(tag_id)
    return jsonify({
        "tag": tag_repo.serialize_doc(tag)
    }), 200


@tags_bp.route("/categories", methods=["GET"])
@jwt_required()
def list_categories():
    user_id = get_jwt_identity()
    ensure_tag_categories(user_id)
    categories = category_repo.find_by_user(user_id)
    return jsonify({"categories": [category_repo.serialize_doc(c) for c in categories]}), 200


@tags_bp.route("/categories", methods=["POST"])
@jwt_required()
def create_category():
    user_id = get_jwt_identity()
    data = request.get_json() or {}
    name = data.get("name", "").strip()
    color = data.get("color", "")
    if not name:
        raise ValidationError("Category name is required.")
    if not is_valid_hex_color(color):
        raise ValidationError("Invalid hex color.")
    if category_repo.find_one({"user_id": ObjectId(user_id), "name": name}):
        raise ValidationError(f"Category '{name}' already exists.")
    category_id = category_repo.insert_one(create_tag_category_doc(ObjectId(user_id), name, color))
    return jsonify({"category": category_repo.serialize_doc(category_repo.find_by_id(category_id))}), 201


@tags_bp.route("/categories/<category_id>", methods=["PUT"])
@jwt_required()
def update_category(category_id):
    user_id = get_jwt_identity()
    category = category_repo.find_by_id(category_id)
    if not category or str(category["user_id"]) != user_id:
        raise NotFoundError("Category not found.")
    data = request.get_json() or {}
    updates = {}
    if "name" in data:
        if category.get("system_key") == "general":
            raise ValidationError("The General category cannot be renamed.")
        updates["name"] = data["name"].strip()
    if "color" in data:
        if not is_valid_hex_color(data["color"]):
            raise ValidationError("Invalid hex color.")
        updates["color"] = data["color"]
    if updates:
        category_repo.update_one(category_id, {"$set": updates})
    return jsonify({"category": category_repo.serialize_doc(category_repo.find_by_id(category_id))}), 200


@tags_bp.route("/categories/<category_id>", methods=["DELETE"])
@jwt_required()
def delete_category(category_id):
    user_id = get_jwt_identity()
    category = category_repo.find_by_id(category_id)
    if not category or str(category["user_id"]) != user_id:
        raise NotFoundError("Category not found.")
    if category.get("system_key") == "general":
        raise ValidationError("The General category cannot be deleted.")
    if mongo.db.tags.count_documents({"user_id": ObjectId(user_id), "category_id": category["_id"]}):
        raise ValidationError("Move or delete all tags in this category first.")
    category_repo.delete_one(category_id)
    return jsonify({"message": "Category deleted."}), 200


@tags_bp.route("/<tag_id>", methods=["DELETE"])
@jwt_required()
def delete_tag(tag_id):
    """Delete a tag."""
    user_id = get_jwt_identity()
    tag = tag_repo.find_by_id(tag_id)

    if not tag:
        raise NotFoundError("Tag not found.")
    if str(tag["user_id"]) != user_id:
        raise NotFoundError("Tag not found.")

    cleanup_result = mongo.db.trades.update_many(
        {
            "user_id": ObjectId(user_id),
            "tag_ids": tag["_id"],
        },
        {"$pull": {"tag_ids": tag["_id"]}},
    )
    tag_repo.delete_one(tag_id)
    return jsonify({
        "message": "Tag deleted.",
        "trades_updated": cleanup_result.modified_count,
    }), 200
