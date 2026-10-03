"""Validation schemas for durable Backtest simulation records and commands."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
import math
from typing import Any

from bson import ObjectId
from marshmallow import Schema, ValidationError, fields, validate
from marshmallow.decorators import validates_schema


OPERATION_KINDS = frozenset(
    {
        "submit_order",
        "cancel_order",
        "close_position",
        "modify_protection",
        "update_risk",
        "update_costs",
        "advance",
        "rewind",
        "reset",
    }
)
OPERATION_STATES = frozenset(
    {"pending", "cleanup_pending", "committed", "rejected"}
)
ORDER_ROLES = frozenset(
    {"entry", "protective_stop", "protective_target", "manual_close"}
)
ORDER_TYPES = frozenset({"market", "limit", "stop_market"})
ORDER_STATES = frozenset({"pending", "filled", "cancelled"})
SIDES = frozenset({"buy", "sell"})
POSITION_SIDES = frozenset({"long", "short"})
POSITION_STATES = frozenset({"open", "closed"})
class SimulationSchema(Schema):
    """Base schema carrying the run's immutable price precision."""

    def __init__(
        self,
        *args,
        instrument_precision: int | None = None,
        instrument_tick_size: float | None = None,
        **kwargs,
    ):
        if instrument_precision is not None and (
            isinstance(instrument_precision, bool)
            or not isinstance(instrument_precision, int)
            or instrument_precision < 0
            or instrument_precision > 15
        ):
            raise ValueError("instrument_precision must be an integer from 0 to 15")
        self.instrument_precision = instrument_precision
        if instrument_tick_size is not None:
            try:
                tick = Decimal(str(instrument_tick_size))
            except (InvalidOperation, TypeError, ValueError) as exc:
                raise ValueError("instrument_tick_size must be positive and finite") from exc
            if not tick.is_finite() or tick <= 0:
                raise ValueError("instrument_tick_size must be positive and finite")
            self.instrument_tick_size = tick
        else:
            self.instrument_tick_size = None
        super().__init__(*args, **kwargs)


class FiniteFloat(fields.Float):
    """A JSON number that cannot be NaN or infinite."""

    def _deserialize(self, value: Any, attr: str | None, data: Any, **kwargs):
        if isinstance(value, bool):
            raise ValidationError("Must be a finite number.")
        result = super()._deserialize(value, attr, data, **kwargs)
        if not math.isfinite(result):
            raise ValidationError("Must be a finite number.")
        return result


class InstrumentPrice(FiniteFloat):
    """A finite price checked against immutable run precision when supplied."""

    def _deserialize(self, value: Any, attr: str | None, data: Any, **kwargs):
        result = super()._deserialize(value, attr, data, **kwargs)
        precision = getattr(self.root, "instrument_precision", None)
        if precision is None:
            raise ValidationError(
                "Instrument precision is required to validate this price."
            )
        try:
            price = Decimal(str(result))
            scaled = price.scaleb(precision)
        except (InvalidOperation, ValueError) as exc:
            raise ValidationError("Must be a finite instrument price.") from exc
        if not scaled.is_finite() or scaled != scaled.to_integral_value():
            raise ValidationError(
                f"Must use no more than {precision} decimal places."
            )
        tick = getattr(self.root, "instrument_tick_size", None)
        if tick is not None and price % tick != 0:
            raise ValidationError(
                f"Must be a multiple of the instrument tick size {tick}."
            )
        return result


class LotSize(FiniteFloat):
    """A positive lot quantity; the run's frozen instrument rules check its grid."""

    def _deserialize(self, value: Any, attr: str | None, data: Any, **kwargs):
        result = super()._deserialize(value, attr, data, **kwargs)
        if result <= 0:
            raise ValidationError("Must be greater than zero.")
        return result


class PositionLots(FiniteFloat):
    """Nonnegative remaining quantity; instrument grids are run-specific."""

    def _deserialize(self, value: Any, attr: str | None, data: Any, **kwargs):
        result = super()._deserialize(value, attr, data, **kwargs)
        if result < 0:
            raise ValidationError("Remaining lots cannot be negative.")
        return result


class NonnegativeFiniteFloat(FiniteFloat):
    """Finite numeric amount that may be zero but not negative."""

    def _deserialize(self, value: Any, attr: str | None, data: Any, **kwargs):
        result = super()._deserialize(value, attr, data, **kwargs)
        if result < 0:
            raise ValidationError("Must be greater than or equal to zero.")
        return result


