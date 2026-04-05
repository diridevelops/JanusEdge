"""Database initialization — index creation."""

from pymongo.database import Database


def init_db(db: Database) -> None:
    """
    Create all required indexes for Janus Edge collections.

    Parameters:
        db: A PyMongo database instance.
    """
    # Users
    db.users.create_index("username", unique=True)
    db.auth_refresh_sessions.create_index(
        [("token_hash", 1)], unique=True
    )
    db.auth_refresh_sessions.create_index(
        [("user_id", 1), ("revoked_at", 1), ("created_at", -1)]
    )

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
    db.trades.create_index(
        [
            ("user_id", 1),
            ("status", 1),
            ("source", 1),
            ("symbol", 1),
            ("side", 1),
            ("entry_time", 1),
            ("exit_time", 1),
            ("total_quantity", 1),
            ("avg_entry_price", 1),
            ("avg_exit_price", 1),
        ]
    )

    # Tags
    db.tags.create_index(
        [("user_id", 1), ("name", 1)], unique=True
    )
    db.tags.create_index(
        [("user_id", 1), ("category", 1)]
    )

    # Market data datasets
    db.market_data_datasets.create_index(
        [
            ("symbol", 1),
            ("dataset_type", 1),
            ("timeframe", 1),
            ("date", 1),
        ],
        unique=True,
    )
    db.market_data_datasets.create_index(
        [("dataset_type", 1), ("timeframe", 1), ("date", 1)]
    )
    db.market_data_datasets.create_index([("status", 1)])

    # Market data import batches
    db.market_data_import_batches.create_index(
        [("user_id", 1), ("created_at", -1)]
    )
    db.market_data_import_batches.create_index(
        [("user_id", 1), ("status", 1), ("created_at", -1)]
    )

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

    # Media Attachments
    db.media.create_index(
        [("user_id", 1), ("trade_id", 1), ("created_at", 1)]
    )
