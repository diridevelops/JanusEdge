"""Market-data import batch model helpers."""

from app.utils.datetime_utils import utc_now


def create_market_data_import_batch_doc(
    user_id,
    file_name: str,
    file_hash: str,
    file_size_bytes: int,
    symbol: str,
    raw_symbol: str | None,
    source_platform: str = "ninjatrader",
    batch_type: str = "import",
) -> dict:
    """Create a market-data import batch document."""

    now = utc_now()
    return {
        "user_id": user_id,
        "file_name": file_name,
        "file_hash": file_hash,
        "file_size_bytes": file_size_bytes,
        "source_platform": source_platform,
        "batch_type": batch_type,
        "symbol": symbol,
        "raw_symbol": raw_symbol,
        "status": "queued",
        "progress": {
            "processed_bytes": 0,
            "total_bytes": file_size_bytes,
            "processed_percentage": 0.0,
        },
        "stats": {
            "processed_lines": 0,
            "valid_ticks": 0,
            "skipped_lines": 0,
            "days_completed": 0,
            "datasets_written": 0,
        },
        "error_message": None,
        "preview": None,
        "created_at": now,
        "started_at": None,
        "completed_at": None,
        "updated_at": now,
    }
