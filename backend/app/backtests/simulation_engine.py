"""Deterministic, runtime-independent rules for simulated Backtest orders."""

from __future__ import annotations

from decimal import (
    Decimal,
    InvalidOperation,
    ROUND_CEILING,
    ROUND_DOWN,
    ROUND_FLOOR,
    ROUND_HALF_UP,
)
import math
from typing import Any, Mapping


LOT_INCREMENT = Decimal("0.001")
MIN_LOTS = LOT_INCREMENT


class SimulationRuleError(ValueError):
    """An order or fill violates the frozen run's trading rules."""


def _decimal(value: Any, field_name: str) -> Decimal:
    if isinstance(value, bool):
        raise SimulationRuleError(f"{field_name} must be a finite number.")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise SimulationRuleError(
            f"{field_name} must be a finite number."
        ) from exc
    if not result.is_finite():
        raise SimulationRuleError(f"{field_name} must be a finite number.")
    return result


def _precision(metadata: Mapping[str, Any]) -> int:
    value = metadata.get("price_precision")
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 15:
        raise SimulationRuleError("Run instrument precision is invalid.")
    return value


def _positive_metadata_decimal(metadata: Mapping[str, Any], field: str) -> Decimal:
    value = _decimal(metadata.get(field), field)
    if value <= 0:
        raise SimulationRuleError(f"Run instrument {field} must be positive.")
    return value


def validate_price(value: Any, metadata: Mapping[str, Any], field_name: str) -> Decimal:
    """Validate a finite price at frozen instrument precision; negatives are valid."""
    price = _decimal(value, field_name)
    precision = _precision(metadata)
    scaled = price.scaleb(precision)
    rounded = price.quantize(Decimal(1).scaleb(-precision))
    if scaled != scaled.to_integral_value():
        value_as_float = None
        try:
            value_as_float = float(price)
            tolerance = max(
                math.ulp(value_as_float) * 2,
                10 ** -(precision + 8),
            )
        except (OverflowError, ValueError):
            tolerance = 0.0
        if (
            value_as_float is not None
            and math.isfinite(value_as_float)
            and abs(float(price - rounded)) <= tolerance
        ):
            return rounded
        raise SimulationRuleError(
            f"{field_name} must use no more than {precision} decimal places."
        )
    return rounded


def validate_market_data_price(value: Any, field_name: str) -> Decimal:
    """Validate raw source OHLC without imposing an executable tick size."""
    return _decimal(value, field_name)


def normalize_market_reference_price(
    value: Any, metadata: Mapping[str, Any], field_name: str
) -> Decimal:
    """Round a source midpoint to the frozen instrument precision for sizing."""
    price = validate_market_data_price(value, field_name)
    tick = Decimal(1).scaleb(-_precision(metadata))
    return price.quantize(tick, rounding=ROUND_HALF_UP)


def validate_lots(value: Any) -> Decimal:
    """Require the minimum 0.001 lot and exact 0.001 increments."""
    lots = _decimal(value, "lots")
    if lots < MIN_LOTS:
        raise SimulationRuleError("Lots must be at least 0.001.")
    if lots % LOT_INCREMENT != 0:
        raise SimulationRuleError("Lots must be in 0.001 increments.")
    return lots


def validate_entry_bracket(
    side: str,
    reference_price: Any,
    stop_loss: Any,
    take_profit: Any,
    metadata: Mapping[str, Any],
) -> tuple[Decimal, Decimal, Decimal]:
    """Validate entry and both protective levels using long/short orientation."""
    entry = validate_price(reference_price, metadata, "entry_price")
    stop = validate_price(stop_loss, metadata, "stop_loss")
    target = validate_price(take_profit, metadata, "take_profit")
    normalized_side = str(side).lower()
    if normalized_side in {"buy", "long"}:
        valid = stop < entry < target
    elif normalized_side in {"sell", "short"}:
        valid = target < entry < stop
    else:
        raise SimulationRuleError("Side must be buy/long or sell/short.")
    if not valid:
        raise SimulationRuleError(
            "Stop-loss and take-profit must be on the correct sides of entry."
        )
    return entry, stop, target


