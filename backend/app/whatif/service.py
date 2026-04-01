"""What-if service — stop analysis and simulation."""

import hashlib
import json
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from bson import ObjectId

from app.extensions import mongo
from app.market_data.service import MarketDataService
from app.market_data.symbol_mapper import (
    get_effective_market_data_mappings,
    get_effective_symbol_mappings,
    get_point_value,
)
from app.repositories.tag_repo import TagRepository
from app.repositories.trade_repo import TradeRepository
from app.repositories.user_repo import UserRepository
from app.utils.errors import ValidationError
from app.utils.trade_metrics import (
    calculate_r_multiple,
    calculate_widened_effective_risk,
)
from app.whatif.cache import _CACHE_TTL, _sim_cache
from app.whatif.bootstrap import (
    build_confidence_intervals,
    empty_confidence_intervals,
)


_BAR_INTERVAL_SECONDS = {
    "1m": 60,
    "5m": 300,
    "15m": 900,
    "1h": 3600,
    "1d": 86400,
}


def _parse_date_from(value: str) -> datetime:
    """Parse date_from as inclusive lower bound."""
    return datetime.fromisoformat(value)


def _parse_date_to(value: str) -> datetime:
    """Parse date_to as inclusive upper bound."""
    dt = datetime.fromisoformat(value)
    if len(value) == 10:
        return (
            dt + timedelta(days=1)
            - timedelta(microseconds=1)
        )
    return dt


def _percentile(
    values: List[float], pct: float
) -> float:
    """Compute linear-interpolated percentile.

    Parameters:
        values: Numeric samples.
        pct: Percentile in [0, 100].

    Returns:
        Percentile value (0.0 for empty input).
    """
    if not values:
        return 0.0
    s = sorted(values)
    if len(s) == 1:
        return float(s[0])
    rank = (pct / 100.0) * (len(s) - 1)
    lo = int(rank)
    hi = min(lo + 1, len(s) - 1)
    w = rank - lo
    return float(s[lo]) + (float(s[hi]) - float(s[lo])) * w


def _build_match(
    user_id: str, filters: Dict[str, Any]
) -> Dict[str, Any]:
    """Build $match for whatif queries."""
    match: Dict[str, Any] = {
        "user_id": ObjectId(user_id),
        "status": "closed",
    }
    if filters.get("account"):
        match["trade_account_id"] = ObjectId(
            filters["account"]
        )
    if filters.get("symbol"):
        symbol = str(filters["symbol"]).strip().upper()
        if symbol:
            match["symbol"] = symbol
    if filters.get("side"):
        match["side"] = filters["side"]
    if filters.get("tag"):
        match["tag_ids"] = ObjectId(filters["tag"])
    if filters.get("date_from"):
        match.setdefault("exit_time", {})
        match["exit_time"]["$gte"] = _parse_date_from(
            filters["date_from"]
        )
    if filters.get("date_to"):
        match.setdefault("exit_time", {})
        match["exit_time"]["$lte"] = _parse_date_to(
            filters["date_to"]
        )
    return match


def _cache_key(
    user_id: str,
    filters: dict,
    r_widening: float,
    replay_mode: str,
) -> str:
    """Generate a stable cache key."""
    raw = json.dumps(
        {
            "user_id": user_id,
            "filters": {
                k: v for k, v in sorted(filters.items())
                if v is not None
            },
            "r_widening": r_widening,
            "replay_mode": replay_mode,
        },
        sort_keys=True,
        default=str,
    )
    return hashlib.sha256(raw.encode()).hexdigest()


