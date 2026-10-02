"""Deterministic run-scoped effects for simulated Backtest trading.

Handlers stage versioned documents before the run-level sequence is committed.
Every document id is derived from the durable operation id, so a worker can
repeat an interrupted handler without publishing duplicate fills or trades.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
import math
from typing import Any, Mapping

from bson import ObjectId

from app.backtests.fx_conversion import (
    FXConversionUnavailable,
    build_conversion_spec,
    resolve_conversion_route_rate,
)
from app.backtests.repository import BacktestRepository
from app.backtests.simulation_engine import (
    SimulationRuleError,
    adjusted_market_fill,
    allocate_opposing_fill_fifo,
    auto_size_lots,
    default_bracket_for_budget,
    entry_order_fill,
    normalize_market_reference_price,
    protective_exit_fill,
    projected_risk_usd,
    realized_native_pnl,
    validate_entry_bracket,
    validate_lots,
    validate_price,
)
from app.backtests.simulation_repository import BacktestSimulationRepository
from app.backtests.simulation_schemas import (
    make_cost_profile_doc,
    make_default_cost_profile,
    make_fill_doc,
    make_order_version_doc,
    make_position_version_doc,
)
from app.extensions import mongo
from app.models.tag import create_tag_doc
from app.models.trade import create_trade_doc
from app.repositories.tag_repo import TagRepository
from app.tags.categories import ensure_tag_categories
from app.utils.datetime_utils import utc_now
from app.utils.errors import ConflictError, NotFoundError, ValidationError
from app.backtests.simulation_service import SimulationRejected


def _stable_oid(*parts: Any) -> ObjectId:
    """Return the same valid BSON id for the same logical effect."""
    value = "|".join(str(part) for part in parts)
    return ObjectId(sha256(value.encode("utf-8")).hexdigest()[:24])


def _as_oid(value: Any, field: str) -> ObjectId:
    if isinstance(value, ObjectId):
        return value
    if ObjectId.is_valid(value):
        return ObjectId(value)
    raise ValidationError(f"{field} is invalid.")


def _as_float(value: Any, field: str) -> float:
    if isinstance(value, bool):
        raise SimulationRuleError(f"{field} must be finite.")
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise SimulationRuleError(f"{field} must be finite.") from exc
    if not math.isfinite(result):
        raise SimulationRuleError(f"{field} must be finite.")
    return result


def _utc_datetime(time_ms: int) -> datetime:
    return datetime.fromtimestamp(time_ms / 1000, tz=timezone.utc)


def _normalize_utc_datetime(value: datetime) -> datetime:
    """Treat database datetimes without tzinfo as UTC for mixed-fill math."""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


class BacktestSimulationEffects:
    """Apply validated simulation commands to one immutable run snapshot."""

    def __init__(
        self,
        backtest_repository: BacktestRepository | None = None,
        simulation_repository: BacktestSimulationRepository | None = None,
        snapshot_store=None,
    ) -> None:
        self.backtest_repository = backtest_repository or BacktestRepository()
        self.simulation_repository = (
            simulation_repository or BacktestSimulationRepository()
        )
        if snapshot_store is None:
            from app.backtests.snapshot_store import SnapshotStore

            snapshot_store = SnapshotStore()
        self.snapshot_store = snapshot_store

    @property
    def database(self):
        return self.simulation_repository.database

    def apply_operation(self, operation: dict, run: dict) -> dict[str, Any]:
        """Dispatch one operation to a deterministic, retry-safe effect."""
        kind = operation.get("kind")
        request = operation.get("request") or {}
        try:
            if kind == "submit_order":
                return self._submit_order(operation, run, request)
            if kind == "cancel_order":
                return self._cancel_order(operation, run, request)
            if kind == "close_position":
                return self._close_position(operation, run, request)
            if kind == "modify_protection":
                return self._modify_protection(operation, run, request)
            if kind == "update_risk":
                return self._update_risk(operation, run, request)
            if kind == "update_costs":
                return self._update_costs(operation, run, request)
            if kind == "advance":
                return self._advance(operation, run, request)
            if kind == "rewind":
                return self._rewind(operation, run, request)
            if kind == "reset":
                return self._reset(operation, run)
            raise SimulationRuleError("Unsupported simulation operation.")
        except (SimulationRuleError, FXConversionUnavailable) as exc:
            raise SimulationRejected(str(exc)) from exc

    def cleanup_generation(self, operation: dict, run: dict, old_generation: int):
        """Idempotently purge one prior generation after reset fencing."""
        self.simulation_repository.delete_generation_data(
            operation["user_id"], operation["run_id"], old_generation
        )

    def get_state(self, user_id: str, run_id) -> dict[str, Any]:
        """Build the current owner-scoped committed simulation projection."""
        run = self.backtest_repository.find_owned_run(user_id, run_id)
        if run is None:
            raise NotFoundError("Backtest run not found.")
        if run.get("status") not in {"ready", "complete"} or not run.get("snapshot"):
            raise ConflictError("Backtest run is not ready for simulation.")
        run = self.backtest_repository.ensure_simulation_control(user_id, run_id)
        control = (run or {}).get("simulation_control") or {}
        sequence = int(control.get("committed_sequence", 0))
        generation = int(control.get("reset_generation", 0))
        cursor = run.get("replay_cursor") or {}
        profile = self.simulation_repository.find_visible_cost_profile(
            user_id,
            run_id,
            committed_sequence=sequence,
            execution_costs=run.get("execution_costs"),
        )
        if profile is None:
            profile = make_default_cost_profile(
                ObjectId(user_id),
                ObjectId(run["_id"]),
                now=utc_now(),
                execution_costs=run.get("execution_costs"),
            )

        orders = self.simulation_repository.list_visible_orders(
            user_id,
            run_id,
            reset_generation=generation,
            committed_sequence=sequence,
            limit=500,
        )
        positions = self.simulation_repository.list_visible_positions(
            user_id,
            run_id,
            reset_generation=generation,
            committed_sequence=sequence,
            open_only=True,
            limit=500,
        )
        fills = self.simulation_repository.list_visible_fills(
            user_id,
            run_id,
            reset_generation=generation,
            committed_sequence=sequence,
            limit=500,
        )
        closed_trades = list(
            self.database.trades.find(
                {
                    "user_id": ObjectId(user_id),
                    "backtest_run_id": ObjectId(run["_id"]),
                    "simulation_generation": generation,
                    "simulation_operation_sequence": {"$lte": sequence},
                    "status": "closed",
                }
            ).sort([("exit_time", -1), ("_id", -1)]).limit(500)
        )

        current_candle = self._candle_at(run, cursor.get("source_candle_index"))
        current_quote_to_usd_rate = None
        if current_candle is not None:
            metadata = run.get("instrument_metadata") or {}
            if metadata.get("supported_for_simulation"):
                try:
                    current_quote_to_usd_rate = self._quote_rate(
                        run, metadata, int(current_candle["time_ms"]) + 60_000
                    )
                except (SimulationRuleError, FXConversionUnavailable):
                    current_quote_to_usd_rate = None
                for position in positions:
                    try:
                        rate = current_quote_to_usd_rate
                        if rate is None:
                            raise FXConversionUnavailable(
                                str(metadata.get("quote_currency", "")),
                                int(current_candle["time_ms"]) + 60_000,
                            )
                        native = realized_native_pnl(
                            side=position["side"],
                            entry_price=position.get(
                                "weighted_reference_price",
                                position["weighted_entry_price"],
                            ),
                            exit_price=normalize_market_reference_price(
                                current_candle["close"], metadata, "close"
                            ),
                            lots=position["remaining_lots"],
                            metadata=metadata,
                        )
                        entry_cost_usd = float(
                            position.get("entry_spread_slippage_usd_remaining", 0.0)
                        )
                        position["unrealized_pnl_usd"] = float(native) * rate - entry_cost_usd
                    except (SimulationRuleError, FXConversionUnavailable):
                        position["unrealized_pnl_usd"] = None
            else:
                for position in positions:
                    position["unrealized_pnl_usd"] = None

        return {
            "committed_sequence": sequence,
            "control_revision": int(control.get("control_revision", 0)),
            "reset_generation": generation,
            "cursor": cursor,
            "pending_operation": control.get("pending_operation_id") is not None,
            "backward_navigation_locked": bool(control.get("has_accepted_order")),
            "initial_balance_usd": float(run.get("initial_balance_usd", 10_000.0)),
            "risk_percent": float(
                run.get("simulation_risk_percent", run.get("risk_percent", 1.0))
            ),
            "current_balance_usd": float(
                run.get("current_balance_usd", run.get("initial_balance_usd", 10_000.0))
            ),
            "current_quote_to_usd_rate": current_quote_to_usd_rate,
            "cost_profile": profile,
            "orders": orders,
            "fills": fills,
            "positions": positions,
            "closed_trades": closed_trades,
            "status": run.get("status", "ready"),
        }

    def _metadata(self, run: dict) -> dict[str, Any]:
        metadata = run.get("instrument_metadata")
        if not isinstance(metadata, dict):
            raise SimulationRuleError(
                "This run's instrument has no frozen simulation sizing metadata."
            )
        if not metadata.get("supported_for_simulation"):
            raise SimulationRuleError(
                metadata.get("reason")
                or "This run's instrument has no frozen simulation sizing metadata."
            )
        required = (
            "price_precision", "pip_size", "contract_size", "quote_currency"
        )
        if metadata.get("spec_version"):
            required += ("tick_size", "min_lots", "lot_increment")
        if any(metadata.get(field) is None for field in required):
            raise SimulationRuleError("Run instrument metadata is incomplete.")
        return metadata

    def _snapshot_range(self, run: dict, first: int, last: int) -> list[dict[str, Any]]:
        """Read only day partitions intersecting a source-index range."""
        if first > last:
            return []
        snapshot = run.get("snapshot") or {}
        indexed_days = snapshot.get("_day_candle_indexes")
        rows: list[dict[str, Any]] = []
        if isinstance(indexed_days, list):
            for item in indexed_days:
                day_first = int(item["first_source_candle_index"])
                count = int(item["candle_count"])
                day_last = day_first + count - 1
                if day_last < first or day_first > last:
                    continue
                frame = self.snapshot_store.read_snapshot_day(
                    snapshot, item["utc_date"]
                ).sort_values("time_ms", kind="stable")
                lower = max(first, day_first) - day_first
                upper = min(last, day_last) - day_first
                values = frame.iloc[lower : upper + 1]
                for offset, candle in enumerate(values.itertuples(index=False)):
                    rows.append(
                        {
                            "source_candle_index": day_first + lower + offset,
                            "time_ms": int(candle.time_ms),
                            "open": float(candle.open),
                            "high": float(candle.high),
                            "low": float(candle.low),
                            "close": float(candle.close),
                            "volume": float(candle.volume),
                        }
                    )
        else:
            frame = self.snapshot_store.read_snapshot(snapshot["object_key"]).sort_values(
                "time_ms", kind="stable"
            )
            values = frame.iloc[first : last + 1]
            for source_index, candle in enumerate(values.itertuples(index=False), start=first):
                rows.append(
                    {
                        "source_candle_index": source_index,
                        "time_ms": int(candle.time_ms),
                        "open": float(candle.open),
                        "high": float(candle.high),
                        "low": float(candle.low),
                        "close": float(candle.close),
                        "volume": float(candle.volume),
                    }
                )
        rows.sort(key=lambda item: item["source_candle_index"])
        if rows and (
            rows[0]["source_candle_index"] != first
            or rows[-1]["source_candle_index"] != last
            or len(rows) != last - first + 1
        ):
            raise SimulationRuleError("The requested source candles are unavailable.")
        return rows

    def _candle_at(self, run: dict, source_index: Any) -> dict | None:
        if isinstance(source_index, bool) or not isinstance(source_index, int):
            return None
        rows = self._snapshot_range(run, source_index, source_index)
        return rows[0] if rows else None

    def _source_bounds(self, run: dict) -> tuple[int, int]:
        snapshot = run.get("snapshot") or {}
        count = snapshot.get("candle_count")
        if isinstance(count, bool) or not isinstance(count, int) or count < 1:
            raise SimulationRuleError("The immutable run snapshot is unavailable.")
        first = int(snapshot.get("replay_start_source_index", 0))
        return first, count - 1

    def _validate_cursor(self, run: dict, index: Any, time_ms: Any) -> dict:
        first, last = self._source_bounds(run)
        if (
            isinstance(index, bool)
            or not isinstance(index, int)
            or index < first
            or index > last
            or isinstance(time_ms, bool)
            or not isinstance(time_ms, int)
            or time_ms < 0
        ):
            raise SimulationRuleError("Replay cursor is outside the selected snapshot.")
        candle_time = self.snapshot_store.read_snapshot_candle_time(
            run["snapshot"], index
        )
        if candle_time is None or int(candle_time) != time_ms:
            raise SimulationRuleError("Replay cursor does not identify a snapshot candle.")
        return {"source_candle_index": index, "time_ms": time_ms}

    def _current_candle(self, run: dict) -> dict:
        cursor = run.get("replay_cursor") or {}
        candle = self._candle_at(run, cursor.get("source_candle_index"))
        if candle is None or candle.get("time_ms") != cursor.get("time_ms"):
            raise SimulationRuleError("The current replay candle is unavailable.")
        return candle

    def _quote_rate(self, run: dict, metadata: dict, event_time_ms: int) -> float:
        quote = str(metadata.get("quote_currency", "")).upper()
        snapshot = run.get("snapshot") or {}
        spec = metadata.get("conversion_spec")
        if not isinstance(spec, dict):
            reference = next(
                (
                    item
                    for item in snapshot.get("fx_conversion_series", [])
                    if str(item.get("quote_currency", "")).upper() == quote
                ),
                None,
            )
            spec = reference or build_conversion_spec(quote)
        if not spec or not spec.get("supported"):
            raise FXConversionUnavailable(quote, event_time_ms)
        route = spec.get("route")
        if not isinstance(route, list):
            route = (
                [{
                    "instrument": spec.get("instrument"),
                    "direction": spec.get("direction"),
                    "from_currency": quote,
                    "to_currency": "USD",
                }]
                if spec.get("instrument")
                and spec.get("direction") in {"direct", "inverse"}
                else []
            )
        observations_by_instrument = {
            str(leg.get("instrument", "")).upper():
                self.snapshot_store.read_fx_conversion_series(
                    snapshot, str(leg.get("instrument", ""))
                )
            for leg in route
            if isinstance(leg, dict) and leg.get("instrument")
        }
        return resolve_conversion_route_rate(
            quote,
            int(event_time_ms),
            route,
            observations_by_instrument,
            quote_currency_unit_scale=float(
                spec.get("quote_currency_unit_scale", 1.0)
            ),
        )

    def _profile(self, run: dict, *, sequence: int | None = None) -> dict:
        sequence = (
            int((run.get("simulation_control") or {}).get("committed_sequence", 0))
            if sequence is None
            else sequence
        )
        profile = self.simulation_repository.find_visible_cost_profile(
            run["user_id"],
            run["_id"],
            committed_sequence=sequence,
            execution_costs=run.get("execution_costs"),
        )
        return profile or make_default_cost_profile(
            run["user_id"],
            run["_id"],
            now=utc_now(),
            execution_costs=run.get("execution_costs"),
        )

    def _context(self, operation: dict, run: dict) -> dict[str, Any]:
        metadata = self._metadata(run)
        cursor = run.get("replay_cursor") or {}
        candle = self._current_candle(run)
        return {
            "user_id": _as_oid(run["user_id"], "user_id"),
            "run_id": _as_oid(run["_id"], "run_id"),
            "account_id": _as_oid(run.get("account_id"), "account_id"),
            "metadata": metadata,
            "cursor_index": int(cursor["source_candle_index"]),
            "cursor_time_ms": int(cursor["time_ms"]),
            "candle": candle,
            "sequence": int(operation["sequence"]),
            "generation": int(operation["reset_generation"]),
        }

    def _visible_orders(self, context: dict) -> dict[str, dict]:
        docs = self.simulation_repository.list_visible_orders(
            context["user_id"],
            context["run_id"],
            reset_generation=context["generation"],
            committed_sequence=context["sequence"] - 1,
            limit=500,
        )
        return {str(doc["order_id"]): doc for doc in docs}

    def _visible_positions(self, context: dict) -> dict[str, dict]:
        docs = self.simulation_repository.list_visible_positions(
            context["user_id"],
            context["run_id"],
            reset_generation=context["generation"],
            committed_sequence=context["sequence"] - 1,
            open_only=True,
            limit=500,
        )
        return {str(doc["position_id"]): doc for doc in docs}

    def _stage_order(
        self,
        context: dict,
        changed: dict[str, dict],
        current: dict[str, dict],
        order_id: Any,
        updates: dict[str, Any],
    ) -> dict:
        key = str(order_id)
        order = changed.get(key)
        if order is None:
            prior = current.get(key)
            if prior is None:
                raise SimulationRuleError("Simulation order was not found.")
            order = deepcopy(prior)
            order["entity_version"] = int(prior.get("entity_version", 0)) + 1
            order["operation_sequence"] = context["sequence"]
            order["_id"] = _stable_oid(
                "simulation-order-version", context["run_id"],
                context["generation"], order_id, context["sequence"]
            )
        order.update(updates)
        changed[key] = order
        current[key] = order
        return order

    def _stage_position(
        self,
        context: dict,
        changed: dict[str, dict],
        current: dict[str, dict],
        position_id: Any,
        updates: dict[str, Any],
    ) -> dict:
        key = str(position_id)
        position = changed.get(key)
        if position is None:
            prior = current.get(key)
            if prior is None:
                raise SimulationRuleError("Simulated position was not found.")
            position = deepcopy(prior)
            position["entity_version"] = int(prior.get("entity_version", 0)) + 1
            position["operation_sequence"] = context["sequence"]
            position["_id"] = _stable_oid(
                "simulation-position-version", context["run_id"],
                context["generation"], position_id, context["sequence"]
            )
        position.update(updates)
        changed[key] = position
        current[key] = position
        return position

    def _new_fill(
        self,
        operation: dict,
        run: dict,
        context: dict,
        *,
        order_id: Any,
        position: dict,
        candle: dict,
        allocation_index: int,
        lots: float,
        fill: Mapping[str, Any],
        order_type: str,
        entry_exit: str,
        quote_rate: float,
        native_gross: float | None = None,
        usd_gross: float | None = None,
    ) -> dict:
        operation_id = str(operation["_id"])
        fill_id = _stable_oid(
            "simulation-fill", operation_id, order_id,
            candle["source_candle_index"], allocation_index, entry_exit,
            position["position_id"]
        )
        order_oid = _as_oid(order_id, "order_id")
        position_oid = _as_oid(position["position_id"], "position_id")
        trade_oid = _as_oid(position["simulated_trade_id"], "simulated_trade_id")
        side = str(fill["side"]).lower()
        return make_fill_doc(
            fill_id=fill_id,
            user_id=context["user_id"],
            trade_id=trade_oid,
            trade_account_id=context["account_id"],
            import_batch_id=None,
            backtest_run_id=context["run_id"],
            backtest_order_id=order_oid,
            simulated_position_id=position_oid,
            symbol=str(run["instrument"]),
            raw_symbol=str(run["instrument"]),
            reset_generation=context["generation"],
            simulation_operation_sequence=context["sequence"],
            source_candle_index=int(candle["source_candle_index"]),
            allocation_index=allocation_index,
            time_ms=int(candle["time_ms"]),
            timestamp=_utc_datetime(int(candle["time_ms"])),
            side=side,
            lots=float(lots),
            quantity=float(lots),
            reference_price=float(fill["reference_price"]),
            fill_price=float(fill["fill_price"]),
            price=float(fill["fill_price"]),
            order_type=order_type,
            entry_exit=entry_exit,
            cost_profile_revision=int(fill.get("cost_profile_revision", 0)),
            spread_cost=float(fill.get("spread_cost", 0.0)),
            slippage_cost=float(fill.get("slippage_cost", 0.0)),
            commission=float(fill.get("commission_usd", 0.0)),
            commission_usd=float(fill.get("commission_usd", 0.0)),
            quote_currency=str(context["metadata"]["quote_currency"]).upper(),
            quote_to_usd_rate=float(quote_rate),
            native_gross_pnl=native_gross,
            usd_gross_pnl=usd_gross,
            source="backtest",
            status="filled",
            simulation_committed=False,
            platform_execution_id=str(fill_id),
            platform_order_id=str(order_oid),
            created_at=utc_now(),
        )

    def _persist_plan(
        self,
        *,
        orders: Mapping[str, dict] | None = None,
        positions: Mapping[str, dict] | None = None,
        fills: list[dict] = (),
        trades: list[dict] = (),
    ) -> None:
        order_collection = self.database[self.simulation_repository.ORDERS]
        for document in (orders or {}).values():
            order_collection.replace_one(
                {"_id": document["_id"]}, document, upsert=True
            )
        position_collection = self.database[self.simulation_repository.POSITIONS]
        for document in (positions or {}).values():
            position_collection.replace_one(
                {"_id": document["_id"]}, document, upsert=True
            )
        fill_collection = self.database[self.simulation_repository.FILLS]
        for document in fills:
            fill_collection.replace_one(
                {"_id": document["_id"]}, document, upsert=True
            )
        for document in trades:
            self.database.trades.replace_one(
                {"_id": document["_id"]}, document, upsert=True
            )

    def _balance_after(
        self, run: dict, context: dict, extra_fills: list[dict]
    ) -> float:
        query = {
            "user_id": context["user_id"],
            "backtest_run_id": context["run_id"],
            "reset_generation": context["generation"],
            "backtest_order_id": {"$exists": True},
            "simulation_operation_sequence": {"$lt": context["sequence"]},
        }
        realized = 0.0
        commissions = 0.0
        for fill in self.database[self.simulation_repository.FILLS].find(query):
            if fill.get("usd_gross_pnl") is not None:
                realized += float(fill["usd_gross_pnl"])
            commissions += float(fill.get("commission_usd", 0.0))
        for fill in extra_fills:
            if fill.get("usd_gross_pnl") is not None:
                realized += float(fill["usd_gross_pnl"])
            commissions += float(fill.get("commission_usd", 0.0))
        return float(run.get("initial_balance_usd", 10_000.0)) + realized - commissions

    def _current_costs(self, run: dict, operation: dict) -> dict:
        profile = self._profile(
            run,
            sequence=int((run.get("simulation_control") or {}).get("committed_sequence", 0)),
        )
        return {
            **profile,
            "cost_profile_revision": int(profile.get("revision", 0)),
        }

    def _submit_order(self, operation: dict, run: dict, request: dict) -> dict:
        context = self._context(operation, run)
        first, last = self._source_bounds(run)
        if context["cursor_index"] >= last:
            raise SimulationRuleError("No future candle is available for an entry order.")
        metadata = context["metadata"]
        side = str(request.get("side", "")).lower()
        order_type = str(request.get("order_type", "")).lower()
        if side not in {"buy", "sell"} or order_type not in {"market", "limit"}:
            raise SimulationRuleError("Entry orders support market/limit and buy/sell only.")
        entry_reference = (
            normalize_market_reference_price(
                context["candle"]["close"], metadata, "entry_price"
            )
            if order_type == "market"
            else validate_price(request.get("entry_price"), metadata, "entry_price")
        )
        _, stop, target = validate_entry_bracket(
            side,
            entry_reference,
            request.get("stop_loss"),
            request.get("take_profit"),
            metadata,
        )
        profile = self._current_costs(run, operation)
        quote_rate = self._quote_rate(
            run, metadata, context["cursor_time_ms"] + 60_000
        )
        risk_percent = _as_float(
            run.get("simulation_risk_percent", run.get("risk_percent", 1.0)),
            "risk_percent",
        )
        balance = _as_float(
            run.get("current_balance_usd", run.get("initial_balance_usd", 10_000.0)),
            "current_balance_usd",
        )
        risk_budget = balance * risk_percent / 100.0
        if not math.isfinite(risk_budget) or risk_budget <= 0:
            raise SimulationRuleError("A positive current balance is required to size an order.")
        if request.get("auto_size"):
            lots = auto_size_lots(
                risk_budget_usd=risk_budget,
                entry_price=entry_reference,
                stop_loss=stop,
                quote_to_usd_rate=quote_rate,
                metadata=metadata,
                cost_profile=profile,
            )
            sizing_mode = "auto"
        else:
            lots = validate_lots(request.get("lots"), metadata)
            sizing_mode = "manual"
        risk_usd = projected_risk_usd(
            lots=lots,
            entry_price=entry_reference,
            stop_loss=stop,
            quote_to_usd_rate=quote_rate,
            metadata=metadata,
            cost_profile=profile,
        )
        order_id = _stable_oid("simulation-entry-order", operation["_id"])
        now = utc_now()
        order = make_order_version_doc(
            user_id=context["user_id"],
            run_id=context["run_id"],
            reset_generation=context["generation"],
            order_id=order_id,
            operation_sequence=context["sequence"],
            entity_version=1,
            document_id=_stable_oid("simulation-order-version", order_id, context["sequence"]),
            client_order_id=str(operation["client_operation_id"]),
            role="entry",
            order_type=order_type,
            side=side,
            lots=float(lots),
            entry_price=float(entry_reference) if order_type == "limit" else None,
            sizing_reference_entry_price=float(entry_reference),
            sizing_quote_to_usd_rate=float(quote_rate),
            stop_loss_price=float(stop),
            take_profit_price=float(target),
            sizing_mode=sizing_mode,
            risk_percent=risk_percent,
            risk_budget_usd=float(risk_budget),
            projected_risk_usd=float(risk_usd),
            cost_profile_revision=int(profile.get("revision", 0)),
            status="pending",
            eligible_source_index=context["cursor_index"] + 1,
            linked_position_id=None,
            oco_group_id=None,
            submitted_at=now,
            updated_at=now,
        )
        self._persist_plan(orders={str(order_id): order})
        return {
            "result": {
                "order_id": str(order_id),
                "lots": float(lots),
                "risk_budget_usd": float(risk_budget),
                "projected_risk_usd": float(risk_usd),
                "eligible_source_index": context["cursor_index"] + 1,
            },
            "run_updates": {},
        }

    def _cancel_order(self, operation: dict, run: dict, request: dict) -> dict:
        context = self._context(operation, run)
        current_orders = self._visible_orders(context)
        order_id = request.get("order_id")
        order = current_orders.get(str(order_id))
        if order is None or order.get("role") != "entry":
            raise SimulationRuleError("Only a run-owned entry order can be cancelled.")
        if order.get("status") != "pending":
            raise SimulationRuleError("Only pending entry orders can be cancelled.")
        changed: dict[str, dict] = {}
        updated = self._stage_order(
            context,
            changed,
            current_orders,
            order["order_id"],
            {"status": "cancelled", "updated_at": utc_now()},
        )
        self._persist_plan(orders=changed)
        return {"result": {"order_id": str(updated["order_id"]), "status": "cancelled"}, "run_updates": {}}

    def _close_position(self, operation: dict, run: dict, request: dict) -> dict:
        context = self._context(operation, run)
        current_positions = self._visible_positions(context)
        current_orders = self._visible_orders(context)
        position_id = request.get("position_id")
        position = current_positions.get(str(position_id))
        if position is None or position.get("status") != "open":
            raise SimulationRuleError("Open position was not found in this run.")
        profile = self._current_costs(run, operation)
        candle = context["candle"]
        side = "sell" if position["side"] == "long" else "buy"
        fill = adjusted_market_fill(
            candle["close"],
            side,
            lots=position["remaining_lots"],
            metadata=context["metadata"],
            cost_profile=profile,
        )
        fill["cost_profile_revision"] = int(profile.get("revision", 0))
        rate = self._quote_rate(
            run, context["metadata"], int(candle["time_ms"]) + 60_000
        )
        close_order_id = _stable_oid(
            "simulation-manual-close", operation["_id"], position["position_id"]
        )
        now = utc_now()
        close_order = make_order_version_doc(
            user_id=context["user_id"],
            run_id=context["run_id"],
            reset_generation=context["generation"],
            order_id=close_order_id,
            operation_sequence=context["sequence"],
            entity_version=1,
            document_id=_stable_oid("simulation-order-version", close_order_id, context["sequence"]),
            client_order_id=str(operation["client_operation_id"]),
            role="manual_close",
            order_type="market",
            side=side,
            lots=float(position["remaining_lots"]),
            entry_price=float(fill["reference_price"]),
            sizing_reference_entry_price=None,
            sizing_quote_to_usd_rate=None,
            stop_loss_price=None,
            take_profit_price=None,
            sizing_mode=None,
            risk_percent=None,
            risk_budget_usd=None,
            status="filled",
            eligible_source_index=context["cursor_index"],
            linked_position_id=position["position_id"],
            oco_group_id=None,
            submitted_at=now,
            updated_at=now,
        )
        current_orders[str(close_order_id)] = close_order
        changed_orders = {str(close_order_id): close_order}
        changed_positions: dict[str, dict] = {}
        fills: list[dict] = []
        closed, fill_doc, trade = self._apply_position_exit(
            operation,
            run,
            context,
            candle,
            position,
            close_order_id,
            fill,
            "market",
            rate,
            allocation_index=0,
            lots=float(position["remaining_lots"]),
            current_orders=current_orders,
            changed_orders=changed_orders,
            current_positions=current_positions,
            changed_positions=changed_positions,
            staged_fills=fills,
        )
        fills.append(fill_doc)
        balance = self._balance_after(run, context, fills)
        self._persist_plan(
            orders=changed_orders,
            positions=changed_positions,
            fills=fills,
            trades=[trade] if closed and trade is not None else [],
        )
        return {
            "result": {
                "position_id": str(position_id),
                "closed": bool(closed),
                "current_balance_usd": balance,
            },
            "run_updates": {"current_balance_usd": balance},
        }

    def _modify_protection(self, operation: dict, run: dict, request: dict) -> dict:
        context = self._context(operation, run)
        metadata = context["metadata"]
        current_positions = self._visible_positions(context)
        current_orders = self._visible_orders(context)
        position_id = request.get("position_id")
        position = current_positions.get(str(position_id))
        if position is None or position.get("status") != "open":
            raise SimulationRuleError("Open position was not found in this run.")
        stop = position.get("stop_loss_price")
        target = position.get("take_profit_price")
        close = normalize_market_reference_price(
            context["candle"]["close"], metadata, "current_close"
        )
        stop_changed = False
        if request.get("stop_loss") is not None:
            stop = validate_price(request["stop_loss"], metadata, "stop_loss")
            if position["side"] == "long" and stop >= close:
                raise SimulationRuleError("A long stop-loss must remain below the current close.")
            if position["side"] == "short" and stop <= close:
                raise SimulationRuleError("A short stop-loss must remain above the current close.")
            stop_changed = float(stop) != float(position.get("stop_loss_price"))
        if request.get("take_profit") is not None:
            target = validate_price(request["take_profit"], metadata, "take_profit")
            if position["side"] == "long" and target <= close:
                raise SimulationRuleError("A long take-profit must remain above the current close.")
            if position["side"] == "short" and target >= close:
                raise SimulationRuleError("A short take-profit must remain below the current close.")
        if stop is None or target is None:
            raise SimulationRuleError("Open positions require both protection prices.")
        tag_ids = list(position.get("tag_ids", []))
        stop_moved = bool(position.get("stop_moved"))
        if stop_changed:
            tag_id = self._ensure_stop_moved_tag(context["user_id"])
            if str(tag_id) not in {str(value) for value in tag_ids}:
                tag_ids.append(tag_id)
            stop_moved = True

        eligible = context["cursor_index"] + 1
        changed_positions: dict[str, dict] = {}
        updated_position = self._stage_position(
            context,
            changed_positions,
            current_positions,
            position["position_id"],
            {
                "stop_loss_price": float(stop),
                "take_profit_price": float(target),
                "stop_loss_eligible_source_index": eligible if request.get("stop_loss") is not None else position.get("stop_loss_eligible_source_index", eligible),
                "take_profit_eligible_source_index": eligible if request.get("take_profit") is not None else position.get("take_profit_eligible_source_index", eligible),
                "tag_ids": tag_ids,
                "stop_moved": stop_moved,
                "updated_at": utc_now(),
            },
        )
        changed_orders: dict[str, dict] = {}
        stop_order_id = position.get("stop_loss_order_id")
        target_order_id = position.get("take_profit_order_id")
        if request.get("stop_loss") is not None:
            self._stage_order(
                context,
                changed_orders,
                current_orders,
                stop_order_id,
                {
                    "entry_price": float(position["weighted_entry_price"]),
                    "stop_loss_price": float(stop),
                    "eligible_source_index": eligible,
                    "lots": float(position["remaining_lots"]),
                    "updated_at": utc_now(),
                },
            )
        if request.get("take_profit") is not None:
            self._stage_order(
                context,
                changed_orders,
                current_orders,
                target_order_id,
                {
                    "entry_price": float(position["weighted_entry_price"]),
                    "take_profit_price": float(target),
                    "eligible_source_index": eligible,
                    "lots": float(position["remaining_lots"]),
                    "updated_at": utc_now(),
                },
            )
        self._persist_plan(orders=changed_orders, positions=changed_positions)
        return {
            "result": {
                "position_id": str(position_id),
                "stop_loss": updated_position["stop_loss_price"],
                "take_profit": updated_position["take_profit_price"],
                "initial_risk_usd": updated_position["initial_risk_usd"],
                "tag_ids": [str(value) for value in tag_ids],
                "stop_moved": stop_moved,
            },
            "run_updates": {},
        }

    def _ensure_stop_moved_tag(self, user_id: ObjectId) -> ObjectId:
        user_id = _as_oid(user_id, "user_id")
        tag_repo = TagRepository()
        existing = tag_repo.find_by_name(str(user_id), "stop-moved")
        if existing is not None:
            return existing["_id"]
        categories = ensure_tag_categories(str(user_id))
        general = categories.get("general")
        if general is None:
            raise RuntimeError("The General tag category could not be initialized.")
        document = create_tag_doc(
            user_id,
            "stop-moved",
            category_id=general["_id"],
            category="general",
            color=general.get("color", "#6366F1"),
        )
        document["_id"] = _stable_oid("user-tag", user_id, "stop-moved")
        self.database.tags.replace_one(
            {"user_id": user_id, "name": "stop-moved"}, document, upsert=True
        )
        tag = self.database.tags.find_one({"user_id": user_id, "name": "stop-moved"})
        if tag is None:
            raise RuntimeError("The stop-moved tag could not be persisted.")
        return tag["_id"]

    def _update_costs(self, operation: dict, run: dict, request: dict) -> dict:
        context = self._context(operation, run)
        current = self._profile(
            run,
            sequence=int((run.get("simulation_control") or {}).get("committed_sequence", 0)),
        )
        values = {
            "total_spread_pips": _as_float(request.get("total_spread_pips"), "total_spread_pips"),
            "slippage_pips": _as_float(request.get("slippage_pips"), "slippage_pips"),
            "commission_usd_per_lot_per_side": _as_float(
                request.get("commission_usd_per_lot_per_side"),
                "commission_usd_per_lot_per_side",
            ),
        }
        if any(value < 0 for value in values.values()):
            raise SimulationRuleError("Execution costs must be nonnegative.")
        revision = int(current.get("revision", 0)) + 1
        document_id = _stable_oid(
            "simulation-cost-profile", context["run_id"], revision
        )
        profile = make_cost_profile_doc(
            user_id=context["user_id"],
            run_id=context["run_id"],
            revision=revision,
            operation_sequence=context["sequence"],
            updated_at=utc_now(),
            profile_id=document_id,
            **values,
        )
        self.database[self.simulation_repository.COST_PROFILES].replace_one(
            {"_id": document_id}, profile, upsert=True
        )
        return {
            "result": {"cost_profile": profile},
            "run_updates": {},
        }

    def _update_risk(self, operation: dict, run: dict, request: dict) -> dict:
        risk_percent = _as_float(request.get("risk_percent"), "risk_percent")
        if risk_percent <= 0 or risk_percent > 100:
            raise SimulationRuleError(
                "Risk percent must be greater than 0% and no more than 100%."
            )
        return {
            "result": {"risk_percent": risk_percent},
            "run_updates": {"simulation_risk_percent": risk_percent},
        }

    def _rewind(self, operation: dict, run: dict, request: dict) -> dict:
        context = self._context(operation, run)
        index = request.get("source_candle_index")
        time_ms = request.get("time_ms")
        cursor = self._validate_cursor(run, index, time_ms)
        if index >= context["cursor_index"]:
            raise SimulationRuleError("Rewind must move to an earlier candle.")
        control = run.get("simulation_control") or {}
        if control.get("has_accepted_order"):
            raise SimulationRuleError("Reset is required before moving backward.")
        return {"result": {"cursor": cursor}, "run_updates": {"replay_cursor": cursor}}

    def _reset(self, operation: dict, run: dict) -> dict:
        first, _ = self._source_bounds(run)
        time_ms = self.snapshot_store.read_snapshot_candle_time(run["snapshot"], first)
        if time_ms is None:
            raise SimulationRuleError("The selected replay start candle is unavailable.")
        cursor = {"source_candle_index": first, "time_ms": int(time_ms)}
        return {"result": {"cursor": cursor}, "run_updates": {"replay_cursor": cursor}}

    def _advance(self, operation: dict, run: dict, request: dict) -> dict:
        context = self._context(operation, run)
        first, last = self._source_bounds(run)
        target = request.get("target_source_index")
        if isinstance(target, bool) or not isinstance(target, int):
            raise SimulationRuleError("target_source_index must be an integer.")
        if target <= context["cursor_index"] or target > last:
            raise SimulationRuleError("Advance target must be a later available candle.")
        candles = self._snapshot_range(run, context["cursor_index"] + 1, target)
        metadata = context["metadata"]
        profile = self._current_costs(run, operation)
        current_orders = self._visible_orders(context)
        current_positions = self._visible_positions(context)
        changed_orders: dict[str, dict] = {}
        changed_positions: dict[str, dict] = {}
        new_fills: list[dict] = []
        closed_positions: list[dict] = []

        for candle in candles:
            # Existing OCO protection is evaluated before entries on this
            # candle. A position opened below is therefore never exposed to
            # its bracket until the next full one-minute candle.
            for position in list(current_positions.values()):
                if position.get("status") != "open":
                    continue
                protection_fill = protective_exit_fill(
                    position,
                    candle,
                    int(candle["source_candle_index"]),
                    metadata=metadata,
                    cost_profile=profile,
                )
                if protection_fill is None:
                    continue
                role = protection_fill.pop("exit_role")
                order_id = position.get(
                    "stop_loss_order_id" if role == "protective_stop" else "take_profit_order_id"
                )
                if order_id is None:
                    raise SimulationRuleError("Open position is missing its OCO order.")
                rate = self._quote_rate(run, metadata, int(candle["time_ms"]))
                fill = {**protection_fill, "cost_profile_revision": profile.get("revision", 0)}
                order_type = "stop_market" if role == "protective_stop" else "limit"
                closed, fill_doc, trade = self._apply_position_exit(
                    operation,
                    run,
                    context,
                    candle,
                    position,
                    order_id,
                    fill,
                    order_type,
                    rate,
                    allocation_index=0,
                    lots=float(position["remaining_lots"]),
                    current_orders=current_orders,
                    changed_orders=changed_orders,
                    current_positions=current_positions,
                    changed_positions=changed_positions,
                    staged_fills=new_fills,
                )
                new_fills.append(fill_doc)
                if closed:
                    closed_positions.append(trade)

            pending_entries = [
                order for order in current_orders.values()
                if order.get("role") == "entry" and order.get("status") == "pending"
            ]
            pending_entries.sort(key=lambda item: (item.get("submitted_at"), str(item.get("order_id"))))
            for order_index, order in enumerate(pending_entries):
                entry_fill = entry_order_fill(
                    order,
                    candle,
                    int(candle["source_candle_index"]),
                    metadata=metadata,
                    cost_profile=profile,
                )
                if entry_fill is None:
                    continue
                rate = self._quote_rate(run, metadata, int(candle["time_ms"]))
                entry_fill = {
                    **entry_fill,
                    "cost_profile_revision": int(profile.get("revision", 0)),
                }
                allocated, excess = allocate_opposing_fill_fifo(
                    order["side"], order["lots"], list(current_positions.values()),
                    metadata=metadata,
                )
                total_lots = float(order["lots"])
                allocation_index = 0
                opened_position_id = None
                for allocation in allocated:
                    allocated_lots = float(allocation["lots"])
                    share = allocated_lots / total_lots
                    allocation_fill = self._scaled_fill(entry_fill, share)
                    position = current_positions.get(str(allocation["position_id"]))
                    if position is None or position.get("status") != "open":
                        continue
                    closed, fill_doc, trade = self._apply_position_exit(
                        operation,
                        run,
                        context,
                        candle,
                        position,
                        order["order_id"],
                        allocation_fill,
                        order["order_type"],
                        rate,
                        allocation_index=allocation_index,
                        lots=allocated_lots,
                        current_orders=current_orders,
                        changed_orders=changed_orders,
                        current_positions=current_positions,
                        changed_positions=changed_positions,
                        staged_fills=new_fills,
                    )
                    allocation_index += 1
                    new_fills.append(fill_doc)
                    if closed:
                        closed_positions.append(trade)

                if excess > 0:
                    excess_lots = float(excess)
                    share = excess_lots / total_lots
                    allocation_fill = self._scaled_fill(entry_fill, share)
                    position, entry_doc = self._open_position(
                        operation,
                        run,
                        context,
                        candle,
                        order,
                        allocation_fill,
                        profile,
                        rate,
                        order_index=order_index,
                        allocation_index=allocation_index,
                        lots=excess_lots,
                    )
                    opened_position_id = position["position_id"]
                    for child_order in position.pop("_created_order_versions", []):
                        current_orders[str(child_order["order_id"])] = child_order
                        changed_orders[str(child_order["order_id"])] = child_order
                    current_positions[str(opened_position_id)] = position
                    changed_positions[str(opened_position_id)] = position
                    new_fills.append(entry_doc)

                staged_order = self._stage_order(
                    context,
                    changed_orders,
                    current_orders,
                    order["order_id"],
                    {
                        "status": "filled",
                        "linked_position_id": opened_position_id,
                        "updated_at": utc_now(),
                    },
                )

        # A protective fill may have closed a position and staged OCO updates;
        # publish one latest version per logical entity for this operation.
        closed_trades = [trade for trade in closed_positions if trade is not None]
        balance = self._balance_after(run, context, new_fills)
        self._persist_plan(
            orders=changed_orders,
            positions=changed_positions,
            fills=new_fills,
            trades=closed_trades,
        )
        candle = candles[-1]
        run_updates: dict[str, Any] = {
            "replay_cursor": {
                "source_candle_index": target,
                "time_ms": int(candle["time_ms"]),
            },
            "current_balance_usd": balance,
        }
        if target == last:
            run_updates["status"] = "complete"
        return {
            "result": {
                "cursor": run_updates["replay_cursor"],
                "fill_count": len(new_fills),
                "current_balance_usd": balance,
            },
            "run_updates": run_updates,
        }

    @staticmethod
    def _scaled_fill(fill: Mapping[str, Any], factor: float) -> dict[str, Any]:
        result = dict(fill)
        for field in ("spread_cost", "slippage_cost", "commission_usd"):
            result[field] = float(fill.get(field, 0.0)) * factor
        return result

    def _open_position(
        self,
        operation: dict,
        run: dict,
        context: dict,
        candle: dict,
        entry_order: dict,
        fill: dict,
        profile: dict,
        quote_rate: float,
        *,
        order_index: int,
        allocation_index: int,
        lots: float,
    ) -> tuple[dict, dict]:
        metadata = context["metadata"]
        order_id = entry_order["order_id"]
        position_id = _stable_oid(
            "simulation-position", context["run_id"], context["generation"], order_id
        )
        trade_id = _stable_oid("simulation-trade", position_id)
        stop = validate_price(entry_order["stop_loss_price"], metadata, "stop_loss")
        target = validate_price(entry_order["take_profit_price"], metadata, "take_profit")
        fill_price = validate_price(fill["fill_price"], metadata, "fill_price")
        stop_loss_order_id = _stable_oid("simulation-protection", position_id, "stop")
        take_profit_order_id = _stable_oid("simulation-protection", position_id, "target")
        oco_id = _stable_oid("simulation-oco", position_id)
        order_side = str(entry_order["side"]).lower()
        position_side = "long" if order_side == "buy" else "short"
        initial_native = abs(float(fill_price - stop)) * float(metadata["contract_size"]) * lots
        risk_usd = projected_risk_usd(
            lots=lots,
            entry_price=fill_price,
            stop_loss=stop,
            quote_to_usd_rate=quote_rate,
            metadata=metadata,
            cost_profile=profile,
        )
        now = _utc_datetime(int(candle["time_ms"]))
        opened_sequence = (
            int(candle["source_candle_index"]) * 1_000_000
            + order_index * 1_000
            + allocation_index
        )
        position = make_position_version_doc(
            user_id=context["user_id"],
            run_id=context["run_id"],
            reset_generation=context["generation"],
            position_id=position_id,
            operation_sequence=context["sequence"],
            entity_version=1,
            document_id=_stable_oid(
                "simulation-position-version", position_id, context["sequence"]
            ),
            trade_account_id=context["account_id"],
            simulated_trade_id=trade_id,
            instrument=str(run["instrument"]),
            side=position_side,
            status="open",
            remaining_lots=lots,
            max_lots=lots,
            weighted_entry_price=float(fill_price),
            weighted_reference_price=float(fill["reference_price"]),
            entry_fill_ids=[],
            original_stop_loss_price=float(stop),
            original_take_profit_price=float(target),
            stop_loss_order_id=stop_loss_order_id,
            take_profit_order_id=take_profit_order_id,
            stop_loss_price=float(stop),
            take_profit_price=float(target),
            stop_loss_eligible_source_index=int(candle["source_candle_index"]) + 1,
            take_profit_eligible_source_index=int(candle["source_candle_index"]) + 1,
            initial_risk_native=max(initial_native, 10 ** -int(metadata["price_precision"])),
            initial_risk_usd=float(risk_usd),
            entry_quote_to_usd_rate=float(quote_rate),
            realized_partial_native_pnl=0.0,
            realized_partial_usd_pnl=0.0,
            applied_spread_cost=float(fill.get("spread_cost", 0.0)),
            applied_slippage_cost=float(fill.get("slippage_cost", 0.0)),
            applied_commission_usd=float(fill.get("commission_usd", 0.0)),
            entry_spread_slippage_native_remaining=(
                float(fill.get("spread_cost", 0.0))
                + float(fill.get("slippage_cost", 0.0))
            ),
            entry_spread_slippage_usd_remaining=(
                float(fill.get("spread_cost", 0.0))
                + float(fill.get("slippage_cost", 0.0))
            ) * quote_rate,
            opened_at=now,
            opened_sequence=opened_sequence,
            updated_at=utc_now(),
            tag_ids=[],
            unrealized_pnl_usd=None,
        )
        entry_fill_doc = self._new_fill(
            operation,
            run,
            context,
            order_id=order_id,
            position=position,
            candle=candle,
            allocation_index=allocation_index,
            lots=lots,
            fill=fill,
            order_type=entry_order["order_type"],
            entry_exit="Entry",
            quote_rate=quote_rate,
        )
        position["entry_fill_ids"] = [entry_fill_doc["_id"]]

        common = {
            "lots": lots,
            "entry_price": float(fill_price),
            "sizing_reference_entry_price": None,
            "sizing_quote_to_usd_rate": None,
            "sizing_mode": None,
            "risk_percent": None,
            "risk_budget_usd": None,
            "status": "pending",
            "linked_position_id": position_id,
            "oco_group_id": oco_id,
            "submitted_at": now,
            "updated_at": utc_now(),
        }
        for order_id_child, role, child_type, child_side, child_price in (
            (stop_loss_order_id, "protective_stop", "stop_market", "sell" if order_side == "buy" else "buy", float(stop)),
            (take_profit_order_id, "protective_target", "limit", "sell" if order_side == "buy" else "buy", float(target)),
        ):
            document = make_order_version_doc(
                user_id=context["user_id"],
                run_id=context["run_id"],
                reset_generation=context["generation"],
                order_id=order_id_child,
                operation_sequence=context["sequence"],
                entity_version=1,
                document_id=_stable_oid(
                    "simulation-order-version", order_id_child, context["sequence"]
                ),
                client_order_id=str(entry_order["client_order_id"]),
                role=role,
                order_type=child_type,
                side=child_side,
                eligible_source_index=int(candle["source_candle_index"]) + 1,
                **common,
                **{
                    "stop_loss_price": child_price if role == "protective_stop" else None,
                    "take_profit_price": child_price if role == "protective_target" else None,
                },
            )
            # Child orders are part of the same logical entry-fill operation.
            # They are added by the caller through the shared staged order map.
            position.setdefault("_created_order_versions", []).append(document)
        return position, entry_fill_doc

    def _apply_position_exit(
        self,
        operation: dict,
        run: dict,
        context: dict,
        candle: dict,
        position: dict,
        order_id: Any,
        fill: dict,
        order_type: str,
        quote_rate: float,
        *,
        allocation_index: int,
        lots: float,
        current_orders: dict[str, dict],
        changed_orders: dict[str, dict],
        current_positions: dict[str, dict],
        changed_positions: dict[str, dict],
        staged_fills: list[dict] | None = None,
    ) -> tuple[bool, dict, dict | None]:
        metadata = context["metadata"]
        before = float(position["remaining_lots"])
        quantity = float(validate_lots(lots, metadata))
        if quantity > before:
            raise SimulationRuleError("Exit quantity exceeds the remaining position.")
        share = quantity / before
        reference_entry = position.get(
            "weighted_reference_price", position["weighted_entry_price"]
        )
        raw_native = float(
            realized_native_pnl(
                side=position["side"],
                entry_price=reference_entry,
                exit_price=fill["reference_price"],
                lots=quantity,
                metadata=metadata,
            )
        )
        entry_cost_native = float(
            position.get("entry_spread_slippage_native_remaining", 0.0)
        ) * share
        entry_cost_usd = float(
            position.get("entry_spread_slippage_usd_remaining", 0.0)
        ) * share
        exit_cost_native = float(fill.get("spread_cost", 0.0)) + float(
            fill.get("slippage_cost", 0.0)
        )
        native_gross = raw_native - entry_cost_native - exit_cost_native
        usd_gross = (
            raw_native * quote_rate
            - entry_cost_usd
            - exit_cost_native * quote_rate
        )
        next_position = self._stage_position(
            context,
            changed_positions,
            current_positions,
            position["position_id"],
            {
                "remaining_lots": round(before - quantity, 3),
                "realized_partial_native_pnl": float(
                    position.get("realized_partial_native_pnl", 0.0)
                ) + native_gross,
                "realized_partial_usd_pnl": float(
                    position.get("realized_partial_usd_pnl", 0.0)
                ) + usd_gross,
                "entry_spread_slippage_native_remaining": max(
                    0.0,
                    float(position.get("entry_spread_slippage_native_remaining", 0.0))
                    - entry_cost_native,
                ),
                "entry_spread_slippage_usd_remaining": max(
                    0.0,
                    float(position.get("entry_spread_slippage_usd_remaining", 0.0))
                    - entry_cost_usd,
                ),
                "applied_spread_cost": float(position.get("applied_spread_cost", 0.0))
                + float(fill.get("spread_cost", 0.0)),
                "applied_slippage_cost": float(position.get("applied_slippage_cost", 0.0))
                + float(fill.get("slippage_cost", 0.0)),
                "applied_commission_usd": float(position.get("applied_commission_usd", 0.0))
                + float(fill.get("commission_usd", 0.0)),
                "last_quote_to_usd_rate": quote_rate,
                "updated_at": utc_now(),
            },
        )
        fully_closed = next_position["remaining_lots"] <= 0
        if fully_closed:
            next_position["remaining_lots"] = 0.0
            next_position["status"] = "closed"
            next_position["closed_at"] = _utc_datetime(int(candle["time_ms"]))

        fill_doc = self._new_fill(
            operation,
            run,
            context,
            order_id=order_id,
            position=next_position,
            candle=candle,
            allocation_index=allocation_index,
            lots=quantity,
            fill=fill,
            order_type=order_type,
            entry_exit="Exit",
            quote_rate=quote_rate,
            native_gross=native_gross,
            usd_gross=usd_gross,
        )
        next_position["last_exit_fill_id"] = fill_doc["_id"]

        if fully_closed:
            self._cancel_position_protection(
                context,
                next_position,
                current_orders,
                changed_orders,
                filled_order_id=order_id,
            )
            trade = self._closed_trade(
                run,
                context,
                next_position,
                extra_fills=[*(staged_fills or []), fill_doc],
                operation_sequence=context["sequence"],
            )
        else:
            for child_id in (
                next_position.get("stop_loss_order_id"),
                next_position.get("take_profit_order_id"),
            ):
                child = current_orders.get(str(child_id))
                if child and child.get("status") == "pending":
                    self._stage_order(
                        context,
                        changed_orders,
                        current_orders,
                        child_id,
                        {"lots": next_position["remaining_lots"], "updated_at": utc_now()},
                    )
            trade = None
        return fully_closed, fill_doc, trade

    def _cancel_position_protection(
        self,
        context: dict,
        position: dict,
        current_orders: dict[str, dict],
        changed_orders: dict[str, dict],
        *,
        filled_order_id: Any,
    ) -> None:
        for child_id in (
            position.get("stop_loss_order_id"),
            position.get("take_profit_order_id"),
        ):
            if child_id is None:
                continue
            child = current_orders.get(str(child_id))
            if child is None or child.get("status") != "pending":
                continue
            self._stage_order(
                context,
                changed_orders,
                current_orders,
                child_id,
                {
                    "status": "filled" if str(child_id) == str(filled_order_id) else "cancelled",
                    "updated_at": utc_now(),
                },
            )

    def _closed_trade(
        self,
        run: dict,
        context: dict,
        position: dict,
        *,
        extra_fills: list[dict],
        operation_sequence: int,
    ) -> dict:
        query = {
            "user_id": context["user_id"],
            "backtest_run_id": context["run_id"],
            "reset_generation": context["generation"],
            "simulated_position_id": position["position_id"],
            "backtest_order_id": {"$exists": True},
        }
        existing = list(self.database[self.simulation_repository.FILLS].find(query))
        fills_by_id = {str(fill["_id"]): fill for fill in existing}
        for fill in extra_fills:
            if str(fill.get("simulated_position_id")) == str(position["position_id"]):
                fills_by_id[str(fill["_id"])] = fill
        all_fills = list(fills_by_id.values())
        entries = [fill for fill in all_fills if str(fill.get("entry_exit", "")).lower() == "entry"]
        exits = [fill for fill in all_fills if str(fill.get("entry_exit", "")).lower() == "exit"]
        entry_lots = sum(float(fill["lots"]) for fill in entries) or float(position.get("max_lots", 0.0))
        exit_lots = sum(float(fill["lots"]) for fill in exits)
        if not entries or not exits or exit_lots <= 0:
            raise SimulationRuleError("A closed position requires entry and exit fills.")
        avg_entry = sum(float(fill["fill_price"]) * float(fill["lots"]) for fill in entries) / sum(float(fill["lots"]) for fill in entries)
        avg_exit = sum(float(fill["fill_price"]) * float(fill["lots"]) for fill in exits) / exit_lots
        native_pnl = float(position.get("realized_partial_native_pnl", 0.0))
        gross_usd = float(position.get("realized_partial_usd_pnl", 0.0))
        fees = float(position.get("applied_commission_usd", 0.0))
        entry_time = min(
            _normalize_utc_datetime(fill["timestamp"]) for fill in entries
        )
        exit_time = max(
            _normalize_utc_datetime(fill["timestamp"]) for fill in exits
        )
        initial_quantity = float(position.get("max_lots", entry_lots))
        metadata = context["metadata"]
        pip_denominator = float(metadata["pip_size"]) * float(metadata["contract_size"]) * max(initial_quantity, 0.001)
        pips = native_pnl / pip_denominator if pip_denominator else None
        trade = create_trade_doc(
            user_id=context["user_id"],
            trade_account_id=context["account_id"],
            import_batch_id=None,
            symbol=str(run["instrument"]),
            raw_symbol=str(run["instrument"]),
            side="Long" if position["side"] == "long" else "Short",
            total_quantity=entry_lots,
            max_quantity=max(initial_quantity, entry_lots),
            avg_entry_price=avg_entry,
            avg_exit_price=avg_exit,
            gross_pnl=gross_usd,
            fee=fees,
            fee_source="simulated_cost_profile",
            net_pnl=gross_usd - fees,
            initial_risk=float(position["initial_risk_usd"]),
            entry_time=entry_time,
            exit_time=exit_time,
            holding_time_seconds=max(0, int((exit_time - entry_time).total_seconds())),
            execution_count=len(all_fills),
            source="backtest",
            status="closed",
            instrument_type="cfd",
            lot_size=entry_lots,
            base_currency=metadata.get("base_currency"),
            quote_currency=metadata.get("quote_currency"),
            pip_size=float(metadata["pip_size"]),
            price_precision=int(metadata["price_precision"]),
            contract_size=float(metadata["contract_size"]),
            pip_value_per_standard_lot=float(metadata.get("pip_value_per_standard_lot", 0.0)),
            pips=pips,
            native_pnl=native_pnl,
            native_pnl_currency=str(metadata["quote_currency"]).upper(),
            quote_to_usd_rate=position.get("last_quote_to_usd_rate"),
        )
        trade.update(
            {
                "_id": position["simulated_trade_id"],
                "backtest_run_id": context["run_id"],
                "simulation_generation": context["generation"],
                "simulation_operation_sequence": operation_sequence,
                "simulated_position_id": position["position_id"],
                "tag_ids": list(position.get("tag_ids", [])),
                # The trade shares the Journal collection, so keep it hidden
                # from ordinary status != deleted queries until its operation
                # sequence is committed by SimulationService.
                "status": "deleted",
                "deleted_at": utc_now(),
                "created_at": position.get("opened_at", entry_time),
                "updated_at": utc_now(),
            }
        )
        return trade
