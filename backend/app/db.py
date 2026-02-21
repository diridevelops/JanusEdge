"""Database initialization — index creation."""

from pymongo.database import Database


def init_db(db: Database) -> None:
    """
    Create all required indexes for TradeLogs collections.

    Parameters:
        db: A PyMongo database instance.
    """
    # Users
    db.users.create_index("username", unique=True)

    # Trade Accounts
    db.trade_accounts.create_index(
        [("user_id", 1), ("account_name", 1)], unique=True
    )
    db.trade_accounts.create_index(
        [("user_id", 1), ("status", 1)]
    )

    # Import Batches
    db.import_batches.create_index(
        [("user_id", 1), ("imported_at", -1)]
    )
    db.import_batches.create_index(
        [("user_id", 1), ("file_hash", 1)], unique=True
    )

    # Executions
    db.executions.create_index(
        [("user_id", 1), ("symbol", 1), ("timestamp", 1)]
    )
    db.executions.create_index("trade_id")
    db.executions.create_index("import_batch_id")
    db.executions.create_index("trade_account_id")

    # Trades
    db.trades.create_index(
        [("user_id", 1), ("entry_time", -1)]
    )
    db.trades.create_index(
        [("user_id", 1), ("symbol", 1), ("entry_time", -1)]
    )
    db.trades.create_index(
        [("user_id", 1), ("trade_account_id", 1),
         ("entry_time", -1)]
    )
    db.trades.create_index(
        [("user_id", 1), ("status", 1), ("entry_time", -1)]
    )
    db.trades.create_index(
        [("user_id", 1), ("tag_ids", 1)]
    )
    db.trades.create_index(
        [("user_id", 1), ("side", 1), ("entry_time", -1)]
    )
    db.trades.create_index("import_batch_id")

    # Tags
    db.tags.create_index(
        [("user_id", 1), ("name", 1)], unique=True
    )
    db.tags.create_index(
        [("user_id", 1), ("category", 1)]
    )

    # Market Data Cache
    db.market_data_cache.create_index(
        [("symbol", 1), ("interval", 1), ("date", 1)],
        unique=True,
    )
    db.market_data_cache.create_index([("fetched_at", 1)])

    # Audit Logs
    db.audit_logs.create_index(
        [("user_id", 1), ("timestamp", -1)]
    )
    db.audit_logs.create_index(
        [("entity_type", 1), ("entity_id", 1)]
    )
    db.audit_logs.create_index(
        [("user_id", 1), ("action", 1), ("timestamp", -1)]
    )