class WhatIfService:
    """Service for stop analysis and what-if simulations."""

    def __init__(self):
        self.trade_repo = TradeRepository()
        self.tag_repo = TagRepository()
        self.market_data_service = MarketDataService()
        self.user_repo = UserRepository()

    def get_stop_analysis(
        self,
        user_id: str,
        filters: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Compute R-normalized overshoot statistics
        for wicked-out trades filtered by symbol.

        overshoot_R = abs(avg_exit_price - wish_stop_price)
                      / abs(avg_entry_price - avg_exit_price)

        Parameters:
            user_id: User ObjectId string.
            filters: Optional query filters.

        Returns:
            Dict with count, stats, and per-trade detail.
        """
        if filters is None:
            filters = {}

        # Find wicked-out tag
        wo_tag = self.tag_repo.find_by_name(
            user_id, "wicked-out"
        )
        if not wo_tag:
            return self._empty_analysis()

        match = _build_match(user_id, filters)
        match["tag_ids"] = wo_tag["_id"]
        match["wish_stop_price"] = {"$ne": None}

        trades = self.trade_repo.find_many(
            match, sort=[("exit_time", -1)], limit=0
        )

        overshoot_rs: List[float] = []
        details: List[Dict[str, Any]] = []

        for t in trades:
            entry = t.get("avg_entry_price", 0)
            exit_p = t.get("avg_exit_price", 0)
            wish = t.get("wish_stop_price")
            if wish is None:
                continue

            # R denominator: initial risk in price terms
            r_denom = abs(entry - exit_p)
            if r_denom == 0:
                continue  # skip breakeven

            overshoot = abs(exit_p - wish) / r_denom

            overshoot_rs.append(overshoot)
            details.append({
                "trade_id": str(t["_id"]),
                "symbol": t.get("symbol", ""),
                "side": t.get("side", ""),
                "entry_time": (
                    t["entry_time"].isoformat()
                    if isinstance(
                        t.get("entry_time"), datetime
                    )
                    else str(t.get("entry_time", ""))
                ),
                "net_pnl": t.get("net_pnl", 0),
                "overshoot_r": round(overshoot, 4),
            })

        if not overshoot_rs:
            return self._empty_analysis()

        q25 = _percentile(overshoot_rs, 25)
        q75 = _percentile(overshoot_rs, 75)
        confidence_intervals = build_confidence_intervals(
            overshoot_rs
        )

        return {
            "count": len(overshoot_rs),
            "mean": round(
                float(np.mean(overshoot_rs)), 4
            ),
            "median": round(
                float(np.median(overshoot_rs)), 4
            ),
            "p75": round(
                _percentile(overshoot_rs, 75), 4
            ),
            "p90": round(
                _percentile(overshoot_rs, 90), 4
            ),
            "p95": round(
                _percentile(overshoot_rs, 95), 4
            ),
            "iqr": round(q75 - q25, 4),
            "confidence_intervals": {
                key: {
                    "lower": round(interval["lower"], 4),
                    "upper": round(interval["upper"], 4),
                }
                for key, interval in confidence_intervals.items()
            },
            "details": details,
        }

    def _get_market_data_mappings(self, user_id: str) -> dict:
        """Return the effective market-data mappings for a user."""
        user = self.user_repo.find_by_id(user_id)
        return get_effective_market_data_mappings(
            user.get("market_data_mappings") if user else None
        )

    def get_wicked_out_trades(
        self,
        user_id: str,
        filters: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        List wicked-out trades with tick-data availability.

        Parameters:
            user_id: User ObjectId string.
            filters: Optional query filters.

        Returns:
            Dict with list of wicked-out trade summaries.
        """
        if filters is None:
            filters = {}

        wo_tag = self.tag_repo.find_by_name(
            user_id, "wicked-out"
        )
        if not wo_tag:
            return {"trades": []}

        match = _build_match(user_id, filters)
        match["tag_ids"] = wo_tag["_id"]

        trades = self.trade_repo.find_many(
            match, sort=[("exit_time", -1)], limit=0
        )
        market_data_mappings = self._get_market_data_mappings(
            user_id
        )

        tick_cache: Dict[
            Tuple[str, Any], bool
        ] = {}
        results: List[Dict[str, Any]] = []

        for t in trades:
            symbol = t.get("symbol", "")
            raw_sym = t.get("raw_symbol")

            entry_time = t.get("entry_time")
            if isinstance(entry_time, datetime):
                day = entry_time.date()
            else:
                day = datetime.fromisoformat(
                    str(entry_time)
                ).date()

            cache_key = (symbol, raw_sym, day)
            if cache_key not in tick_cache:
                tick_cache[cache_key] = (
                    self.market_data_service.tick_data_service.has_ticks_for_day(
                        symbol=symbol,
                        raw_symbol=raw_sym,
                        trading_day=day,
                        market_data_mappings=market_data_mappings,
                    )
                )

            results.append({
                "id": str(t["_id"]),
                "symbol": symbol,
                "side": t.get("side", ""),
                "entry_time": (
                    entry_time.isoformat()
                    if isinstance(entry_time, datetime)
                    else str(entry_time)
                ),
                "exit_time": (
                    t["exit_time"].isoformat()
                    if isinstance(
                        t.get("exit_time"), datetime
                    )
                    else str(t.get("exit_time", ""))
                ),
                "net_pnl": t.get("net_pnl", 0),
                "wish_stop_price": t.get(
                    "wish_stop_price"
                ),
                "target_price": t.get("target_price"),
                "has_tick_data": tick_cache[cache_key],
            })

        return {"trades": results}

    def simulate(
        self,
        user_id: str,
        r_widening: float,
        replay_mode: str = "ohlc",
        filters: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Simulate widening stops by xR across losing trades.

        For each losing trade with target_price and market data:
        replay either 1-minute candles or raw ticks to determine if wider stop would
        have reached the target.

        Winners: keep original P&L, recalculate R with wider stop.
        Losers with target + market data: replay the selected dataset.
        Losers without target or usable market data: keep original P&L.

        Parameters:
            user_id: User ObjectId string.
            r_widening: Stop widening factor in R units.
            replay_mode: 'ohlc' or 'tick'.
            filters: Optional query filters.

        Returns:
            Dict with original/what-if metrics and details.
        """
        if filters is None:
            filters = {}

        # Check cache
        ck = _cache_key(
            user_id, filters, r_widening, replay_mode
        )
        if ck in _sim_cache:
            ts, result = _sim_cache[ck]
            if time.time() - ts < _CACHE_TTL:
                return result

        match = _build_match(user_id, filters)
        trades = self.trade_repo.find_many(
            match, sort=[("exit_time", -1)], limit=0
        )
        user = self.user_repo.find_by_id(user_id)
        symbol_mappings = get_effective_symbol_mappings(
            user.get("symbol_mappings") if user else None
        )
        market_data_mappings = get_effective_market_data_mappings(
            user.get("market_data_mappings") if user else None
        )

        original_pnls: List[float] = []
        original_grosses: List[float] = []
        whatif_pnls: List[float] = []
        whatif_grosses: List[float] = []
        original_rs: List[float] = []
        whatif_rs: List[float] = []
        details: List[Dict[str, Any]] = []
        converted = 0
        simulated = 0
        skipped = 0

        def build_detail(
            trade_doc: Dict[str, Any],
            original_pnl: float,
            new_pnl: float,
            converted_flag: bool,
            status: str,
            original_risk: float,
            fee_value: float,
            widened_risk_value: Optional[float],
        ) -> Dict[str, Any]:
            """Build simulation detail with P&L and R-multiple deltas."""
            original_r_value = calculate_r_multiple(
                original_pnl,
                original_risk,
                fee_value,
            )
            original_r = (
                round(original_r_value, 2)
                if original_r_value is not None
                else None
            )
            new_r = (
                round(new_pnl / widened_risk_value, 2)
                if widened_risk_value and widened_risk_value > 0
                else None
            )
            change_r = (
                round(new_r - original_r, 2)
                if original_r is not None and new_r is not None
                else None
            )
            detail_entry = {
                "trade_id": str(trade_doc["_id"]),
                "symbol": trade_doc.get("symbol", ""),
                "side": trade_doc.get("side", ""),
                "entry_time": (
                    entry_time.isoformat()
                    if isinstance(entry_time, datetime)
                    else str(entry_time or "")
                ),
                "original_pnl": round(original_pnl, 2),
                "new_pnl": round(new_pnl, 2),
                "original_r": original_r,
                "new_r": new_r,
                "change_r": change_r,
                "converted": converted_flag,
                "status": status,
            }
            return detail_entry

        for t in trades:
            net_pnl = t.get("net_pnl", 0)
            entry = t.get("avg_entry_price", 0)
            exit_p = t.get("avg_exit_price", 0)
            side = t.get("side", "")
            symbol = t.get("symbol", "")
            qty = t.get("total_quantity", 0)
            fee = t.get("fee", 0)
            gross_pnl = t.get("gross_pnl", net_pnl + fee)
            initial_risk = t.get("initial_risk", 0)
            entry_time = t.get("entry_time")
            widened_risk = calculate_widened_effective_risk(
                initial_risk,
                fee,
                r_widening,
            )

            original_pnls.append(net_pnl)
            original_grosses.append(gross_pnl)
            original_r = calculate_r_multiple(
                float(net_pnl),
                float(initial_risk),
                float(fee),
            )
            if original_r is not None:
                original_rs.append(original_r)

            if net_pnl >= 0:
                # Winner — keep P&L, widen initial risk
                whatif_pnls.append(net_pnl)
                whatif_grosses.append(gross_pnl)
                if widened_risk:
                    whatif_rs.append(net_pnl / widened_risk)
                skipped += 1
                details.append(
                    build_detail(
                        t,
                        net_pnl,
                        net_pnl,
                        False,
                        "winner",
                        initial_risk,
                        fee,
                        widened_risk,
                    )
                )
                continue

            # Loser — try to simulate
            raw_sym = t.get("raw_symbol")
            if isinstance(entry_time, datetime):
                day = entry_time.date()
            else:
                day = datetime.fromisoformat(
                    str(entry_time)
                ).date()

            has_market_data = self._has_replay_data_for_day(
                replay_mode=replay_mode,
                symbol=symbol,
                raw_symbol=raw_sym,
                trading_day=day,
                market_data_mappings=market_data_mappings,
            )

            target = t.get("target_price")
            if target is None and not has_market_data:
                whatif_pnls.append(net_pnl)
                whatif_grosses.append(gross_pnl)
                if widened_risk:
                    whatif_rs.append(net_pnl / widened_risk)
                skipped += 1
                details.append(
                    build_detail(
                        t,
                        net_pnl,
                        net_pnl,
                        False,
                        "no_data",
                        initial_risk,
                        fee,
                        widened_risk,
                    )
                )
                continue

            if target is None:
                # No target — keep P&L
                whatif_pnls.append(net_pnl)
                whatif_grosses.append(gross_pnl)
                if widened_risk:
                    whatif_rs.append(net_pnl / widened_risk)
                skipped += 1
                details.append(
                    build_detail(
                        t,
                        net_pnl,
                        net_pnl,
                        False,
                        "no_target",
                        initial_risk,
                        fee,
                        widened_risk,
                    )
                )
                continue

            # Calculate wider stop price
            try:
                point_value = get_point_value(
                    symbol,
                    raw_sym,
                    symbol_mappings,
                )
            except ValueError as exc:
                raise ValidationError(str(exc)) from exc

            # R in price points = |entry − exit| (fee-free,
            # consistent with overshoot_R formula).
            price_risk = abs(entry - exit_p)
            if price_risk == 0:
                # Breakeven — can't compute R
                whatif_pnls.append(net_pnl)
                whatif_grosses.append(gross_pnl)
                if widened_risk:
                    whatif_rs.append(net_pnl / widened_risk)
                skipped += 1
                details.append(
                    build_detail(
                        t,
                        net_pnl,
                        net_pnl,
                        False,
                        "no_risk",
                        initial_risk,
                        fee,
                        widened_risk,
                    )
                )
                continue

            widening_pts = price_risk * r_widening

            # Original stop ≈ exit price (that's where the
            # loser actually got stopped).  Widen from there.
            if side == "Long":
                new_stop = exit_p - widening_pts
            else:
                new_stop = exit_p + widening_pts

            if not has_market_data:
                whatif_pnls.append(net_pnl)
                whatif_grosses.append(gross_pnl)
                if widened_risk:
                    whatif_rs.append(net_pnl / widened_risk)
                skipped += 1
                details.append(
                    build_detail(
                        t,
                        net_pnl,
                        net_pnl,
                        False,
                        "no_data",
                        initial_risk,
                        fee,
                        widened_risk,
                    )
                )
                continue

            if replay_mode == "tick":
                new_pnl = self._replay_ticks(
                    symbol=symbol,
                    raw_symbol=raw_sym,
                    trade=t,
                    new_stop=new_stop,
                    target=target,
                    side=side,
                    entry=entry,
                    qty=qty,
                    fee=fee,
                    point_value=point_value,
                    market_data_mappings=market_data_mappings,
                )
            else:
                new_pnl = self._replay_bars(
                    symbol=symbol,
                    raw_symbol=raw_sym,
                    interval="1m",
                    trade=t,
                    new_stop=new_stop,
                    target=target,
                    side=side,
                    entry=entry,
                    qty=qty,
                    fee=fee,
                    point_value=point_value,
                    market_data_mappings=market_data_mappings,
                )

            if new_pnl is None:
                # Ticks don't cover trade entry — skip
                whatif_pnls.append(net_pnl)
                whatif_grosses.append(gross_pnl)
                if widened_risk:
                    whatif_rs.append(net_pnl / widened_risk)
                skipped += 1
                details.append(
                    build_detail(
                        t,
                        net_pnl,
                        net_pnl,
                        False,
                        "no_data",
                        initial_risk,
                        fee,
                        widened_risk,
                    )
                )
                continue

            was_converted = new_pnl > net_pnl
            if was_converted and new_pnl > 0:
                converted += 1
            else:
                simulated += 1

            whatif_pnls.append(new_pnl)
            whatif_grosses.append(round(new_pnl + fee, 2))
            if widened_risk:
                whatif_rs.append(new_pnl / widened_risk)
            details.append(
                build_detail(
                    t,
                    net_pnl,
                    new_pnl,
                    was_converted and new_pnl > 0,
                    "simulated",
                    initial_risk,
                    fee,
                    widened_risk,
                )
            )

        result = {
            "original": self._compute_metrics(
                original_pnls,
                original_rs,
                original_grosses,
            ),
            "what_if": self._compute_metrics(
                whatif_pnls,
                whatif_rs,
                whatif_grosses,
            ),
            "trades_total": len(trades),
            "trades_converted": converted,
            "trades_simulated": simulated,
            "trades_skipped": skipped,
            "details": details,
        }

        # Cache result
        _sim_cache[ck] = (time.time(), result)

        return result

    def _has_replay_data_for_day(
        self,
        *,
        replay_mode: str,
        symbol: str,
        raw_symbol: str | None,
        trading_day,
        market_data_mappings: dict | None = None,
    ) -> bool:
        """Return True when the selected replay source exists for a day."""

        if replay_mode == "tick":
            return self.market_data_service.tick_data_service.has_ticks_for_day(
                symbol=symbol,
                raw_symbol=raw_symbol,
                trading_day=trading_day,
                market_data_mappings=market_data_mappings,
            )

        return self.market_data_service.tick_data_service.has_ohlc_for_day(
            symbol=symbol,
            raw_symbol=raw_symbol,
            interval="1m",
            trading_day=trading_day,
            market_data_mappings=market_data_mappings,
        )

    def _replay_bars(
        self,
        symbol: str,
        raw_symbol: str | None,
        interval: str,
        trade: dict,
        new_stop: float,
        target: float,
        side: str,
        entry: float,
        qty: int,
        fee: float,
        point_value: float,
        market_data_mappings: dict | None = None,
    ) -> Optional[float]:
        """
        Replay OHLC bars to simulate wider stop outcome.

        Returns:
            Simulated net PnL, or None if bars
            don't cover the trade entry time.
        """
        entry_time = trade.get("entry_time")

        if isinstance(entry_time, datetime):
            day = entry_time.date()
        else:
            day = datetime.fromisoformat(
                str(entry_time)
            ).date()

        bars = self.market_data_service.tick_data_service.read_bars_for_day(
            symbol=symbol,
            raw_symbol=raw_symbol,
            interval=interval,
            trading_day=day,
            market_data_mappings=market_data_mappings,
        )
        if not bars:
            return None

        interval_seconds = _BAR_INTERVAL_SECONDS.get(
            interval, 60
        )

        if isinstance(entry_time, datetime):
            utc_entry = entry_time.replace(tzinfo=timezone.utc)
            entry_ts = int(utc_entry.timestamp())
        else:
            entry_ts = int(
                datetime.fromisoformat(
                    str(entry_time)
                ).replace(tzinfo=timezone.utc).timestamp()
            )

        # Include the bar that contains the trade entry time,
        # not just bars that start after it. Otherwise a mid-bar
        # entry can incorrectly skip adverse movement that
        # happened later inside the same candle.
        trade_bars = [
            bar
            for bar in bars
            if bar["time"] + interval_seconds > entry_ts
        ]
        if not trade_bars:
            return None

        for bar in trade_bars:
            high = bar["high"]
            low = bar["low"]

            if side == "Long":
                if low <= new_stop:
                    exit_price = new_stop
                    gross = (
                        (exit_price - entry)
                        * qty
                        * point_value
                    )
                    return round(gross - fee, 2)
                if high >= target:
                    exit_price = target
                    gross = (
                        (exit_price - entry)
                        * qty
                        * point_value
                    )
                    return round(gross - fee, 2)
            else:
                if high >= new_stop:
                    exit_price = new_stop
                    gross = (
                        (entry - exit_price)
                        * qty
                        * point_value
                    )
                    return round(gross - fee, 2)
                if low <= target:
                    exit_price = target
                    gross = (
                        (entry - exit_price)
                        * qty
                        * point_value
                    )
                    return round(gross - fee, 2)

        last_close = trade_bars[-1]["close"]
        if side == "Long":
            gross = (
                (last_close - entry)
                * qty
                * point_value
            )
        else:
            gross = (
                (entry - last_close)
                * qty
                * point_value
            )
        return round(gross - fee, 2)

    def _replay_ticks(
        self,
        symbol: str,
        raw_symbol: str | None,
        trade: dict,
        new_stop: float,
        target: float,
        side: str,
        entry: float,
        qty: int,
        fee: float,
        point_value: float,
        market_data_mappings: dict | None = None,
    ) -> Optional[float]:
        """
        Replay raw ticks to simulate wider stop outcome.

        Parameters:
            symbol: Trade symbol.
            raw_symbol: Original raw symbol.
            trade: Raw trade document.
            new_stop: Widened stop price.
            target: Target price.
            side: 'Long' or 'Short'.
            entry: Entry price.
            qty: Trade quantity.
            fee: Trade fee.
            point_value: Dollar per point.

        Returns:
            Simulated net PnL, or None if ticks
            don't cover the trade entry time.
        """
        entry_time = trade.get("entry_time")

        if isinstance(entry_time, datetime):
            day = entry_time.date()
        else:
            day = datetime.fromisoformat(
                str(entry_time)
            ).date()

        # Get ticks for trade day
        ticks = self.market_data_service.tick_data_service.read_ticks_for_day(
            symbol=symbol,
            raw_symbol=raw_symbol,
            trading_day=day,
            market_data_mappings=market_data_mappings,
        )
        if not ticks:
            return None

        if isinstance(entry_time, datetime):
            utc_entry = entry_time.replace(tzinfo=timezone.utc)
            entry_dt = utc_entry
        else:
            entry_dt = datetime.fromisoformat(
                str(entry_time)
            ).replace(tzinfo=timezone.utc)

        # Include ticks from entry to end of day.
        trade_ticks = [
            tick
            for tick in ticks
            if tick["timestamp"] >= entry_dt
        ]

        if not trade_ticks:
            return None

        # Replay
        for tick in trade_ticks:
            last_price = tick["last_price"]

            if side == "Long":
                if last_price <= new_stop:
                    exit_price = new_stop
                    gross = (
                        (exit_price - entry)
                        * qty
                        * point_value
                    )
                    return round(gross - fee, 2)
                if last_price >= target:
                    exit_price = target
                    gross = (
                        (exit_price - entry)
                        * qty
                        * point_value
                    )
                    return round(gross - fee, 2)
            else:
                if last_price >= new_stop:
                    exit_price = new_stop
                    gross = (
                        (entry - exit_price)
                        * qty
                        * point_value
                    )
                    return round(gross - fee, 2)
                if last_price <= target:
                    exit_price = target
                    gross = (
                        (entry - exit_price)
                        * qty
                        * point_value
                    )
                    return round(gross - fee, 2)

        # Neither stop nor target hit by EOD —
        # exit at last tick price.
        last_price = trade_ticks[-1]["last_price"]
        if side == "Long":
            gross = (
                (last_price - entry)
                * qty
                * point_value
            )
        else:
            gross = (
                (entry - last_price)
                * qty
                * point_value
            )
        return round(gross - fee, 2)

    @staticmethod
    def _compute_metrics(
        pnls: List[float],
        r_values: Optional[List[float]] = None,
        gross_values: Optional[List[float]] = None,
    ) -> Dict[str, Any]:
        """Compute summary metrics from P&L list.

        Parameters:
            pnls: List of net P&L values.

        Returns:
            Dict of summary statistics.
        """
        if not pnls:
            return {
                "total_pnl": 0,
                "avg_pnl": 0,
                "win_rate": 0,
                "total_winners": 0,
                "total_losers": 0,
                "profit_factor": 0,
                "expectancy_r": None,
            }

        loss_filter = []
        for idx, pnl in enumerate(pnls):
            gross = (
                gross_values[idx]
                if gross_values is not None
                and idx < len(gross_values)
                else pnl
            )
            loss_filter.append(
                pnl < 0 and gross != 0
            )

        total = sum(pnls)
        wins = [p for p in pnls if p > 0]
        pf_losses = [p for p in pnls if p < 0]
        losses = [
            pnl
            for idx, pnl in enumerate(pnls)
            if loss_filter[idx]
        ]
        win_rate = (
            len(wins) / len(pnls) * 100
            if pnls
            else 0
        )
        gross_profit = sum(wins)
        gross_loss = abs(sum(pf_losses))
        pf = (
            gross_profit / gross_loss
            if gross_loss > 0
            else float("inf")
            if gross_profit > 0
            else 0
        )
        return {
            "total_pnl": round(total, 2),
            "avg_pnl": round(
                total / len(pnls), 2
            ),
            "win_rate": round(win_rate, 2),
            "total_winners": len(wins),
            "total_losers": len(losses),
            "profit_factor": (
                round(pf, 2) if pf != float("inf")
                else "Inf"
            ),
            "expectancy_r": (
                round(sum(r_values) / len(r_values), 2)
                if r_values
                else None
            ),
        }

    @staticmethod
    def _empty_analysis() -> Dict[str, Any]:
        """Return empty stop analysis response."""
        return {
            "count": 0,
            "mean": 0,
            "median": 0,
            "p75": 0,
            "p90": 0,
            "p95": 0,
            "iqr": 0,
            "confidence_intervals": empty_confidence_intervals(),
            "details": [],
        }
