"""Monte Carlo helpers for analytics simulations."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Dict, List


NUM_SIMULATIONS = 50
MAX_DISPLAY_LINES = 15
MAX_CHART_POINTS = 300


@dataclass(frozen=True)
class MonteCarloParams:
    """Validated Monte Carlo request parameters."""

    mode: str
    starting_equity: float
    win_rate: float
    win_loss_ratio: float
    risk_fixed: float
    risk_pct: float
    min_risk: float
    risk_mode: str
    seed: int
    num_trades: int


class Mulberry32:
    """Deterministic PRNG matching the frontend worker implementation."""

    def __init__(self, seed: int):
        self.state = seed & 0xFFFFFFFF

    @staticmethod
    def _imul(left: int, right: int) -> int:
        """Emulate JavaScript's 32-bit integer multiplication."""
        return ((left & 0xFFFFFFFF) * (right & 0xFFFFFFFF)) & 0xFFFFFFFF

    def random(self) -> float:
        """Return the next pseudo-random float in [0, 1)."""
        self.state = (self.state + 0x6D2B79F5) & 0xFFFFFFFF
        value = self.state
        value = self._imul(value ^ (value >> 15), value | 1)
        value ^= (
            value
            + self._imul(value ^ (value >> 7), value | 61)
        ) & 0xFFFFFFFF
        result = (value ^ (value >> 14)) & 0xFFFFFFFF
        return result / 4294967296.0


def _risk_for_trade(
    equity: float,
    risk_mode: str,
    risk_fixed: float,
    risk_pct: float,
    min_risk: float,
) -> float:
    """Compute risk size for a trade step."""
    if risk_mode == "fixed":
        return risk_fixed
    return max((risk_pct / 100.0) * equity, min_risk)


def _run_parametric_simulation(
    params: MonteCarloParams,
) -> List[List[float]]:
    """Run parametric Monte Carlo simulations."""
    win_rate = params.win_rate / 100.0
    rng = Mulberry32(params.seed)
    simulations: List[List[float]] = []

    for _ in range(NUM_SIMULATIONS):
        equity_curve = [params.starting_equity]
        for trade_index in range(params.num_trades):
            current_equity = equity_curve[-1]
            if current_equity <= 0:
                for _ in range(trade_index, params.num_trades):
                    equity_curve.append(0.0)
                break

            risk = _risk_for_trade(
                current_equity,
                params.risk_mode,
                params.risk_fixed,
                params.risk_pct,
                params.min_risk,
            )
            if rng.random() < win_rate:
                next_equity = current_equity + (risk * params.win_loss_ratio)
            else:
                next_equity = max(0.0, current_equity - risk)
            equity_curve.append(next_equity)

        simulations.append(equity_curve)

    return simulations


def _run_bootstrap_simulation(
    params: MonteCarloParams,
    r_multiples: List[float],
) -> List[List[float]]:
    """Run bootstrap Monte Carlo simulations using stored trade R values."""
    rng = Mulberry32(params.seed)
    simulations: List[List[float]] = []
    count = len(r_multiples)

    for _ in range(NUM_SIMULATIONS):
        equity_curve = [params.starting_equity]
        for trade_index in range(params.num_trades):
            current_equity = equity_curve[-1]
            if current_equity <= 0:
                for _ in range(trade_index, params.num_trades):
                    equity_curve.append(0.0)
                break

            risk = _risk_for_trade(
                current_equity,
                params.risk_mode,
                params.risk_fixed,
                params.risk_pct,
                params.min_risk,
            )
            index = min(int(rng.random() * count), count - 1)
            next_equity = max(
                0.0,
                current_equity + (r_multiples[index] * risk),
            )
            equity_curve.append(next_equity)

        simulations.append(equity_curve)

    return simulations