class PositiveFiniteFloat(FiniteFloat):
    """Finite numeric amount that must be strictly positive."""

    def _deserialize(self, value: Any, attr: str | None, data: Any, **kwargs):
        result = super()._deserialize(value, attr, data, **kwargs)
        if result <= 0:
            raise ValidationError("Must be greater than zero.")
        return result


class SimulationRequestSchema(SimulationSchema):
    """Fields common to every mutation request."""

    client_operation_id = fields.Str(
        required=True, validate=validate.Length(min=1, max=128)
    )
    expected_revision = fields.Int(required=True, validate=validate.Range(min=0))


class SubmitOrderRequestSchema(SimulationRequestSchema):
    """Protected market/limit entry command; negative prices remain valid."""

    side = fields.Str(required=True, validate=validate.OneOf(sorted(SIDES)))
    order_type = fields.Str(
        required=True, validate=validate.OneOf(["market", "limit"])
    )
    auto_size = fields.Bool(required=True)
    lots = LotSize(allow_none=True, load_default=None)
    entry_price = InstrumentPrice(allow_none=True, load_default=None)
    stop_loss = InstrumentPrice(required=True)
    take_profit = InstrumentPrice(required=True)

    @validates_schema
    def validate_sizing_and_bracket(self, data, **kwargs) -> None:
        """Require entry fields to match order type and protect its entry."""
        if data["auto_size"] and data.get("lots") is not None:
            raise ValidationError(
                {"lots": ["Omit lots when auto_size is true."]}
            )
        if not data["auto_size"] and data.get("lots") is None:
            raise ValidationError(
                {"lots": ["Lots are required when auto_size is false."]}
            )

        if data["order_type"] == "market":
            if data.get("entry_price") is not None:
                raise ValidationError(
                    {"entry_price": ["Market entries do not submit entry_price."]}
                )
            return

        entry_price = data.get("entry_price")
        if entry_price is None:
            raise ValidationError(
                {"entry_price": ["Limit entries require entry_price."]}
            )
        if data["side"] == "buy":
            valid = data["stop_loss"] < entry_price < data["take_profit"]
        else:
            valid = data["take_profit"] < entry_price < data["stop_loss"]
        if not valid:
            raise ValidationError(
                "Stop-loss and take-profit must bracket the limit entry."
            )


class CancelOrderRequestSchema(SimulationRequestSchema):
    """Cancel one pending entry order identified by the route path."""


class ClosePositionRequestSchema(SimulationRequestSchema):
    """Close the full remaining quantity of one position."""


class ModifyProtectionRequestSchema(SimulationRequestSchema):
    """Move one or both protection prices for a single position."""

    stop_loss = InstrumentPrice(allow_none=True, load_default=None)
    take_profit = InstrumentPrice(allow_none=True, load_default=None)

    @validates_schema
    def require_changed_level(self, data, **kwargs) -> None:
        if data.get("stop_loss") is None and data.get("take_profit") is None:
            raise ValidationError(
                "At least one of stop_loss or take_profit is required."
            )


class UpdateCostsRequestSchema(SimulationRequestSchema):
    """Replace the per-run execution cost profile."""

    total_spread_pips = NonnegativeFiniteFloat(required=True)
    slippage_pips = NonnegativeFiniteFloat(required=True)
    commission_usd_per_lot_per_side = NonnegativeFiniteFloat(required=True)


class UpdateRiskRequestSchema(SimulationRequestSchema):
    """Update the risk budget percentage used to size future entries."""

    risk_percent = PositiveFiniteFloat(required=True)

    @validates_schema
    def validate_risk_percent(self, data, **kwargs) -> None:
        if data["risk_percent"] > 100:
            raise ValidationError(
                {"risk_percent": ["Risk percent cannot exceed 100%."]}
            )


class AdvanceSimulationRequestSchema(SimulationRequestSchema):
    """Advance through every source candle up to the requested index."""

    target_source_index = fields.Int(required=True, validate=validate.Range(min=0))


class RewindSimulationRequestSchema(SimulationRequestSchema):
    """Rewind before the first accepted order, through the shared CAS gate."""

    source_candle_index = fields.Int(required=True, validate=validate.Range(min=0))
    time_ms = fields.Int(required=True, validate=validate.Range(min=0))


class ResetSimulationRequestSchema(SimulationRequestSchema):
    """Require an explicit reset confirmation."""

    confirmed = fields.Bool(required=True, validate=validate.Equal(True))


