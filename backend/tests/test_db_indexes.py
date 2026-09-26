"""Database index contracts needed by optional app features."""

import mongomock

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
