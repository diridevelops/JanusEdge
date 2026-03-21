"""Market-data dataset model helpers."""

from app.utils.datetime_utils import utc_now


def create_market_data_doc(
    symbol: str,
    raw_symbol: str | None,
    dataset_type: str,
    timeframe: str | None,
    date,
    object_key: str,
    row_count: int,
    byte_size: int,
    source_file_name: str,
    import_batch_id: str | None = None,
    status: str = "ready",
) -> dict:
    """
    Create a market-data dataset metadata document.

    Parameters:
        symbol: Canonical market-data symbol key.
        raw_symbol: Original raw symbol if available.
        dataset_type: 'ticks' or 'candles'.
        timeframe: Candle timeframe or None for raw ticks.
        date: Trading day as a date object.
        object_key: MinIO object key for the dataset.
        row_count: Number of rows stored in the Parquet object.
        byte_size: Stored object size in bytes.
        source_file_name: Source import file name.
        import_batch_id: Related import batch id string.
        status: Dataset status.

    Returns:
        Dict ready for MongoDB insert.
    """
    now = utc_now()
    return {
        "symbol": symbol,
        "raw_symbol": raw_symbol,
        "dataset_type": dataset_type,
        "timeframe": timeframe,
        "date": date,
        "object_key": object_key,
        "row_count": row_count,
        "byte_size": byte_size,
        "source_file_name": source_file_name,
        "import_batch_id": import_batch_id,
        "status": status,
        "created_at": now,
        "updated_at": now,
    }