def _effective_bootstrap_metrics(
    r_multiples: List[float],
    fallback_win_rate: float,
    fallback_win_loss_ratio: float,
) -> Dict[str, float]:
    """Compute effective win-rate inputs for bootstrap simulations."""
    if not r_multiples:
        return {
            "win_rate": fallback_win_rate,
            "win_loss_ratio": fallback_win_loss_ratio,
        }

    wins = [value for value in r_multiples if value > 0]
    losses = [value for value in r_multiples if value < 0]
    win_rate = (len(wins) / len(r_multiples)) * 100.0
    avg_win_r = sum(wins) / len(wins) if wins else 0.0
    avg_loss_r = (
        abs(sum(losses) / len(losses)) if losses else 0.0
    )
    win_loss_ratio = (
        avg_win_r / avg_loss_r if avg_loss_r > 0 else 0.0
    )
    return {
        "win_rate": win_rate,
        "win_loss_ratio": win_loss_ratio,
    }


def _compute_metrics(
    simulations: List[List[float]],
    starting_equity: float,
    win_rate: float,
    win_loss_ratio: float,
) -> Dict[str, float]:
    """Compute Monte Carlo summary metrics from simulations."""
    win_rate_ratio = win_rate / 100.0
    kelly = (
        win_rate_ratio - ((1 - win_rate_ratio) / win_loss_ratio)
        if win_loss_ratio > 0
        else 0.0
    )
    expectation = (win_rate_ratio * win_loss_ratio) - (1 - win_rate_ratio)

    max_drawdowns: List[float] = []
    max_drawdown_pcts: List[float] = []
    final_equities: List[float] = []
    global_min_equity = float("inf")
    global_max_equity = float("-inf")
    global_max_consecutive_wins = 0
    global_max_consecutive_losses = 0
    ruined_count = 0

    for equity_curve in simulations:
        peak = equity_curve[0]
        max_drawdown = 0.0
        max_drawdown_pct = 0.0
        consecutive_wins = 0
        consecutive_losses = 0
        max_consecutive_wins = 0
        max_consecutive_losses = 0
        hit_zero = False

        for index in range(1, len(equity_curve)):
            value = equity_curve[index]
            previous = equity_curve[index - 1]
            if value <= 0:
                hit_zero = True
            if value > peak:
                peak = value
            drawdown = peak - value
            if drawdown > max_drawdown:
                max_drawdown = drawdown
            if peak > 0:
                drawdown_pct = 1 - (value / peak)
                if drawdown_pct > max_drawdown_pct:
                    max_drawdown_pct = drawdown_pct
            global_min_equity = min(global_min_equity, value)
            global_max_equity = max(global_max_equity, value)
            if value > previous:
                consecutive_wins += 1
                consecutive_losses = 0
                max_consecutive_wins = max(
                    max_consecutive_wins, consecutive_wins
                )
            elif value < previous:
                consecutive_losses += 1
                consecutive_wins = 0
                max_consecutive_losses = max(
                    max_consecutive_losses, consecutive_losses
                )

        if hit_zero:
            ruined_count += 1
        max_drawdowns.append(max_drawdown)
        max_drawdown_pcts.append(max_drawdown_pct)
        final_equities.append(equity_curve[-1])
        global_max_consecutive_wins = max(
            global_max_consecutive_wins, max_consecutive_wins
        )
        global_max_consecutive_losses = max(
            global_max_consecutive_losses, max_consecutive_losses
        )

    biggest_max_drawdown = max(max_drawdowns)
    avg_max_drawdown = sum(max_drawdowns) / len(max_drawdowns)
    biggest_max_drawdown_pct = max(max_drawdown_pcts) * 100.0
    avg_max_drawdown_pct = (
        sum(max_drawdown_pcts) / len(max_drawdown_pcts)
    ) * 100.0
    avg_final_equity = sum(final_equities) / len(final_equities)
    avg_performance_pct = (
        (avg_final_equity / starting_equity) * 100.0
        if starting_equity > 0
        else 0.0
    )
    return_on_max_drawdown = (
        avg_final_equity / biggest_max_drawdown
        if biggest_max_drawdown > 0
        else 0.0
    )
    pct_profitable = (
        len(
            [equity for equity in final_equities if equity > starting_equity]
        )
        / len(simulations)
    ) * 100.0
    pct_ruined = (ruined_count / len(simulations)) * 100.0

    return {
        "kelly": kelly,
        "expectation": expectation,
        "biggestMaxDrawdown": biggest_max_drawdown,
        "biggestMaxDrawdownPct": biggest_max_drawdown_pct,
        "avgMaxDrawdown": avg_max_drawdown,
        "avgMaxDrawdownPct": avg_max_drawdown_pct,
        "minEquity": global_min_equity,
        "maxEquity": global_max_equity,
        "avgFinalEquity": avg_final_equity,
        "avgPerformancePct": avg_performance_pct,
        "returnOnMaxDrawdown": return_on_max_drawdown,
        "maxConsecutiveWins": global_max_consecutive_wins,
        "maxConsecutiveLosses": global_max_consecutive_losses,
        "pctProfitable": pct_profitable,
        "pctRuined": pct_ruined,
    }


