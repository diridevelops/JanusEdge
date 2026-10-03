"""Database initialization — index creation."""

from pymongo.database import Database


_LEGACY_SIMULATION_ENTITY_INDEX_KEYS = [
    ("run_id", 1),
    ("generation", 1),
    ("record_id", 1),
    ("sequence", 1),
]


def _drop_legacy_simulation_entity_indexes(db: Database) -> None:
    """Remove the pre-versioned order/position uniqueness indexes.

    Those indexes key fields that current simulation records no longer use.
    MongoDB treats their missing values as null, so every new entity version
    for a run collides with the first legacy record. The current, versioned
    unique indexes are created below; dropping these exact obsolete indexes
    leaves all existing documents untouched.
    """
    for collection_name in (
        "backtest_simulation_orders",
        "backtest_simulation_positions",
    ):
        collection = db[collection_name]
        for name, index in collection.index_information().items():
            if (
                index.get("unique") is True
                and index.get("key") == _LEGACY_SIMULATION_ENTITY_INDEX_KEYS
            ):
                collection.drop_index(name)


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
    # Backtest fills are append-only Execution documents. Partial indexes keep
    # ordinary imported/manual executions outside Backtest uniqueness rules.
    db.executions.create_index(
        [
            ("user_id", 1),
            ("backtest_run_id", 1),
            ("reset_generation", 1),
            ("simulation_operation_sequence", 1),
        ]
    )
    db.executions.create_index(
        [
            ("user_id", 1),
            ("backtest_run_id", 1),
            ("reset_generation", 1),
            ("backtest_order_id", 1),
            ("source_candle_index", 1),
            ("simulation_operation_sequence", 1),
            ("allocation_index", 1),
        ],
        unique=True,
        partialFilterExpression={
            "backtest_run_id": {"$exists": True},
            "backtest_order_id": {"$exists": True},
            "allocation_index": {"$exists": True},
        },
    )

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
    # One conventional closed Trade may be published for each simulated
    # position and reset generation; ordinary trades are excluded.
    db.trades.create_index(
        [
            ("backtest_run_id", 1),
            ("simulation_generation", 1),
            ("simulated_position_id", 1),
        ],
        unique=True,
        partialFilterExpression={
            "backtest_run_id": {"$exists": True},
            "simulated_position_id": {"$exists": True},
        },
    )
    db.trades.create_index(
        [
            ("backtest_run_id", 1),
            ("simulation_generation", 1),
            ("simulation_operation_sequence", 1),
            ("status", 1),
        ],
        partialFilterExpression={"backtest_run_id": {"$exists": True}},
    )

    # Tags
    db.tags.create_index(
        [("user_id", 1), ("name", 1)], unique=True
    )
    db.tags.create_index(
        [("user_id", 1), ("category", 1)]
    )
    db.tags.create_index([("user_id", 1), ("category_id", 1)])
    db.tag_categories.create_index(
        [("user_id", 1), ("name", 1)], unique=True
    )
    db.tag_categories.create_index(
        [("user_id", 1), ("system_key", 1)], unique=True,
        # MongoDB partial indexes do not support $ne; system keys are strings.
        partialFilterExpression={"system_key": {"$type": "string"}},
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

    # Backtest workspace
    _drop_legacy_simulation_entity_indexes(db)

    db.backtest_runs.create_index(
        [("user_id", 1), ("created_at", -1)]
    )
    db.backtest_runs.create_index(
        [
            ("status", 1),
            ("simulation_control.pending_operation_id", 1),
            ("updated_at", 1),
        ]
    )
    # Snapshot objects are run-owned and immutable; sparse keeps preparing
    # runs without a completed snapshot out of this uniqueness constraint.
    db.backtest_runs.create_index(
        [("snapshot.object_key", 1)], unique=True, sparse=True
    )
    db.trade_accounts.create_index(
        [("user_id", 1), ("backtest_run_id", 1)],
        unique=True,
        partialFilterExpression={"backtest_run_id": {"$exists": True}},
    )
    db.backtest_preparation_jobs.create_index(
        [("run_id", 1)], unique=True
    )
    db.backtest_preparation_jobs.create_index(
        [("state", 1), ("lease_expires_at", 1), ("created_at", 1)]
    )
    db.backtest_candle_cache.create_index(
        [("user_id", 1), ("cache_key", 1)], unique=True
    )
    db.backtest_candle_cache.create_index(
        [("state", 1), ("lease_expires_at", 1)]
    )
    db.backtest_chart_tabs.create_index(
        [("user_id", 1), ("run_id", 1), ("id", 1)], unique=True
    )
    db.backtest_chart_tabs.create_index(
        [("user_id", 1), ("run_id", 1), ("position", 1)]
    )
    db.backtest_chart_workspaces.create_index(
        [("user_id", 1), ("run_id", 1)], unique=True
    )
    db.backtest_drawing_states.create_index(
        [
            ("user_id", 1),
            ("run_id", 1),
            ("interval_minutes", 1),
        ],
        unique=True,
    )
    db.backtest_notices.create_index(
        [("user_id", 1), ("dismissed", 1), ("created_at", -1)]
    )

    # Backtest simulation operation journal and immutable entity versions.
    db.backtest_simulation_operations.create_index(
        [("user_id", 1), ("run_id", 1), ("client_operation_id", 1)],
        unique=True,
    )
    db.backtest_simulation_operations.create_index(
        [("run_id", 1), ("sequence", 1)], unique=True
    )
    db.backtest_simulation_operations.create_index(
        [("user_id", 1), ("run_id", 1), ("state", 1), ("sequence", 1)]
    )

    db.backtest_simulation_orders.create_index(
        [
            ("user_id", 1),
            ("run_id", 1),
            ("reset_generation", 1),
            ("order_id", 1),
            ("entity_version", 1),
        ],
        unique=True,
    )
    db.backtest_simulation_orders.create_index(
        [
            ("user_id", 1),
            ("run_id", 1),
            ("reset_generation", 1),
            ("operation_sequence", -1),
        ]
    )

    db.backtest_simulation_positions.create_index(
        [
            ("user_id", 1),
            ("run_id", 1),
            ("reset_generation", 1),
            ("position_id", 1),
            ("entity_version", 1),
        ],
        unique=True,
    )
    db.backtest_simulation_positions.create_index(
        [
            ("user_id", 1),
            ("run_id", 1),
            ("reset_generation", 1),
            ("operation_sequence", -1),
            ("status", 1),
        ]
    )

    db.backtest_simulation_cost_profiles.create_index(
        [("user_id", 1), ("run_id", 1), ("revision", 1)], unique=True
    )
    db.backtest_simulation_cost_profiles.create_index(
        [("user_id", 1), ("run_id", 1), ("operation_sequence", -1)]
    )
