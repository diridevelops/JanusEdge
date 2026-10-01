"""Database index contracts needed by optional app features."""

import mongomock
from bson import ObjectId

from app.db import init_db


def test_init_db_creates_supported_partial_and_workspace_indexes():
    db = mongomock.MongoClient().janusedge

    init_db(db)

    category_index = next(
        index
        for index in db.tag_categories.index_information().values()
        if index["key"] == [("user_id", 1), ("system_key", 1)]
    )
    assert category_index["unique"] is True
    assert category_index["partialFilterExpression"] == {
        "system_key": {"$type": "string"}
    }

    workspace_index = next(
        index
        for index in db.backtest_chart_workspaces.index_information().values()
        if index["key"] == [("user_id", 1), ("run_id", 1)]
    )
    assert workspace_index["unique"] is True


def test_init_db_drops_legacy_simulation_entity_indexes():
    db = mongomock.MongoClient().janusedge
    legacy_keys = [
        ("run_id", 1),
        ("generation", 1),
        ("record_id", 1),
        ("sequence", 1),
    ]
    order_collection = db.backtest_simulation_orders
    position_collection = db.backtest_simulation_positions
    order_collection.create_index(legacy_keys, unique=True)
    position_collection.create_index(legacy_keys, unique=True)
    run_id = ObjectId()
    order_collection.insert_one({"run_id": run_id, "legacy": True})
    position_collection.insert_one({"run_id": run_id, "legacy": True})

    init_db(db)

    for collection_name in (
        "backtest_simulation_orders",
        "backtest_simulation_positions",
    ):
        collection = db[collection_name]
        assert not any(
            index.get("key") == legacy_keys and index.get("unique") is True
            for index in collection.index_information().values()
        )
        assert collection.count_documents({"run_id": run_id, "legacy": True}) == 1

    user_id = ObjectId()
    order_collection.insert_one({
        "user_id": user_id,
        "run_id": run_id,
        "reset_generation": 0,
        "order_id": ObjectId(),
        "entity_version": 1,
    })
    position_collection.insert_one({
        "user_id": user_id,
        "run_id": run_id,
        "reset_generation": 0,
        "position_id": ObjectId(),
        "entity_version": 1,
    })
    position_collection.insert_one({
        "user_id": user_id,
        "run_id": run_id,
        "reset_generation": 0,
        "position_id": ObjectId(),
        "entity_version": 1,
    })
    order_collection.insert_one({
        "user_id": user_id,
        "run_id": run_id,
        "reset_generation": 0,
        "order_id": ObjectId(),
        "entity_version": 1,
    })
