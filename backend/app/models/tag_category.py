"""Tag category model and default category constants."""

from app.utils.datetime_utils import utc_now

DEFAULT_TAG_CATEGORIES = (
    ("general", "General", "#6366F1"),
    ("triggers", "Triggers", "#D4A72C"),
    ("mistakes", "Mistakes", "#EF4444"),
)


def create_tag_category_doc(user_id, name: str, color: str, system_key=None):
    now = utc_now()
    return {
        "user_id": user_id,
        "name": name,
        "color": color,
        "system_key": system_key,
        "created_at": now,
        "updated_at": now,
    }
