"""Tag model definition."""

from app.utils.datetime_utils import utc_now


def create_tag_doc(
    user_id,
    name: str,
    category: str = "custom",
    color: str = "#6B7280",
) -> dict:
    """
    Create a tag document.

    Parameters:
        user_id: ObjectId of the user.
        name: Tag name.
        category: 'strategy', 'mistake', etc.
        color: Hex color code.

    Returns:
        Dict ready for MongoDB insert.
    """
    return {
        "user_id": user_id,
        "name": name,
        "category": category,
        "color": color,
        "created_at": utc_now(),
    }
