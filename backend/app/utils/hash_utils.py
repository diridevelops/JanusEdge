"""File hashing utilities for duplicate detection."""

import hashlib


def compute_file_hash(content: bytes) -> str:
    """
    Compute SHA-256 hash of file content.

    Parameters:
        content: Raw file bytes.

    Returns:
        Hex-encoded SHA-256 hash string.
    """
    return hashlib.sha256(content).hexdigest()
