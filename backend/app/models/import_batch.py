"""Import batch model definition."""

from app.utils.datetime_utils import utc_now


def create_import_batch_doc(
    user_id,
    file_name: str,
    file_hash: str,
    file_size_bytes: int,
    platform: str,
    column_mapping: dict = None,
    reconstruction_method: str = "FIFO",
    stats: dict = None,
    errors: list = None,
) -> dict:
    """
    Create an import batch document for MongoDB insertion.

    Parameters:
        user_id: ObjectId of the user.
        file_name: Original CSV file name.
        file_hash: SHA-256 of file contents.
        file_size_bytes: File size in bytes.
        platform: 'ninjatrader' or 'quantower'.
        column_mapping: Detected column mapping.
        reconstruction_method: 'FIFO', 'LIFO', or 'WAVG'.
        stats: Import statistics.
        errors: List of parsing errors.

    Returns:
        Dict ready for MongoDB insert.
    """
    return {
        "user_id": user_id,
        "file_name": file_name,
        "file_hash": file_hash,
        "file_size_bytes": file_size_bytes,
        "platform": platform,
        "column_mapping": column_mapping or {},
        "reconstruction_method": reconstruction_method,
        "stats": stats or {
            "total_rows": 0,
            "imported_rows": 0,
            "skipped_rows": 0,
            "error_rows": 0,
            "trades_reconstructed": 0,
        },
        "errors": errors or [],
        "imported_at": utc_now(),
    }