class SimulationOperationSchema(SimulationSchema):
    """Durable idempotency-journal record."""

    user_id = fields.Raw(required=True)
    run_id = fields.Raw(required=True)
    client_operation_id = fields.Str(
        required=True, validate=validate.Length(min=1, max=128)
    )
    sequence = fields.Int(required=True, validate=validate.Range(min=0))
    control_revision = fields.Int(required=True, validate=validate.Range(min=1))
    reset_generation = fields.Int(required=True, validate=validate.Range(min=0))
    kind = fields.Str(required=True, validate=validate.OneOf(sorted(OPERATION_KINDS)))
    state = fields.Str(required=True, validate=validate.OneOf(sorted(OPERATION_STATES)))
    final_state = fields.Str(
        allow_none=True,
        load_default=None,
        validate=validate.OneOf(["committed", "rejected"]),
    )
    request = fields.Dict(required=True)
    result = fields.Dict(allow_none=True, load_default=None)
    commit_updates = fields.Dict(allow_none=True, load_default=None)
    created_at = fields.DateTime(required=True)
    committed_at = fields.DateTime(allow_none=True, load_default=None)


class BacktestOrderSchema(SimulationSchema):
    """Versioned order document, including entry and protective orders."""

    user_id = fields.Raw(required=True)
    run_id = fields.Raw(required=True)
    reset_generation = fields.Int(required=True, validate=validate.Range(min=0))
    order_id = fields.Raw(required=True)
    operation_sequence = fields.Int(required=True, validate=validate.Range(min=0))
    entity_version = fields.Int(required=True, validate=validate.Range(min=1))
    client_order_id = fields.Str(required=True)
    role = fields.Str(required=True, validate=validate.OneOf(sorted(ORDER_ROLES)))
    order_type = fields.Str(required=True, validate=validate.OneOf(sorted(ORDER_TYPES)))
    side = fields.Str(required=True, validate=validate.OneOf(sorted(SIDES)))
    lots = LotSize(required=True)
    entry_price = InstrumentPrice(allow_none=True, load_default=None)
    sizing_reference_entry_price = InstrumentPrice(allow_none=True, load_default=None)
    sizing_quote_to_usd_rate = PositiveFiniteFloat(allow_none=True, load_default=None)
    stop_loss_price = InstrumentPrice(allow_none=True, load_default=None)
    take_profit_price = InstrumentPrice(allow_none=True, load_default=None)
    sizing_mode = fields.Str(
        allow_none=True,
        load_default=None,
        validate=validate.OneOf(["auto", "manual"]),
    )
    risk_percent = PositiveFiniteFloat(
        allow_none=True,
        load_default=None,
        validate=validate.Range(max=100),
    )
    risk_budget_usd = PositiveFiniteFloat(allow_none=True, load_default=None)
    status = fields.Str(required=True, validate=validate.OneOf(sorted(ORDER_STATES)))
    eligible_source_index = fields.Int(
        required=True, validate=validate.Range(min=0)
    )
    eligible_after_time_ms = fields.Int(
        allow_none=True, load_default=None, validate=validate.Range(min=0)
    )
    linked_position_id = fields.Raw(allow_none=True, load_default=None)
    oco_group_id = fields.Raw(allow_none=True, load_default=None)
    submitted_at = fields.DateTime(required=True)
    updated_at = fields.DateTime(required=True)

    @validates_schema
    def validate_order_role(self, data, **kwargs) -> None:
        role = data["role"]
        order_type = data["order_type"]
        if role == "entry":
            if order_type not in {"market", "limit"}:
                raise ValidationError("Entry orders support market or limit only.")
            if data.get("stop_loss_price") is None:
                raise ValidationError({"stop_loss_price": ["Required for entries."]})
            if data.get("take_profit_price") is None:
                raise ValidationError(
                    {"take_profit_price": ["Required for entries."]}
                )
            if order_type == "limit" and data.get("entry_price") is None:
                raise ValidationError({"entry_price": ["Required for limit entries."]})
            if order_type == "market" and data.get("entry_price") is not None:
                raise ValidationError(
                    {"entry_price": ["Market entries have no submitted entry price."]}
                )
            reference_price = data.get("sizing_reference_entry_price")
            if reference_price is None:
                raise ValidationError(
                    {"sizing_reference_entry_price": ["Required for entry orders."]}
                )
            if order_type == "limit" and reference_price != data.get("entry_price"):
                raise ValidationError(
                    "A limit entry's sizing reference must equal its entry price."
                )
            if data["side"] == "buy":
                valid_bracket = (
                    data["stop_loss_price"]
                    < reference_price
                    < data["take_profit_price"]
                )
            else:
                valid_bracket = (
                    data["take_profit_price"]
                    < reference_price
                    < data["stop_loss_price"]
                )
            if not valid_bracket:
                raise ValidationError(
                    "Stop-loss and take-profit must bracket the entry reference."
                )
            if data.get("sizing_mode") is None:
                raise ValidationError({"sizing_mode": ["Required for entries."]})
            if data.get("risk_percent") is None:
                raise ValidationError({"risk_percent": ["Required for entries."]})
            if data.get("risk_budget_usd") is None:
                raise ValidationError({"risk_budget_usd": ["Required for entries."]})
            if data.get("sizing_quote_to_usd_rate") is None:
                raise ValidationError(
                    {"sizing_quote_to_usd_rate": ["Required for entries."]}
                )
        elif role == "protective_stop" and order_type != "stop_market":
            raise ValidationError("Protective stops must use stop_market.")
        elif role == "protective_target" and order_type != "limit":
            raise ValidationError("Protective targets must use limit.")
        elif role == "manual_close" and order_type != "market":
            raise ValidationError("Manual closes must use market.")
        if role != "entry" and data.get("entry_price") is None:
            raise ValidationError(
                {"entry_price": ["Required for protective and manual-close orders."]}
            )