def default_bracket_for_budget(
    *,
    side: str,
    entry_price: Any,
    risk_budget_usd: Any,
    quote_to_usd_rate: Any,
    metadata: Mapping[str, Any],
) -> dict[str, float]:
    """Derive the one-standard-lot stop distance and a symmetric 1R target."""
    entry = validate_price(entry_price, metadata, "entry_price")
    budget = _decimal(risk_budget_usd, "risk_budget_usd")
    rate = _decimal(quote_to_usd_rate, "quote_to_usd_rate")
    if budget <= 0 or rate <= 0:
        raise SimulationRuleError("Risk budget and conversion rate must be positive.")
    contract_size = _positive_metadata_decimal(metadata, "contract_size")
    precision = _precision(metadata)
    tick = Decimal(1).scaleb(-precision)

    # The documented pip formula simplifies to budget / (contract * rate).
    # Round the distance outward to a valid tick so the preview never uses a
    # tighter stop than the risk budget implies.
    distance = (budget / (contract_size * rate)).quantize(
        tick, rounding=ROUND_CEILING
    )
    if distance <= 0:
        distance = tick
    normalized_side = str(side).lower()
    if normalized_side in {"buy", "long"}:
        stop, target = entry - distance, entry + distance
    elif normalized_side in {"sell", "short"}:
        stop, target = entry + distance, entry - distance
    else:
        raise SimulationRuleError("Side must be buy/long or sell/short.")
    _, stop, target = validate_entry_bracket(
        normalized_side, entry, stop, target, metadata
    )
    return {"stop_loss": float(stop), "take_profit": float(target)}


def _cost_values(cost_profile: Mapping[str, Any] | None) -> tuple[Decimal, Decimal, Decimal]:
    costs = cost_profile or {}
    spread = _decimal(costs.get("total_spread_pips", 0), "total_spread_pips")
    slippage = _decimal(costs.get("slippage_pips", 0), "slippage_pips")
    commission = _decimal(
        costs.get("commission_usd_per_lot_per_side", 0),
        "commission_usd_per_lot_per_side",
    )
    if spread < 0 or slippage < 0 or commission < 0:
        raise SimulationRuleError("Execution costs cannot be negative.")
    return spread, slippage, commission


def projected_risk_per_lot_usd(
    *,
    entry_price: Any,
    stop_loss: Any,
    quote_to_usd_rate: Any,
    metadata: Mapping[str, Any],
    cost_profile: Mapping[str, Any] | None = None,
) -> Decimal:
    """Estimate stop loss plus round-trip spread, slippage, and commission."""
    entry = validate_price(entry_price, metadata, "entry_price")
    stop = validate_price(stop_loss, metadata, "stop_loss")
    rate = _decimal(quote_to_usd_rate, "quote_to_usd_rate")
    if rate <= 0:
        raise SimulationRuleError("quote_to_usd_rate must be positive.")
    pip_size = _positive_metadata_decimal(metadata, "pip_size")
    contract_size = _positive_metadata_decimal(metadata, "contract_size")
    spread, slippage, commission = _cost_values(cost_profile)

    movement_quote = abs(entry - stop) * contract_size
    cost_pips = spread + (slippage * 2)
    execution_cost_quote = cost_pips * pip_size * contract_size
    return (movement_quote + execution_cost_quote) * rate + commission * 2


def projected_risk_usd(
    *,
    lots: Any,
    entry_price: Any,
    stop_loss: Any,
    quote_to_usd_rate: Any,
    metadata: Mapping[str, Any],
    cost_profile: Mapping[str, Any] | None = None,
) -> Decimal:
    quantity = validate_lots(lots)
    return projected_risk_per_lot_usd(
        entry_price=entry_price,
        stop_loss=stop_loss,
        quote_to_usd_rate=quote_to_usd_rate,
        metadata=metadata,
        cost_profile=cost_profile,
    ) * quantity


def auto_size_lots(
    *,
    risk_budget_usd: Any,
    entry_price: Any,
    stop_loss: Any,
    quote_to_usd_rate: Any,
    metadata: Mapping[str, Any],
    cost_profile: Mapping[str, Any] | None = None,
) -> Decimal:
    """Size down to 0.001 lots; reject if the minimum exceeds the budget."""
    budget = _decimal(risk_budget_usd, "risk_budget_usd")
    if budget <= 0:
        raise SimulationRuleError("Risk budget must be positive.")
    per_lot = projected_risk_per_lot_usd(
        entry_price=entry_price,
        stop_loss=stop_loss,
        quote_to_usd_rate=quote_to_usd_rate,
        metadata=metadata,
        cost_profile=cost_profile,
    )
    lots = (budget / per_lot).quantize(LOT_INCREMENT, rounding=ROUND_DOWN)
    if lots < MIN_LOTS:
        raise SimulationRuleError(
            "The minimum 0.001 lot would exceed the selected risk budget."
        )
    return lots