def _build_chart_data(
    simulations: List[List[float]], num_trades: int
) -> Dict[str, Any]:
    """Build chart data compatible with the current dashboard chart."""
    step = max(1, math.ceil(num_trades / MAX_CHART_POINTS))
    points: List[Dict[str, float]] = []

    for trade_index in range(0, num_trades + 1, step):
        point: Dict[str, float] = {
            "trade": float(trade_index),
            "avgEquity": 0.0,
        }
        total = 0.0
        for sim_index in range(NUM_SIMULATIONS):
            value = simulations[sim_index][trade_index]
            if sim_index < MAX_DISPLAY_LINES:
                point[f"sim_{sim_index}"] = value
            total += value
        point["avgEquity"] = total / NUM_SIMULATIONS
        points.append(point)

    last = points[-1] if points else None
    if last and int(last["trade"]) != num_trades:
        point = {"trade": float(num_trades), "avgEquity": 0.0}
        total = 0.0
        for sim_index in range(NUM_SIMULATIONS):
            value = simulations[sim_index][num_trades]
            if sim_index < MAX_DISPLAY_LINES:
                point[f"sim_{sim_index}"] = value
            total += value
        point["avgEquity"] = total / NUM_SIMULATIONS
        points.append(point)

    return {"points": points, "step": step}


def run_monte_carlo_simulation(
    params: MonteCarloParams,
    r_multiples: List[float],
    bootstrap_trade_count: int,
) -> Dict[str, Any]:
    """Run Monte Carlo simulations and return chart, metrics, metadata."""
    requested_mode = params.mode
    effective_mode = (
        "bootstrap"
        if requested_mode == "bootstrap" and r_multiples
        else "parametric"
    )

    if effective_mode == "bootstrap":
        simulations = _run_bootstrap_simulation(params, r_multiples)
    else:
        simulations = _run_parametric_simulation(params)

    effective_inputs = _effective_bootstrap_metrics(
        r_multiples,
        params.win_rate,
        params.win_loss_ratio,
    )
    if effective_mode != "bootstrap":
        effective_inputs = {
            "win_rate": params.win_rate,
            "win_loss_ratio": params.win_loss_ratio,
        }

    metrics = _compute_metrics(
        simulations,
        params.starting_equity,
        effective_inputs["win_rate"],
        effective_inputs["win_loss_ratio"],
    )
    chart_data = _build_chart_data(simulations, params.num_trades)

    return {
        "chart_data": chart_data["points"],
        "metrics": metrics,
        "metadata": {
            "requested_mode": requested_mode,
            "effective_mode": effective_mode,
            "simulation_count": NUM_SIMULATIONS,
            "displayed_simulation_count": MAX_DISPLAY_LINES,
            "chart_step": chart_data["step"],
            "num_trades": params.num_trades,
            "seed": params.seed,
            "bootstrap_trade_count": bootstrap_trade_count,
            "bootstrap_r_multiple_count": len(r_multiples),
            "effective_win_rate": effective_inputs["win_rate"],
            "effective_win_loss_ratio": effective_inputs[
                "win_loss_ratio"
            ],
        },
    }