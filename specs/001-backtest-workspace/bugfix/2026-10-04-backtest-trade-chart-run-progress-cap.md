# Bug Fix: Cap Backtest Trade Charts at Replay Progress

**Date:** 2026-10-04

## Bug

Backtest trade detail charts requested candles through the selected run period, so they could display candles later than the run's furthest replay position. Charts should stop after the furthest candle reached.

## Root Cause

`BacktestService.get_chart_candles` clipped requests to the run context and selected-period end but did not use `replay_cursor`. It then aggregated the selected rows, allowing later unvisited one-minute candles into both one-minute and larger-interval charts.

## Fix

Cap the exclusive chart range end at one minute after `furthest_time_ms`, with `time_ms` as the legacy-cursor fallback. Continue enforcing request and run boundaries. Larger intervals are aggregated only from the candles in the capped range.

## Verification

- `backend\.venv\Scripts\python.exe -m pytest -q tests/test_backtests/test_backtest_replay_routes.py` — 16 passed; five existing `mongomock` deprecation warnings.
- `git diff --check` — passed.
- Browser UI check — not run.
