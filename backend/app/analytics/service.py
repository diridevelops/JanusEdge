"""Analytics service for computing trade metrics."""

import re
from collections import deque
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from bson import ObjectId

from app.analytics.monte_carlo import (
    MonteCarloParams,
    run_monte_carlo_simulation,
)
from app.extensions import mongo
from app.utils.trade_metrics import calculate_r_multiple


def _parse_date_from(value: str) -> datetime:
    """Parse date_from as inclusive lower bound."""
    return datetime.fromisoformat(value)


def _parse_date_to(value: str) -> datetime:
    """Parse date_to as inclusive upper bound.

    For date-only values (YYYY-MM-DD), include the entire
    selected day by converting to the next day minus 1 microsecond.
    """
    dt = datetime.fromisoformat(value)
    if len(value) == 10:
        return dt + timedelta(days=1) - timedelta(microseconds=1)
    return dt


def _build_base_match(
    user_id: str, filters: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Build the base $match stage for analytics pipelines.

    Filters closed, non-deleted trades for the given user
    and applies optional filters for account, symbol, side,
    tag, and date range.

    Parameters:
        user_id: The user's ObjectId string.
        filters: Dict of optional filter parameters.

    Returns:
        MongoDB $match query dict.
    """
    match = {
        "user_id": ObjectId(user_id),
        "status": "closed",
    }

    if filters.get("account"):
        match["trade_account_id"] = ObjectId(
            filters["account"]
        )

    if filters.get("symbol"):
        symbol = str(filters["symbol"]).strip()
        if symbol:
            match["symbol"] = {
                "$regex": f"^{re.escape(symbol)}$",
                "$options": "i",
            }

    if filters.get("side"):
        match["side"] = filters["side"]

    if filters.get("tag"):
        match["tag_ids"] = ObjectId(filters["tag"])

    # Date range filters on exit_time
    if filters.get("date_from") or filters.get("date_to"):
        date_filter: Dict[str, Any] = {}
        if filters.get("date_from"):
            date_filter["$gte"] = _parse_date_from(
                filters["date_from"]
            )
        if filters.get("date_to"):
            date_filter["$lte"] = _parse_date_to(
                filters["date_to"]
            )
        match["exit_time"] = date_filter

    return match


def _percentile(values: List[float], pct: float) -> float:
    """Compute linear-interpolated percentile.

    Parameters:
        values: Numeric samples.
        pct: Percentile in [0, 100].

    Returns:
        Percentile value (0.0 for empty input).
    """
    if not values:
        return 0.0

    sorted_values = sorted(values)
    if len(sorted_values) == 1:
        return float(sorted_values[0])

    rank = (pct / 100.0) * (len(sorted_values) - 1)
    low_idx = int(rank)
    high_idx = min(low_idx + 1, len(sorted_values) - 1)
    weight = rank - low_idx
    low_val = float(sorted_values[low_idx])
    high_val = float(sorted_values[high_idx])
    return low_val + (high_val - low_val) * weight


def _mongo_effective_risk_expr() -> Dict[str, Any]:
    """Build MongoDB expression for fee-inclusive risk."""
    return {
        "$add": [
            "$initial_risk",
            {"$ifNull": ["$fee", 0]},
        ]
    }


class AnalyticsService:
    """
    Service for computing trade analytics and metrics.

    Uses MongoDB aggregation pipelines for efficient
    server-side computation of summary statistics,
    equity curves, drawdowns, and other analytics.
    """

    def get_summary(
        self,
        user_id: str,
        filters: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Compute summary metrics for closed trades.

        Calculates total trades, win rate, P&L totals,
        profit factor, expectancy, and more.

        Parameters:
            user_id: The user's ObjectId string.
            filters: Optional filter parameters.

        Returns:
            Dict of summary metrics.
        """
        if filters is None:
            filters = {}

        match = _build_base_match(user_id, filters)

        pipeline = [
            {"$match": match},
            # Compute per-contract P&L for each trade
            {
                "$addFields": {
                    "pnl_per_contract": {
                        "$cond": {
                            "if": {
                                "$gt": [
                                    "$total_quantity",
                                    0,
                                ]
                            },
                            "then": {
                                "$divide": [
                                    "$net_pnl",
                                    "$total_quantity",
                                ]
                            },
                            "else": 0,
                        }
                    },
                    "r_multiple": {
                        "$cond": {
                            "if": {
                                "$gt": [
                                    "$initial_risk",
                                    0,
                                ]
                            },
                            "then": {
                                "$divide": [
                                    "$net_pnl",
                                    _mongo_effective_risk_expr(),
                                ]
                            },
                            "else": None,
                        }
                    }
                }
            },
            {
                "$group": {
                    "_id": None,
                    "total_trades": {"$sum": 1},
                    "total_gross_pnl": {
                        "$sum": "$gross_pnl"
                    },
                    "total_net_pnl": {
                        "$sum": "$net_pnl"
                    },
                    "total_fees": {"$sum": "$fee"},
                    "winners": {
                        "$sum": {
                            "$cond": [
                                {"$gt": ["$net_pnl", 0]},
                                1,
                                0,
                            ]
                        }
                    },
                    "losers": {
                        "$sum": {
                            "$cond": [
                                {
                                    "$and": [
                                        {"$lt": ["$net_pnl", 0]},
                                        {"$ne": ["$gross_pnl", 0]},
                                    ]
                                },
                                1,
                                0,
                            ]
                        }
                    },
                    "breakeven": {
                        "$sum": {
                            "$cond": [
                                {
                                    "$eq": [
                                        "$gross_pnl",
                                        0,
                                    ]
                                },
                                1,
                                0,
                            ]
                        }
                    },
                    "sum_winners": {
                        "$sum": {
                            "$cond": [
                                {"$gt": ["$net_pnl", 0]},
                                "$net_pnl",
                                0,
                            ]
                        }
                    },
                    "sum_losers": {
                        "$sum": {
                            "$cond": [
                                {
                                    "$and": [
                                        {"$lt": ["$net_pnl", 0]},
                                        {"$ne": ["$gross_pnl", 0]},
                                    ]
                                },
                                "$net_pnl",
                                0,
                            ]
                        }
                    },
                    "largest_win": {"$max": "$net_pnl"},
                    "largest_loss": {"$min": "$net_pnl"},
                    "avg_holding_time": {
                        "$avg": "$holding_time_seconds"
                    },
                    "avg_executions": {
                        "$avg": "$execution_count"
                    },
                    # Per-contract aggregations
                    # for winners
                    "win_ppc_sum": {
                        "$sum": {
                            "$cond": [
                                {
                                    "$gt": [
                                        "$net_pnl",
                                        0,
                                    ]
                                },
                                "$pnl_per_contract",
                                0,
                            ]
                        }
                    },
                    "win_ppc_max": {
                        "$max": {
                            "$cond": [
                                {
                                    "$gt": [
                                        "$net_pnl",
                                        0,
                                    ]
                                },
                                "$pnl_per_contract",
                                -999999999,
                            ]
                        }
                    },
                    # Per-contract aggregations
                    # for losers
                    "loss_ppc_sum": {
                        "$sum": {
                            "$cond": [
                                {
                                    "$and": [
                                        {"$lt": ["$net_pnl", 0]},
                                        {"$ne": ["$gross_pnl", 0]},
                                    ]
                                },
                                "$pnl_per_contract",
                                0,
                            ]
                        }
                    },
                    "loss_ppc_min": {
                        "$min": {
                            "$cond": [
                                {
                                    "$and": [
                                        {"$lt": ["$net_pnl", 0]},
                                        {"$ne": ["$gross_pnl", 0]},
                                    ]
                                },
                                "$pnl_per_contract",
                                999999999,
                            ]
                        }
                    },
                    "r_defined_trades": {
                        "$sum": {
                            "$cond": [
                                {
                                    "$ne": [
                                        "$r_multiple",
                                        None,
                                    ]
                                },
                                1,
                                0,
                            ]
                        }
                    },
                    "r_winners": {
                        "$sum": {
                            "$cond": [
                                {
                                    "$gt": [
                                        "$r_multiple",
                                        0,
                                    ]
                                },
                                1,
                                0,
                            ]
                        }
                    },
                    "r_losers": {
                        "$sum": {
                            "$cond": [
                                {
                                    "$lt": [
                                        "$r_multiple",
                                        0,
                                    ]
                                },
                                1,
                                0,
                            ]
                        }
                    },
                    "sum_win_r": {
                        "$sum": {
                            "$cond": [
                                {
                                    "$gt": [
                                        "$r_multiple",
                                        0,
                                    ]
                                },
                                "$r_multiple",
                                0,
                            ]
                        }
                    },
                    "sum_loss_r": {
                        "$sum": {
                            "$cond": [
                                {
                                    "$lt": [
                                        "$r_multiple",
                                        0,
                                    ]
                                },
                                "$r_multiple",
                                0,
                            ]
                        }
                    },
                }
            },
        ]

        results = list(
            mongo.db.trades.aggregate(pipeline)
        )

        if not results:
            return _empty_summary()

        data = results[0]
        total = data["total_trades"]
        winners_count = data["winners"]
        sum_winners = data["sum_winners"]
        sum_losers = data["sum_losers"]

        win_rate = (
            (winners_count / total * 100)
            if total > 0
            else 0.0
        )

        avg_winner = (
            (sum_winners / winners_count)
            if winners_count > 0
            else 0.0
        )
        avg_loser = (
            (sum_losers / data["losers"])
            if data["losers"] > 0
            else 0.0
        )

        # Expectancy: (win_rate% × avg_winner) +
        #             ((1 - win_rate%) × avg_loser)
        win_pct = win_rate / 100.0
        expectancy = (win_pct * avg_winner) + (
            (1 - win_pct) * avg_loser
        )

        # APPT: Average Profitability Per Trade
        appt = (
            (data["total_net_pnl"] / total)
            if total > 0
            else 0.0
        )

        # Per-contract (per-share) metrics
        losers_count = data["losers"]
        win_per_share_avg = (
            (data["win_ppc_sum"] / winners_count)
            if winners_count > 0
            else 0.0
        )
        win_per_share_high = (
            data["win_ppc_max"]
            if winners_count > 0
            else 0.0
        )
        # Sentinel check: -999999999 means no winners
        if win_per_share_high == -999999999:
            win_per_share_high = 0.0

        loss_per_share_avg = (
            (data["loss_ppc_sum"] / losers_count)
            if losers_count > 0
            else 0.0
        )
        loss_per_share_high = (
            data["loss_ppc_min"]
            if losers_count > 0
            else 0.0
        )
        # Sentinel check: 999999999 means no losers
        if loss_per_share_high == 999999999:
            loss_per_share_high = 0.0

        # P/L Ratio: avg win ÷ |avg loss|
        pl_ratio = (
            (avg_winner / abs(avg_loser))
            if avg_loser != 0
            else None
        )

        expectancy_r = None
        wl_ratio_r = None
        median_r = None
        profit_factor_r = None
        avg_initial_risk = 0.0
        win_per_share_p95 = 0.0
        loss_per_share_p05 = 0.0

        trade_details = list(
            mongo.db.trades.find(
                match,
                {
                    "net_pnl": 1,
                    "initial_risk": 1,
                    "fee": 1,
                    "total_quantity": 1,
                },
            )
        )

        pf_loss_sum = sum(
            float(trade.get("net_pnl", 0.0))
            for trade in trade_details
            if float(trade.get("net_pnl", 0.0)) < 0
        )

        # Net profit factor includes fee-only breakeven trades
        # (gross == 0, net < 0) in the losing denominator.
        profit_factor = (
            (sum_winners / abs(pf_loss_sum))
            if pf_loss_sum != 0
            else float("inf")
            if sum_winners > 0
            else 0.0
        )

        per_share_wins: List[float] = []
        per_share_losses: List[float] = []
        r_trades = []
        for trade in trade_details:
            qty = trade.get("total_quantity", 0)
            pnl = float(trade.get("net_pnl", 0.0))
            if qty and qty > 0:
                per_share = pnl / qty
                if pnl > 0:
                    per_share_wins.append(per_share)
                elif pnl < 0:
                    per_share_losses.append(per_share)

            risk = trade.get("initial_risk")
            if risk and risk > 0:
                r_trades.append(trade)

        win_per_share_p95 = _percentile(
            per_share_wins, 95
        )
        loss_per_share_p05 = _percentile(
            per_share_losses, 5
        )

        if r_trades:
            avg_initial_risk = sum(
                float(t["initial_risk"]) for t in r_trades
            ) / len(r_trades)

        if r_trades:
            r_values = [
                calculate_r_multiple(
                    float(t["net_pnl"]),
                    float(t["initial_risk"]),
                    float(t.get("fee", 0.0)),
                )
                for t in r_trades
            ]
            r_values = [
                value for value in r_values
                if value is not None
            ]
            win_r_values = [r for r in r_values if r > 0]
            loss_r_values = [r for r in r_values if r < 0]
            r_win_rate = len(win_r_values) / len(
                r_values
            )
            avg_win_r = (
                sum(win_r_values) / len(win_r_values)
                if win_r_values
                else 0.0
            )
            avg_loss_r = (
                abs(sum(loss_r_values) / len(loss_r_values))
                if loss_r_values
                else 0.0
            )
            expectancy_r = (
                r_win_rate * avg_win_r
            ) - ((1 - r_win_rate) * avg_loss_r)
            wl_ratio_r = (
                avg_win_r / avg_loss_r
                if avg_loss_r > 0
                else None
            )
            median_r = _percentile(r_values, 50)
            sum_win_r = sum(win_r_values)
            sum_loss_r_abs = abs(sum(loss_r_values))
            if sum_loss_r_abs > 0:
                profit_factor_r = (
                    sum_win_r / sum_loss_r_abs
                )
            elif sum_win_r > 0:
                profit_factor_r = None
            else:
                profit_factor_r = 0.0

        return {
            "total_trades": total,
            "winners": winners_count,
            "losers": losers_count,
            "breakeven": data["breakeven"],
            "win_rate": round(win_rate, 2),
            "total_gross_pnl": round(
                data["total_gross_pnl"], 2
            ),
            "total_net_pnl": round(
                data["total_net_pnl"], 2
            ),
            "total_fees": round(data["total_fees"], 2),
            "avg_winner": round(avg_winner, 2),
            "avg_loser": round(avg_loser, 2),
            "largest_win": round(data["largest_win"], 2),
            "largest_loss": round(
                data["largest_loss"], 2
            ),
            "profit_factor": (
                round(profit_factor, 2)
                if profit_factor != float("inf")
                else None
            ),
            "expectancy": round(expectancy, 2),
            "avg_holding_time_seconds": round(
                data["avg_holding_time"], 2
            ),
            "avg_executions": round(
                data["avg_executions"], 2
            ),
            "appt": round(appt, 2),
            "pl_ratio": (
                round(pl_ratio, 2)
                if pl_ratio is not None
                else None
            ),
            "expectancy_r": (
                round(expectancy_r, 2)
                if expectancy_r is not None
                else None
            ),
            "wl_ratio_r": (
                round(wl_ratio_r, 2)
                if wl_ratio_r is not None
                else None
            ),
            "win_per_share_avg": round(
                win_per_share_avg, 2
            ),
            "win_per_share_high": round(
                win_per_share_high, 2
            ),
            "loss_per_share_avg": round(
                loss_per_share_avg, 2
            ),
            "loss_per_share_high": round(
                loss_per_share_high, 2
            ),
            "win_per_share_p95": round(
                win_per_share_p95, 2
            ),
            "loss_per_share_p05": round(
                loss_per_share_p05, 2
            ),
            "median_r": (
                round(median_r, 2)
                if median_r is not None
                else None
            ),
            "profit_factor_r": (
                round(profit_factor_r, 2)
                if profit_factor_r is not None
                else None
            ),
            "avg_initial_risk": round(
                avg_initial_risk, 2
            ),
        }

    def get_trade_pnls(
        self,
        user_id: str,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Return per-trade net P&L for bootstrap resampling.

        Returns a lightweight list of {net_pnl} dicts
        for all closed trades matching filters.

        Parameters:
            user_id: The user's ObjectId string.
            filters: Optional filter parameters.

        Returns:
            List of dicts with net_pnl values.
        """
        if filters is None:
            filters = {}

        match = _build_base_match(user_id, filters)

        trades = mongo.db.trades.find(
            match,
            {
                "net_pnl": 1,
                "initial_risk": 1,
                "fee": 1,
                "_id": 0,
            },
        ).sort("exit_time", 1)

        results: List[Dict[str, Any]] = []
        for t in trades:
            pnl = round(t["net_pnl"], 2)
            r_value = calculate_r_multiple(
                pnl,
                float(t.get("initial_risk", 0.0)),
                float(t.get("fee", 0.0)),
            )
            r_mul = (
                round(r_value, 4)
                if r_value is not None
                else None
            )
            results.append(
                {"net_pnl": pnl, "r_multiple": r_mul}
            )
        return results

    def get_monte_carlo(
        self,
        user_id: str,
        params: MonteCarloParams,
        filters: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Run Monte Carlo simulation for dashboard analytics."""
        if filters is None:
            filters = {}

        r_multiples: List[float] = []
        bootstrap_trade_count = 0

        if params.mode == "bootstrap":
            match = _build_base_match(user_id, filters)
            trades = list(
                mongo.db.trades.find(
                    match,
                    {
                        "net_pnl": 1,
                        "initial_risk": 1,
                        "fee": 1,
                        "_id": 0,
                    },
                )
            )
            bootstrap_trade_count = len(trades)
            for trade in trades:
                r_value = calculate_r_multiple(
                    float(trade["net_pnl"]),
                    float(trade.get("initial_risk", 0.0)),
                    float(trade.get("fee", 0.0)),
                )
                if r_value is not None:
                    r_multiples.append(r_value)

        return run_monte_carlo_simulation(
            params,
            r_multiples,
            bootstrap_trade_count=bootstrap_trade_count,
        )

    def get_equity_curve(
        self,
        user_id: str,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Compute daily equity curve with cumulative P&L.

        Groups trades by exit date, computing daily PnL,
        cumulative PnL, trade count, winners, APPT,
        and win rate per day.

        Parameters:
            user_id: The user's ObjectId string.
            filters: Optional filter parameters.

        Returns:
            List of daily equity curve point dicts.
        """
        if filters is None:
            filters = {}

        match = _build_base_match(user_id, filters)

        pipeline = [
            {"$match": match},
            {
                "$group": {
                    "_id": {
                        "$dateToString": {
                            "format": "%Y-%m-%d",
                            "date": "$exit_time",
                        }
                    },
                    "daily_pnl": {
                        "$sum": "$net_pnl"
                    },
                    "trade_count": {"$sum": 1},
                    "winners": {
                        "$sum": {
                            "$cond": [
                                {
                                    "$gt": [
                                        "$net_pnl",
                                        0,
                                    ]
                                },
                                1,
                                0,
                            ]
                        }
                    },
                }
            },
            {"$sort": {"_id": 1}},
        ]

        results = list(
            mongo.db.trades.aggregate(pipeline)
        )

        cumulative = 0.0
        curve = []
        for r in results:
            cumulative += r["daily_pnl"]
            trade_count = r["trade_count"]
            winners = r["winners"]
            appt = (
                r["daily_pnl"] / trade_count
                if trade_count > 0
                else 0.0
            )
            win_rate = (
                winners / trade_count * 100
                if trade_count > 0
                else 0.0
            )
            curve.append(
                {
                    "date": r["_id"],
                    "daily_pnl": round(
                        r["daily_pnl"], 2
                    ),
                    "cumulative_pnl": round(
                        cumulative, 2
                    ),
                    "trade_count": trade_count,
                    "winners": winners,
                    "appt": round(appt, 2),
                    "win_rate": round(win_rate, 2),
                }
            )

        return curve

    def get_drawdown(
        self,
        user_id: str,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Compute drawdown series from equity curve.

        Tracks peak equity and current drawdown at each
        trade close.

        Parameters:
            user_id: The user's ObjectId string.
            filters: Optional filter parameters.

        Returns:
            List of {time, drawdown, drawdown_pct} dicts.
        """
        curve = self.get_equity_curve(user_id, filters)

        if not curve:
            return []

        peak = 0.0
        drawdowns = []
        for point in curve:
            cumulative = point["cumulative_pnl"]
            if cumulative > peak:
                peak = cumulative
            dd = cumulative - peak
            dd_pct = (
                (dd / peak * 100) if peak > 0 else 0.0
            )
            drawdowns.append(
                {
                    "date": point["date"],
                    "cumulative_pnl": cumulative,
                    "drawdown": round(dd, 2),
                    "drawdown_pct": round(dd_pct, 2),
                }
            )

        return drawdowns

    def get_calendar(
        self,
        user_id: str,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Compute daily P&L for calendar heatmap.

        Groups trades by exit date and sums net P&L.

        Parameters:
            user_id: The user's ObjectId string.
            filters: Optional filter parameters.

        Returns:
            List of {date, net_pnl, trade_count} dicts.
        """
        if filters is None:
            filters = {}

        match = _build_base_match(user_id, filters)

        pipeline = [
            {"$match": match},
            {
                "$group": {
                    "_id": {
                        "$dateToString": {
                            "format": "%Y-%m-%d",
                            "date": "$exit_time",
                        }
                    },
                    "net_pnl": {"$sum": "$net_pnl"},
                    "gross_pnl": {"$sum": "$gross_pnl"},
                    "trade_count": {"$sum": 1},
                }
            },
            {"$sort": {"_id": 1}},
        ]

        results = list(
            mongo.db.trades.aggregate(pipeline)
        )

        return [
            {
                "date": r["_id"],
                "net_pnl": round(r["net_pnl"], 2),
                "gross_pnl": round(r["gross_pnl"], 2),
                "trade_count": r["trade_count"],
            }
            for r in results
        ]

    def get_distribution(
        self,
        user_id: str,
        filters: Optional[Dict[str, Any]] = None,
        bucket_size: float = 50.0,
    ) -> List[Dict[str, Any]]:
        """
        Compute P&L distribution histogram.

        Groups trades into fixed-size P&L buckets.

        Parameters:
            user_id: The user's ObjectId string.
            filters: Optional filter parameters.
            bucket_size: Width of each histogram bucket.

        Returns:
            List of {bucket, count} dicts sorted by bucket.
        """
        if filters is None:
            filters = {}

        match = _build_base_match(user_id, filters)

        pipeline = [
            {"$match": match},
            {
                "$project": {
                    "bucket": {
                        "$multiply": [
                            {
                                "$floor": {
                                    "$divide": [
                                        "$net_pnl",
                                        bucket_size,
                                    ]
                                }
                            },
                            bucket_size,
                        ]
                    }
                }
            },
            {
                "$group": {
                    "_id": "$bucket",
                    "count": {"$sum": 1},
                }
            },
            {"$sort": {"_id": 1}},
        ]

        results = list(
            mongo.db.trades.aggregate(pipeline)
        )

        return [
            {
                "bucket": r["_id"],
                "count": r["count"],
            }
            for r in results
        ]

    def get_time_of_day(
        self,
        user_id: str,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Compute performance by hour of day.

        Groups trades by the hour of entry_time and
        computes win rate and average P&L per hour.

        Parameters:
            user_id: The user's ObjectId string.
            filters: Optional filter parameters.

        Returns:
            List of {hour, trade_count, net_pnl,
            avg_pnl, win_rate} dicts for each hour.
        """
        if filters is None:
            filters = {}

        match = _build_base_match(user_id, filters)

        pipeline = [
            {"$match": match},
            {
                "$group": {
                    "_id": {
                        "$hour": "$entry_time"
                    },
                    "trade_count": {"$sum": 1},
                    "net_pnl": {"$sum": "$net_pnl"},
                    "avg_pnl": {"$avg": "$net_pnl"},
                    "winners": {
                        "$sum": {
                            "$cond": [
                                {
                                    "$gt": [
                                        "$net_pnl",
                                        0,
                                    ]
                                },
                                1,
                                0,
                            ]
                        }
                    },
                }
            },
            {"$sort": {"_id": 1}},
        ]

        results = list(
            mongo.db.trades.aggregate(pipeline)
        )

        return [
            {
                "hour": r["_id"],
                "trade_count": r["trade_count"],
                "net_pnl": round(r["net_pnl"], 2),
                "avg_pnl": round(r["avg_pnl"], 2),
                "win_rate": round(
                    r["winners"]
                    / r["trade_count"]
                    * 100,
                    2,
                ),
            }
            for r in results
        ]

    def get_by_tag(
        self,
        user_id: str,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Compute metrics grouped by tag.

        Unwinds tag_ids and computes trade count, net P&L,
        win rate, and profit factor per tag.

        Parameters:
            user_id: The user's ObjectId string.
            filters: Optional filter parameters.

        Returns:
            List of per-tag metric dicts including tag_id,
            trade_count, net_pnl, avg_pnl, win_rate, and
            profit_factor.
        """
        if filters is None:
            filters = {}

        match = _build_base_match(user_id, filters)

        pipeline = [
            {"$match": match},
            {"$unwind": "$tag_ids"},
            {
                "$group": {
                    "_id": "$tag_ids",
                    "trade_count": {"$sum": 1},
                    "net_pnl": {"$sum": "$net_pnl"},
                    "avg_pnl": {"$avg": "$net_pnl"},
                    "winners": {
                        "$sum": {
                            "$cond": [
                                {
                                    "$gt": [
                                        "$net_pnl",
                                        0,
                                    ]
                                },
                                1,
                                0,
                            ]
                        }
                    },
                    "sum_winners": {
                        "$sum": {
                            "$cond": [
                                {
                                    "$gt": [
                                        "$net_pnl",
                                        0,
                                    ]
                                },
                                "$net_pnl",
                                0,
                            ]
                        }
                    },
                    "sum_losers": {
                        "$sum": {
                            "$cond": [
                                {
                                    "$lt": [
                                        "$net_pnl",
                                        0,
                                    ]
                                },
                                "$net_pnl",
                                0,
                            ]
                        }
                    },
                }
            },
            {"$sort": {"net_pnl": -1}},
        ]

        results = list(
            mongo.db.trades.aggregate(pipeline)
        )

        # Look up tag names
        tag_ids = [r["_id"] for r in results]
        tags = {}
        if tag_ids:
            tag_docs = mongo.db.tags.find(
                {"_id": {"$in": tag_ids}}
            )
            tags = {
                t["_id"]: t["name"] for t in tag_docs
            }

        output = []
        for r in results:
            win_rate = (
                (r["winners"] / r["trade_count"] * 100)
                if r["trade_count"] > 0
                else 0.0
            )
            pf = (
                (r["sum_winners"] / abs(r["sum_losers"]))
                if r["sum_losers"] != 0
                else (
                    float("inf")
                    if r["sum_winners"] > 0
                    else 0.0
                )
            )
            output.append(
                {
                    "tag_id": str(r["_id"]),
                    "tag_name": tags.get(
                        r["_id"], "Unknown"
                    ),
                    "trade_count": r["trade_count"],
                    "net_pnl": round(r["net_pnl"], 2),
                    "avg_pnl": round(r["avg_pnl"], 2),
                    "win_rate": round(win_rate, 2),
                    "profit_factor": (
                        round(pf, 2)
                        if pf != float("inf")
                        else None
                    ),
                }
            )

        return output

    def get_appt_by_day_of_week(
        self,
        user_id: str,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Compute APPT grouped by day of week.

        Groups trades by entry weekday (Monday-Sunday)
        and computes APPT for each weekday bucket.

        Parameters:
            user_id: The user's ObjectId string.
            filters: Optional filter parameters.

        Returns:
            List of {day_of_week, appt, trade_count, net_pnl}
            dicts in Monday-Sunday order.
        """
        if filters is None:
            filters = {}

        match = _build_base_match(user_id, filters)
        timezone = filters.get("timezone") or "UTC"

        pipeline = [
            {"$match": match},
            {
                "$group": {
                    "_id": {
                        "$isoDayOfWeek": {
                            "date": "$entry_time",
                            "timezone": timezone,
                        }
                    },
                    "trade_count": {"$sum": 1},
                    "net_pnl": {"$sum": "$net_pnl"},
                }
            },
            {"$sort": {"_id": 1}},
        ]

        results = list(
            mongo.db.trades.aggregate(pipeline)
        )

        day_names = {
            1: "Monday",
            2: "Tuesday",
            3: "Wednesday",
            4: "Thursday",
            5: "Friday",
            6: "Saturday",
            7: "Sunday",
        }

        by_day = {
            r["_id"]: {
                "trade_count": r["trade_count"],
                "net_pnl": r["net_pnl"],
            }
            for r in results
        }

        output = []
        for day_num in range(1, 8):
            trade_count = by_day.get(day_num, {}).get(
                "trade_count", 0
            )
            net_pnl = by_day.get(day_num, {}).get(
                "net_pnl", 0.0
            )
            appt = (
                (net_pnl / trade_count)
                if trade_count > 0
                else 0.0
            )
            output.append(
                {
                    "day_of_week": day_names[day_num],
                    "appt": round(appt),
                    "trade_count": trade_count,
                    "net_pnl": round(net_pnl, 2),
                }
            )

        return output

    def get_appt_by_timeframe(
        self,
        user_id: str,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Compute APPT grouped by 15-minute entry buckets.

        Groups trades by 15-minute timeframe based on
        entry_time (e.g. 09:00, 09:15, 09:30) and computes
        APPT for each bucket.

        Parameters:
            user_id: The user's ObjectId string.
            filters: Optional filter parameters.

        Returns:
            List of {timespan_start, appt, trade_count,
            net_pnl} dicts sorted by timespan.
        """
        if filters is None:
            filters = {}

        match = _build_base_match(user_id, filters)
        timezone = filters.get("timezone") or "UTC"

        pipeline = [
            {"$match": match},
            {
                "$project": {
                    "bucket_minutes": {
                        "$add": [
                            {
                                "$multiply": [
                                    {
                                        "$hour": {
                                            "date": "$entry_time",
                                            "timezone": timezone,
                                        }
                                    },
                                    60,
                                ]
                            },
                            {
                                "$multiply": [
                                    {
                                        "$floor": {
                                            "$divide": [
                                                {
                                                    "$minute": {
                                                        "date": "$entry_time",
                                                        "timezone": timezone,
                                                    }
                                                },
                                                15,
                                            ]
                                        }
                                    },
                                    15,
                                ]
                            },
                        ]
                    },
                    "net_pnl": 1,
                }
            },
            {
                "$group": {
                    "_id": "$bucket_minutes",
                    "trade_count": {"$sum": 1},
                    "net_pnl": {"$sum": "$net_pnl"},
                }
            },
            {"$sort": {"_id": 1}},
        ]

        results = list(
            mongo.db.trades.aggregate(pipeline)
        )

        output = []
        for r in results:
            bucket_minutes = int(r["_id"])
            hour = bucket_minutes // 60
            minute = bucket_minutes % 60
            timespan_start = (
                f"{hour:02d}:{minute:02d}"
            )
            trade_count = r["trade_count"]
            net_pnl = r["net_pnl"]
            appt = (
                (net_pnl / trade_count)
                if trade_count > 0
                else 0.0
            )
            output.append(
                {
                    "timespan_start": timespan_start,
                    "appt": round(appt),
                    "trade_count": trade_count,
                    "net_pnl": round(net_pnl, 2),
                }
            )

        return output

    def get_evolution(
        self,
        user_id: str,
        filters: Optional[Dict[str, Any]] = None,
        window: int = 50,
        min_side_count: int = 5,
    ) -> List[Dict[str, Any]]:
        """
        Compute running/rolling metrics at each trade.

        Metrics include running and rolling mean R
        with 95% CI, cumulative R and net P&L,
        running APPT, and rolling trade P/L ratio.

        Parameters:
            user_id: The user's ObjectId string.
            filters: Optional filter parameters.
            window: Rolling window length.
            min_side_count: Minimum winner/loser count
                required for stable rolling P/L ratio.

        Returns:
            Ordered list of per-trade metric points.
        """
        if filters is None:
            filters = {}

        safe_window = max(5, window)
        safe_min_side = max(1, min_side_count)

        match = _build_base_match(user_id, filters)
        trades = list(
            mongo.db.trades.find(
                match,
                {
                    "net_pnl": 1,
                    "initial_risk": 1,
                    "fee": 1,
                    "entry_time": 1,
                    "exit_time": 1,
                },
            ).sort(
                [
                    ("exit_time", 1),
                    ("entry_time", 1),
                    ("_id", 1),
                ]
            )
        )

        if not trades:
            return []

        points: List[Dict[str, Any]] = []

        trade_count = 0
        cumulative_net_pnl = 0.0

        # Running R (Welford)
        running_r_count = 0
        running_r_mean = 0.0
        running_r_m2 = 0.0
        cumulative_r = 0.0

        # Running R decomposition
        running_r_wins = 0
        running_r_losses = 0
        running_sum_win_r = 0.0
        running_sum_abs_loss_r = 0.0

        # Rolling R stats
        rolling_r_values: deque[float] = deque()
        rolling_r_sum = 0.0
        rolling_r_sum_sq = 0.0

        # Rolling trade P/L ratio stats
        rolling_net_values: deque[float] = deque()
        rolling_win_count = 0
        rolling_loss_count = 0
        rolling_sum_win = 0.0
        rolling_sum_loss = 0.0

        for trade in trades:
            trade_count += 1

            net_pnl = float(trade.get("net_pnl", 0.0))
            initial_risk = float(
                trade.get("initial_risk", 0.0)
            )
            r_multiple = calculate_r_multiple(
                net_pnl,
                initial_risk,
                float(trade.get("fee", 0.0)),
            )

            cumulative_net_pnl += net_pnl
            appt_running = cumulative_net_pnl / trade_count

            # Running R accumulators (defined R only)
            if r_multiple is not None:
                running_r_count += 1
                cumulative_r += r_multiple

                delta = r_multiple - running_r_mean
                running_r_mean += delta / running_r_count
                delta2 = r_multiple - running_r_mean
                running_r_m2 += delta * delta2

                if r_multiple > 0:
                    running_r_wins += 1
                    running_sum_win_r += r_multiple
                elif r_multiple < 0:
                    running_r_losses += 1
                    running_sum_abs_loss_r += abs(
                        r_multiple
                    )

                rolling_r_values.append(r_multiple)
                rolling_r_sum += r_multiple
                rolling_r_sum_sq += (
                    r_multiple * r_multiple
                )
                if len(rolling_r_values) > safe_window:
                    removed_r = rolling_r_values.popleft()
                    rolling_r_sum -= removed_r
                    rolling_r_sum_sq -= (
                        removed_r * removed_r
                    )

            # Rolling trade P/L ratio accumulators
            rolling_net_values.append(net_pnl)
            if net_pnl > 0:
                rolling_win_count += 1
                rolling_sum_win += net_pnl
            elif net_pnl < 0:
                rolling_loss_count += 1
                rolling_sum_loss += net_pnl

            if len(rolling_net_values) > safe_window:
                removed_net = rolling_net_values.popleft()
                if removed_net > 0:
                    rolling_win_count -= 1
                    rolling_sum_win -= removed_net
                elif removed_net < 0:
                    rolling_loss_count -= 1
                    rolling_sum_loss -= removed_net

            # Running mean R + CI
            running_mean_r = None
            running_ci_low = None
            running_ci_high = None
            if running_r_count > 0:
                running_mean_r = running_r_mean
                if running_r_count > 1:
                    running_var = (
                        running_r_m2 / (running_r_count - 1)
                    )
                    running_se = (
                        (running_var**0.5)
                        / (running_r_count**0.5)
                    )
                    running_ci_low = (
                        running_mean_r - 1.96 * running_se
                    )
                    running_ci_high = (
                        running_mean_r + 1.96 * running_se
                    )

            # Rolling mean R + CI
            rolling_mean_r = None
            rolling_ci_low = None
            rolling_ci_high = None
            rolling_r_count = len(rolling_r_values)
            if rolling_r_count > 0:
                rolling_mean_r = (
                    rolling_r_sum / rolling_r_count
                )
                if rolling_r_count > 1:
                    rolling_var = (
                        rolling_r_sum_sq
                        - (
                            rolling_r_sum
                            * rolling_r_sum
                            / rolling_r_count
                        )
                    ) / (rolling_r_count - 1)
                    rolling_var = max(rolling_var, 0.0)
                    rolling_se = (
                        (rolling_var**0.5)
                        / (rolling_r_count**0.5)
                    )
                    rolling_ci_low = (
                        rolling_mean_r - 1.96 * rolling_se
                    )
                    rolling_ci_high = (
                        rolling_mean_r + 1.96 * rolling_se
                    )

            # Running R decomposition
            running_r_win_rate = None
            running_r_avg_win = None
            running_r_avg_loss_abs = None
            if running_r_count > 0:
                running_r_win_rate = (
                    running_r_wins / running_r_count
                )
            if running_r_wins > 0:
                running_r_avg_win = (
                    running_sum_win_r / running_r_wins
                )
            if running_r_losses > 0:
                running_r_avg_loss_abs = (
                    running_sum_abs_loss_r
                    / running_r_losses
                )

            # Rolling P/L ratio (trade)
            rolling_pl_ratio_trade = None
            pl_ratio_stable = False
            if (
                rolling_win_count >= safe_min_side
                and rolling_loss_count >= safe_min_side
            ):
                avg_win_trade = (
                    rolling_sum_win / rolling_win_count
                )
                avg_loss_trade = (
                    rolling_sum_loss / rolling_loss_count
                )
                if abs(avg_loss_trade) >= 1e-9:
                    rolling_pl_ratio_trade = (
                        avg_win_trade / abs(avg_loss_trade)
                    )
                    pl_ratio_stable = True

            exit_time = trade.get("exit_time")
            entry_time = trade.get("entry_time")
            points.append(
                {
                    "trade_index": trade_count,
                    "entry_time": (
                        entry_time.isoformat()
                        if isinstance(entry_time, datetime)
                        else None
                    ),
                    "exit_time": (
                        exit_time.isoformat()
                        if isinstance(exit_time, datetime)
                        else None
                    ),
                    "net_pnl": round(net_pnl, 2),
                    "initial_risk": round(initial_risk, 2),
                    "r_multiple": (
                        round(r_multiple, 4)
                        if r_multiple is not None
                        else None
                    ),
                    "included_r_count": running_r_count,
                    "running_mean_r": (
                        round(running_mean_r, 4)
                        if running_mean_r is not None
                        else None
                    ),
                    "running_mean_r_ci_low": (
                        round(running_ci_low, 4)
                        if running_ci_low is not None
                        else None
                    ),
                    "running_mean_r_ci_high": (
                        round(running_ci_high, 4)
                        if running_ci_high is not None
                        else None
                    ),
                    "rolling_mean_r": (
                        round(rolling_mean_r, 4)
                        if rolling_mean_r is not None
                        else None
                    ),
                    "rolling_mean_r_ci_low": (
                        round(rolling_ci_low, 4)
                        if rolling_ci_low is not None
                        else None
                    ),
                    "rolling_mean_r_ci_high": (
                        round(rolling_ci_high, 4)
                        if rolling_ci_high is not None
                        else None
                    ),
                    "rolling_r_count": rolling_r_count,
                    "window": safe_window,
                    "cum_r": round(cumulative_r, 4),
                    "cum_net_pnl": round(
                        cumulative_net_pnl, 2
                    ),
                    "appt_running": round(
                        appt_running, 2
                    ),
                    "rolling_pl_ratio_trade": (
                        round(rolling_pl_ratio_trade, 4)
                        if rolling_pl_ratio_trade
                        is not None
                        else None
                    ),
                    "rolling_pl_ratio_stable": pl_ratio_stable,
                    "rolling_window_wins": rolling_win_count,
                    "rolling_window_losses": (
                        rolling_loss_count
                    ),
                    "running_r_win_rate": (
                        round(running_r_win_rate, 4)
                        if running_r_win_rate
                        is not None
                        else None
                    ),
                    "running_r_avg_win": (
                        round(running_r_avg_win, 4)
                        if running_r_avg_win
                        is not None
                        else None
                    ),
                    "running_r_avg_loss_abs": (
                        round(
                            running_r_avg_loss_abs,
                            4,
                        )
                        if running_r_avg_loss_abs
                        is not None
                        else None
                    ),
                }
            )

        return points


def _empty_summary() -> Dict[str, Any]:
    """
    Return an empty summary when no trades exist.

    Returns:
        Dict with all summary fields set to zero.
    """
    return {
        "total_trades": 0,
        "winners": 0,
        "losers": 0,
        "breakeven": 0,
        "win_rate": 0.0,
        "total_gross_pnl": 0.0,
        "total_net_pnl": 0.0,
        "total_fees": 0.0,
        "avg_winner": 0.0,
        "avg_loser": 0.0,
        "largest_win": 0.0,
        "largest_loss": 0.0,
        "profit_factor": 0.0,
        "expectancy": 0.0,
        "avg_holding_time_seconds": 0.0,
        "avg_executions": 0.0,
        "appt": 0.0,
        "pl_ratio": None,
        "expectancy_r": None,
        "wl_ratio_r": None,
        "win_per_share_avg": 0.0,
        "win_per_share_high": 0.0,
        "loss_per_share_avg": 0.0,
        "loss_per_share_high": 0.0,
        "win_per_share_p95": 0.0,
        "loss_per_share_p05": 0.0,
        "median_r": None,
        "profit_factor_r": 0.0,
        "avg_initial_risk": 0.0,
    }