class BacktestFillSchema(SimulationSchema):
    """Immutable fill allocation stored as an extended Execution document."""

    user_id = fields.Raw(required=True)
    trade_account_id = fields.Raw(required=True)
    trade_id = fields.Raw(required=True)
    backtest_run_id = fields.Raw(required=True)
    backtest_order_id = fields.Raw(required=True)
    simulated_position_id = fields.Raw(required=True)
    symbol = fields.Str(required=True)
    raw_symbol = fields.Str(required=True)
    reset_generation = fields.Int(required=True, validate=validate.Range(min=0))
    simulation_operation_sequence = fields.Int(
        required=True, validate=validate.Range(min=0)
    )
    source_candle_index = fields.Int(required=True, validate=validate.Range(min=0))
    allocation_index = fields.Int(required=True, validate=validate.Range(min=0))
    time_ms = fields.Int(required=True, validate=validate.Range(min=0))
    timestamp = fields.DateTime(required=True)
    side = fields.Str(
        required=True,
        validate=validate.OneOf(["buy", "sell", "Buy", "Sell"]),
    )
    lots = LotSize(required=True)
    quantity = LotSize(required=True)
    reference_price = InstrumentPrice(required=True)
    fill_price = InstrumentPrice(required=True)
    price = InstrumentPrice(required=True)
    cost_profile_revision = fields.Int(required=True, validate=validate.Range(min=0))
    spread_cost = NonnegativeFiniteFloat(required=True)
    slippage_cost = NonnegativeFiniteFloat(required=True)
    commission = NonnegativeFiniteFloat(required=True)
    commission_usd = NonnegativeFiniteFloat(required=True)
    quote_currency = fields.Str(required=True, validate=validate.Length(min=3, max=8))
    native_gross_pnl = FiniteFloat(allow_none=True, load_default=None)
    usd_gross_pnl = FiniteFloat(allow_none=True, load_default=None)
    quote_to_usd_rate = PositiveFiniteFloat(allow_none=True, load_default=None)
    entry_exit = fields.Str(
        required=True, validate=validate.OneOf(["Entry", "Exit", "entry", "exit"])
    )
    order_type = fields.Str(
        required=True, validate=validate.OneOf(sorted(ORDER_TYPES))
    )


