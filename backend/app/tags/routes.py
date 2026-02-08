"""Tag API routes."""

from flask import jsonify, request
from flask_jwt_extended import (
    get_jwt_identity,
    jwt_required,
)
from bson import ObjectId

from app.tags import tags_bp
from app.models.tag import create_tag_doc
from app.repositories.tag_repo import TagRepository
from app.utils.errors import (
    NotFoundError,
    ValidationError,
)
from app.utils.validators import is_valid_hex_color

tag_repo = TagRepository()


@tags_bp.route("", methods=["GET"])
@jwt_required()
def list_tags():
    """List all tags for the current user."""
    user_id = get_jwt_identity()
    tags = tag_repo.find_by_user(user_id)
    return jsonify({
        "tags": [
            tag_repo.serialize_doc(t) for t in tags
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

    color = data.get("color", "#6B7280")
    if not is_valid_hex_color(color):
        raise ValidationError("Invalid hex color.")

    doc = create_tag_doc(
        user_id=ObjectId(user_id),
        name=name,
        category=data.get("category", "custom"),
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

    tag_repo.delete_one(tag_id)
    return jsonify({"message": "Tag deleted."}), 200
