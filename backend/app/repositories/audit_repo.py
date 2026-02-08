"""Audit log repository."""

from app.repositories.base import BaseRepository


class AuditRepository(BaseRepository):
    """Repository for audit_logs collection."""

    collection_name = "audit_logs"