class BacktestPositionSchema(SimulationSchema):
    """Versioned projection of one run-owned open simulated position."""

    user_id = fields.Raw(required=True)
    run_id = fields.Raw(required=True)
    trade_account_id = fields.Raw(required=True)
    reset_generation = fields.Int(required=True, validate=validate.Range(min=0))
    position_id = fields.Raw(required=True)
    simulated_trade_id = fields.Raw(required=True)
    entity_version = fields.Int(required=True, validate=validate.Range(min=1))
    operation_sequence = fields.Int(required=True, validate=validate.Range(min=0))
    instrument = fields.Str(required=True)
    side = fields.Str(required=True, validate=validate.OneOf(sorted(POSITION_SIDES)))
    status = fields.Str(required=True, validate=validate.OneOf(sorted(POSITION_STATES)))
    remaining_lots = PositionLots(required=True)
    weighted_entry_price = InstrumentPrice(required=True)
    entry_fill_ids = fields.List(fields.Raw(), required=True)
    original_stop_loss_price = InstrumentPrice(required=True)
    original_take_profit_price = InstrumentPrice(required=True)
    stop_loss_order_id = fields.Raw(allow_none=True, load_default=None)
    take_profit_order_id = fields.Raw(allow_none=True, load_default=None)
    stop_loss_price = InstrumentPrice(allow_none=True, load_default=None)
    take_profit_price = InstrumentPrice(allow_none=True, load_default=None)
    stop_loss_eligible_source_index = fields.Int(
        allow_none=True, load_default=None, validate=validate.Range(min=0)
    )
    take_profit_eligible_source_index = fields.Int(
        allow_none=True, load_default=None, validate=validate.Range(min=0)
    )
    stop_loss_eligible_after_time_ms = fields.Int(
        allow_none=True, load_default=None, validate=validate.Range(min=0)
    )
    take_profit_eligible_after_time_ms = fields.Int(
        allow_none=True, load_default=None, validate=validate.Range(min=0)
    )
    initial_risk_native = PositiveFiniteFloat(required=True)
    initial_risk_usd = PositiveFiniteFloat(required=True)
    entry_quote_to_usd_rate = PositiveFiniteFloat(required=True)
    realized_partial_native_pnl = FiniteFloat(load_default=0.0)
    realized_partial_usd_pnl = FiniteFloat(load_default=0.0)
    applied_spread_cost = NonnegativeFiniteFloat(load_default=0.0)
    applied_slippage_cost = NonnegativeFiniteFloat(load_default=0.0)
    applied_commission_usd = NonnegativeFiniteFloat(load_default=0.0)
    tag_ids = fields.List(fields.Raw(), load_default=list)
    unrealized_pnl_usd = FiniteFloat(allow_none=True, load_default=None)
    opened_at = fields.DateTime(required=True)
    updated_at = fields.DateTime(required=True)

    @validates_schema
    def validate_position_state(self, data, **kwargs) -> None:
        if data["status"] == "open":
            if data["remaining_lots"] <= 0:
                raise ValidationError(
                    {"remaining_lots": ["Open positions require a positive remaining size."]}
                )
            for field_name in ("stop_loss_order_id", "take_profit_order_id"):
                if data.get(field_name) is None:
                    raise ValidationError(
                        {field_name: ["Open positions require both protection orders."]}
                    )
            for field_name in ("stop_loss_price", "take_profit_price"):
                if data.get(field_name) is None:
                    raise ValidationError(
                        {field_name: ["Open positions require both protection prices."]}
                    )
        elif data["remaining_lots"] != 0:
            raise ValidationError(
                {"remaining_lots": ["Closed positions must have zero remaining lots."]}
            )


class BacktestCostProfileSchema(SimulationSchema):
    """Immutable version of a run's execution-cost profile."""

    user_id = fields.Raw(required=True)
    run_id = fields.Raw(required=True)
    revision = fields.Int(required=True, validate=validate.Range(min=0))
    operation_sequence = fields.Int(required=True, validate=validate.Range(min=0))
    total_spread_pips = NonnegativeFiniteFloat(required=True)
    slippage_pips = NonnegativeFiniteFloat(required=True)
    commission_usd_per_lot_per_side = NonnegativeFiniteFloat(required=True)
    updated_at = fields.DateTime(required=True)


class SimulationOperationResponseSchema(SimulationSchema):
    """Stable response envelope for idempotent mutation requests."""

    client_operation_id = fields.Str(required=True)
    sequence = fields.Int(required=True, validate=validate.Range(min=0))
    state = fields.Str(required=True, validate=validate.OneOf(sorted(OPERATION_STATES)))
    control_revision = fields.Int(required=True, validate=validate.Range(min=0))
    result = fields.Dict(allow_none=True, load_default=None)


