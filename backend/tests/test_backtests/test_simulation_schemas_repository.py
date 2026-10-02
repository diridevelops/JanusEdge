"""Focused contract checks for simulation schemas and persistence."""

from datetime import datetime, timezone

import mongomock
import pytest
from bson import ObjectId
from marshmallow import ValidationError
from pymongo.errors import DuplicateKeyError

from app.backtests.simulation_repository import BacktestSimulationRepository
from app.backtests.simulation_schemas import (
    SubmitOrderRequestSchema,
)
from app.db import init_db


def test_entry_schema_accepts_negative_blind_prices_and_checks_precision():
    schema = SubmitOrderRequestSchema(instrument_precision=5)
    valid = {
        "client_operation_id": "op-1",
        "expected_revision": 0,
        "side": "buy",
        "order_type": "limit",
        "auto_size": True,
        "entry_price": -1.2,
        "stop_loss": -1.3,
        "take_profit": -1.1,
    }

    assert schema.load(valid)["entry_price"] == -1.2
    with pytest.raises(ValidationError):
        schema.load({**valid, "take_profit": -1.100001})


@pytest.mark.parametrize("lots", [0, -0.0009, float("inf")])
def test_entry_schema_rejects_invalid_manual_lots(lots):
    schema = SubmitOrderRequestSchema(instrument_precision=5)
    request = {
        "client_operation_id": "op-2",
        "expected_revision": 0,
        "side": "buy",
        "order_type": "limit",
        "auto_size": False,
        "lots": lots,
        "entry_price": 1.1,
        "stop_loss": 1.09,
        "take_profit": 1.12,
    }

    with pytest.raises(ValidationError):
        schema.load(request)


@pytest.mark.parametrize("lots", [0.0009, 0.0011])
def test_entry_schema_defers_positive_lot_grid_to_frozen_run(lots):
    from app.backtests.simulation_engine import SimulationRuleError, validate_lots

    schema = SubmitOrderRequestSchema(instrument_precision=5)
    request = {
        "client_operation_id": "op-2",
        "expected_revision": 0,
        "side": "buy",
        "order_type": "limit",
        "auto_size": False,
        "lots": lots,
        "entry_price": 1.1,
        "stop_loss": 1.09,
        "take_profit": 1.12,
    }
    assert schema.load(request)["lots"] == lots
    with pytest.raises(SimulationRuleError):
        validate_lots(lots, {"min_lots": 0.01, "lot_increment": 0.00001})


def test_price_schema_validates_non_decimal_tick_grid():
    schema = SubmitOrderRequestSchema(
        instrument_precision=2,
        instrument_tick_size=0.25,
    )
    request = {
        "client_operation_id": "op-tick",
        "expected_revision": 0,
        "side": "buy",
        "order_type": "limit",
        "auto_size": True,
        "entry_price": 12.5,
        "stop_loss": 12.0,
        "take_profit": 13.0,
    }
    assert schema.load(request)["entry_price"] == 12.5
    with pytest.raises(ValidationError):
        schema.load({**request, "stop_loss": 12.1})


def test_repository_filters_versions_by_scope_generation_and_commit():
    db = mongomock.MongoClient().janusedge
    init_db(db)
    repository = BacktestSimulationRepository(database=db)
    user_id, other_user_id, run_id, order_id = [ObjectId() for _ in range(4)]

    for sequence, version, status in (
        (2, 1, "pending"),
        (4, 2, "filled"),
    ):
        repository.insert_order_version(
            {
                "user_id": user_id,
                "run_id": run_id,
                "reset_generation": 1,
                "order_id": order_id,
                "operation_sequence": sequence,
                "entity_version": version,
                "status": status,
            }
        )
    repository.insert_order_version(
        {
            "user_id": user_id,
            "run_id": run_id,
            "reset_generation": 0,
            "order_id": ObjectId(),
            "operation_sequence": 4,
            "entity_version": 1,
            "status": "filled",
        }
    )

    before_commit = repository.list_visible_orders(
        user_id,
        run_id,
        reset_generation=1,
        committed_sequence=3,
    )
    after_commit = repository.list_visible_orders(
        user_id,
        run_id,
        reset_generation=1,
        committed_sequence=4,
    )
    other_owner = repository.list_visible_orders(
        other_user_id,
        run_id,
        reset_generation=1,
        committed_sequence=4,
    )

    assert len(before_commit) == 1
    assert before_commit[0]["entity_version"] == 1
    assert after_commit[0]["entity_version"] == 2
    assert other_owner == []


def test_simulation_indexes_enforce_idempotency_and_trade_publication():
    db = mongomock.MongoClient().janusedge
    init_db(db)
    repository = BacktestSimulationRepository(database=db)
    user_id, run_id = ObjectId(), ObjectId()
    operation = {
        "user_id": user_id,
        "run_id": run_id,
        "client_operation_id": "stable-op",
        "sequence": 1,
        "reset_generation": 0,
    }
    repository.insert_operation(operation)

    with pytest.raises(DuplicateKeyError):
        repository.insert_operation({**operation, "_id": ObjectId()})

    publication = {
        "backtest_run_id": run_id,
        "simulation_generation": 0,
        "simulated_position_id": ObjectId(),
    }
    db.trades.insert_one(publication)
    with pytest.raises(DuplicateKeyError):
        db.trades.insert_one({**publication, "_id": ObjectId()})


def test_default_cost_profile_is_zero_and_owner_scoped():
    db = mongomock.MongoClient().janusedge
    init_db(db)
    repository = BacktestSimulationRepository(database=db)
    user_id, other_user_id, run_id = ObjectId(), ObjectId(), ObjectId()

    first = repository.find_visible_cost_profile(
        user_id, run_id, committed_sequence=0
    )
    repeated = repository.find_visible_cost_profile(
        user_id, run_id, committed_sequence=0
    )
    other = repository.find_visible_cost_profile(
        other_user_id, run_id, committed_sequence=0
    )

    assert first["revision"] == 0
    assert first["total_spread_pips"] == 0
    assert repeated["_id"] == first["_id"]
    assert other["_id"] != first["_id"]
