"""Audit log model definition."""

from app.utils.datetime_utils import utc_now


def create_audit_log_doc(
    user_id,
    action: str,
    entity_type: str,
    entity_id,
    old_values: dict = None,
    new_values: dict = None,
    metadata: dict = None,
) -> dict:
    """
    Create an audit log document.

    Parameters:
        user_id: ObjectId of the user.
        action: Action performed.
        entity_type: Type of entity affected.
        entity_id: ObjectId of the entity.
        old_values: Snapshot before change.
        new_values: Snapshot after change.
        metadata: Additional metadata.

    Returns:
        Dict ready for MongoDB insert.
    """
    return {
        "user_id": user_id,
        "action": action,
        "entity_type": entity_type,
        "entity_id": entity_id,
        "old_values": old_values,
        "new_values": new_values,
        "metadata": metadata or {},
        "timestamp": utc_now(),
    }