class SimulationStateResponseSchema(SimulationSchema):
    """Current committed simulation view returned to the replay UI."""

    committed_sequence = fields.Int(required=True, validate=validate.Range(min=0))
    control_revision = fields.Int(required=True, validate=validate.Range(min=0))
    reset_generation = fields.Int(required=True, validate=validate.Range(min=0))
    cursor = fields.Dict(required=True)
    pending_operation = fields.Bool(required=True)
    backward_navigation_locked = fields.Bool(required=True)
    initial_balance_usd = PositiveFiniteFloat(required=True)
    risk_percent = PositiveFiniteFloat(required=True)
    current_balance_usd = FiniteFloat(required=True)
    mark_price = FiniteFloat(allow_none=True, load_default=None)
    current_quote_to_usd_rate = PositiveFiniteFloat(allow_none=True, load_default=None)
    cost_profile = fields.Nested(BacktestCostProfileSchema, required=True)
    orders = fields.List(fields.Nested(BacktestOrderSchema), required=True)
    fills = fields.List(fields.Nested(BacktestFillSchema), required=True)
    positions = fields.List(fields.Nested(BacktestPositionSchema), required=True)
    closed_trades = fields.List(fields.Dict(), required=True)
    status = fields.Str(required=True, validate=validate.OneOf(["ready", "complete"]))


def make_simulation_operation_doc(
    *,
    user_id,
    run_id,
    client_operation_id: str,
    sequence: int,
    control_revision: int,
    reset_generation: int,
    kind: str,
    request: dict[str, Any],
    created_at,
    state: str = "pending",
    final_state: str | None = None,
    result: dict[str, Any] | None = None,
    commit_updates: dict[str, Any] | None = None,
    committed_at=None,
    operation_id=None,
) -> dict[str, Any]:
    """Build one durable operation-journal document."""
    return {
        "_id": operation_id or ObjectId(),
        "user_id": user_id,
        "run_id": run_id,
        "client_operation_id": client_operation_id,
        "sequence": sequence,
        "control_revision": control_revision,
        "reset_generation": reset_generation,
        "kind": kind,
        "state": state,
        "final_state": final_state,
        "request": request,
        "result": result,
        "commit_updates": commit_updates,
        "created_at": created_at,
        "committed_at": committed_at,
    }


def make_order_version_doc(
    *,
    user_id,
    run_id,
    reset_generation: int,
    order_id,
    operation_sequence: int,
    entity_version: int,
    document_id=None,
    **order_fields,
) -> dict[str, Any]:
    """Build a versioned order record with a stable logical order id."""
    document = dict(order_fields)
    document.update(
        {
            "_id": document_id or ObjectId(),
            "user_id": user_id,
            "run_id": run_id,
            "reset_generation": reset_generation,
            "order_id": order_id,
            "operation_sequence": operation_sequence,
            "entity_version": entity_version,
        }
    )
    return document


def make_fill_doc(*, fill_id=None, **fill_fields) -> dict[str, Any]:
    """Build one immutable Backtest allocation as an Execution document."""
    document = dict(fill_fields)
    document["_id"] = fill_id or ObjectId()
    return document


def make_position_version_doc(
    *,
    user_id,
    run_id,
    reset_generation: int,
    position_id,
    operation_sequence: int,
    entity_version: int,
    document_id=None,
    **position_fields,
) -> dict[str, Any]:
    """Build a version of the stable position projection."""
    document = dict(position_fields)
    document.update(
        {
            "_id": document_id or ObjectId(),
            "user_id": user_id,
            "run_id": run_id,
            "reset_generation": reset_generation,
            "position_id": position_id,
            "operation_sequence": operation_sequence,
            "entity_version": entity_version,
        }
    )
    return document


def make_cost_profile_doc(
    *,
    user_id,
    run_id,
    revision: int,
    operation_sequence: int,
    total_spread_pips: float,
    slippage_pips: float,
    commission_usd_per_lot_per_side: float,
    updated_at,
    profile_id=None,
) -> dict[str, Any]:
    """Build one immutable cost profile revision."""
    return {
        "_id": profile_id or ObjectId(),
        "user_id": user_id,
        "run_id": run_id,
        "revision": revision,
        "operation_sequence": operation_sequence,
        "total_spread_pips": total_spread_pips,
        "slippage_pips": slippage_pips,
        "commission_usd_per_lot_per_side": commission_usd_per_lot_per_side,
        "updated_at": updated_at,
    }


def make_default_cost_profile(
    user_id, run_id, *, now, execution_costs: dict[str, float] | None = None
) -> dict[str, Any]:
    """Build revision zero from the execution costs frozen on run creation."""
    costs = execution_costs or {}
    return make_cost_profile_doc(
        user_id=user_id,
        run_id=run_id,
        revision=0,
        operation_sequence=0,
        total_spread_pips=float(costs.get("total_spread_pips", 0.0)),
        slippage_pips=float(costs.get("slippage_pips", 0.0)),
        commission_usd_per_lot_per_side=float(
            costs.get("commission_usd_per_lot_per_side", 0.0)
        ),
        updated_at=now,
    )