def entry_order_fill(
    order: Mapping[str, Any],
    candle: Mapping[str, Any],
    source_index: int,
    *,
    metadata: Mapping[str, Any],
    cost_profile: Mapping[str, Any] | None = None,
) -> dict[str, float | str] | None:
    """Return an eligible entry fill without reading unrevealed OHLC early."""
    if order.get("status") != "pending":
        return None
    eligible = order.get("eligible_source_index")
    if isinstance(eligible, bool) or not isinstance(eligible, int):
        raise SimulationRuleError("Entry order eligibility index is invalid.")
    if source_index < eligible:
        return None

    order_type = order.get("order_type")
    if order_type == "market":
        reference = validate_market_data_price(candle.get("open"), "open")
        return adjusted_market_fill(
            reference,
            str(order.get("side")),
            lots=order.get("lots"),
            metadata=metadata,
            cost_profile=cost_profile,
        )
    if order_type != "limit":
        raise SimulationRuleError("Entry orders support market or limit only.")

    limit_price = validate_price(order.get("entry_price"), metadata, "entry_price")
    low = validate_market_data_price(candle.get("low"), "low")
    high = validate_market_data_price(candle.get("high"), "high")
    if low > high:
        raise SimulationRuleError("Candle low cannot exceed candle high.")
    if low <= limit_price <= high:
        return adjusted_limit_fill(
            limit_price,
            str(order.get("side")),
            lots=order.get("lots"),
            metadata=metadata,
            cost_profile=cost_profile,
        )
    return None


def adjusted_market_fill(
    reference_price: Any,
    side: str,
    *,
    lots: Any,
    metadata: Mapping[str, Any],
    cost_profile: Mapping[str, Any] | None = None,
) -> dict[str, float | str]:
    """Apply adverse half-spread and slippage to a market/stop reference."""
    return _adjusted_fill(
        reference_price,
        side,
        lots=lots,
        metadata=metadata,
        cost_profile=cost_profile,
        preserve_price=False,
    )


def adjusted_limit_fill(
    reference_price: Any,
    side: str,
    *,
    lots: Any,
    metadata: Mapping[str, Any],
    cost_profile: Mapping[str, Any] | None = None,
) -> dict[str, float | str]:
    """Keep exact submitted limit price; retain costs as separate amounts."""
    return _adjusted_fill(
        reference_price,
        side,
        lots=lots,
        metadata=metadata,
        cost_profile=cost_profile,
        preserve_price=True,
    )


def _adjusted_fill(
    reference_price: Any,
    side: str,
    *,
    lots: Any,
    metadata: Mapping[str, Any],
    cost_profile: Mapping[str, Any] | None,
    preserve_price: bool,
) -> dict[str, float | str]:
    quantity = validate_lots(lots)
    normalized_side = str(side).lower()
    if normalized_side not in {"buy", "sell"}:
        raise SimulationRuleError("Fill side must be buy or sell.")
    source_reference = (
        _decimal(reference_price, "reference_price")
        if not preserve_price
        else validate_price(reference_price, metadata, "reference_price")
    )
    pip_size = _positive_metadata_decimal(metadata, "pip_size")
    contract_size = _positive_metadata_decimal(metadata, "contract_size")
    precision = _precision(metadata)
    tick = Decimal(1).scaleb(-precision)
    reference = (
        source_reference.quantize(
            tick,
            rounding=ROUND_CEILING if normalized_side == "buy" else ROUND_FLOOR,
        )
        if not preserve_price
        else source_reference
    )
    spread, slippage, commission = _cost_values(cost_profile)
    spread_offset = spread * pip_size / 2
    slippage_offset = slippage * pip_size
    total_offset = spread_offset + slippage_offset
    if preserve_price:
        fill_price = reference
    elif normalized_side == "buy":
        fill_price = (source_reference + total_offset).quantize(
            tick, rounding=ROUND_CEILING
        )
    else:
        fill_price = (source_reference - total_offset).quantize(
            tick, rounding=ROUND_FLOOR
        )

    spread_cost = spread_offset * contract_size * quantity
    slippage_cost = slippage_offset * contract_size * quantity
    commission_usd = commission * quantity
    return {
        "side": normalized_side,
        "reference_price": float(reference),
        "fill_price": float(fill_price),
        "spread_cost": float(spread_cost),
        "slippage_cost": float(slippage_cost),
        "commission_usd": float(commission_usd),
    }


def protective_exit_fill(
    position: Mapping[str, Any],
    candle: Mapping[str, Any],
    source_index: int,
    *,
    metadata: Mapping[str, Any],
    cost_profile: Mapping[str, Any] | None = None,
) -> dict[str, float | str] | None:
    """Evaluate eligible OCO protection; stop wins if both levels are touched."""
    side = str(position.get("side", "")).lower()
    if side not in {"long", "short"} or position.get("status", "open") != "open":
        return None
    stop_index = position.get("stop_loss_eligible_source_index", 0)
    target_index = position.get("take_profit_eligible_source_index", 0)
    if source_index < min(stop_index, target_index):
        return None

    stop = position.get("stop_loss_price")
    target = position.get("take_profit_price")
    if stop is None or target is None:
        raise SimulationRuleError("Open positions require both protections.")
    stop_price = validate_price(stop, metadata, "stop_loss")
    target_price = validate_price(target, metadata, "take_profit")
    opening = validate_market_data_price(candle.get("open"), "open")
    high = validate_market_data_price(candle.get("high"), "high")
    low = validate_market_data_price(candle.get("low"), "low")
    if low > high:
        raise SimulationRuleError("Candle low cannot exceed candle high.")

    if side == "long":
        stop_hit = low <= stop_price and source_index >= stop_index
        target_hit = high >= target_price and source_index >= target_index
        if stop_hit:
            reference = opening if opening < stop_price else stop_price
            return {
                **adjusted_market_fill(
                    reference,
                    "sell",
                    lots=position.get("remaining_lots"),
                    metadata=metadata,
                    cost_profile=cost_profile,
                ),
                "exit_role": "protective_stop",
            }
        if target_hit:
            return {
                **adjusted_limit_fill(
                    target_price,
                    "sell",
                    lots=position.get("remaining_lots"),
                    metadata=metadata,
                    cost_profile=cost_profile,
                ),
                "exit_role": "protective_target",
            }
    else:
        stop_hit = high >= stop_price and source_index >= stop_index
        target_hit = low <= target_price and source_index >= target_index
        if stop_hit:
            reference = opening if opening > stop_price else stop_price
            return {
                **adjusted_market_fill(
                    reference,
                    "buy",
                    lots=position.get("remaining_lots"),
                    metadata=metadata,
                    cost_profile=cost_profile,
                ),
                "exit_role": "protective_stop",
            }
        if target_hit:
            return {
                **adjusted_limit_fill(
                    target_price,
                    "buy",
                    lots=position.get("remaining_lots"),
                    metadata=metadata,
                    cost_profile=cost_profile,
                ),
                "exit_role": "protective_target",
            }
    return None


def allocate_opposing_fill_fifo(
    incoming_side: str,
    incoming_lots: Any,
    positions: list[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], Decimal]:
    """Plan FIFO reductions and return any excess for a reverse position."""
    side = str(incoming_side).lower()
    if side not in {"buy", "sell"}:
        raise SimulationRuleError("Fill side must be buy or sell.")
    remaining = validate_lots(incoming_lots)
    opposing_position_side = "short" if side == "buy" else "long"
    candidates = [
        position
        for position in positions
        if position.get("status", "open") == "open"
        and str(position.get("side", "")).lower() == opposing_position_side
        and _decimal(position.get("remaining_lots"), "remaining_lots") > 0
    ]
    candidates.sort(
        key=lambda position: (
            position.get("opened_sequence", position.get("operation_sequence", 0)),
            str(position.get("position_id", position.get("_id", ""))),
        )
    )
    allocations: list[dict[str, Any]] = []
    for position in candidates:
        if remaining <= 0:
            break
        available = _decimal(position["remaining_lots"], "remaining_lots")
        allocated = min(available, remaining)
        allocated = allocated.quantize(LOT_INCREMENT, rounding=ROUND_DOWN)
        if allocated <= 0:
            continue
        allocations.append(
            {
                "position_id": position.get("position_id", position.get("_id")),
                "lots": float(allocated),
            }
        )
        remaining -= allocated
    return allocations, remaining


def realized_native_pnl(
    *, side: str, entry_price: Any, exit_price: Any, lots: Any, metadata: Mapping[str, Any]
) -> Decimal:
    """Compute quote-currency gross P&L before separately accounted costs."""
    entry = validate_price(entry_price, metadata, "entry_price")
    exit_value = validate_price(exit_price, metadata, "exit_price")
    quantity = validate_lots(lots)
    contract_size = _positive_metadata_decimal(metadata, "contract_size")
    normalized_side = str(side).lower()
    if normalized_side in {"long", "buy"}:
        direction = Decimal(1)
    elif normalized_side in {"short", "sell"}:
        direction = Decimal(-1)
    else:
        raise SimulationRuleError("Side must be long/buy or short/sell.")
    return (exit_value - entry) * direction * contract_size * quantity
