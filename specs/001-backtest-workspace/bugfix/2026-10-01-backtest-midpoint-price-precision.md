# Bug Fix: Midpoint candle precision blocked simulated market fills

**Date:** 2026-10-01

## Bug

Advancing an accepted market order could show `open must use no more than 5 decimal places.` A market order uses the next candle's open for its fill. The live replay's Place order action itself accepted the diagnostic order and cleared the alert; the rejection came from processing a candle value.

## Root Cause

The COMB provider builds each OHLC price by averaging the corresponding bid and ask prices. Even when both quotes use five decimal places, their midpoint can contain a sixth fractional digit. Simulation code passed these source candle prices through the same strict validator used for submitted prices, so a valid midpoint such as `1.200005` was rejected as an invalid executable price.

## Fix

Separated finite source-candle price validation from strict instrument-precision validation for user-submitted prices. Replay now compares raw midpoint OHLC values, normalizes market sizing/mark references to the frozen instrument precision, and rounds actual market fills adversely to that precision after applying spread and slippage. Limit prices and stop/target inputs remain subject to the original precision rules. Updated manual close and protection paths to normalize source close prices as well.

## Verification

- `pytest -q tests/test_backtests/test_backtest_simulation.py tests/test_backtests/test_backtest_replay_routes.py tests/test_backtests/test_simulation_service.py`: 31 passed, 5 existing `mongomock` deprecation warnings.
- The route regression uses a six-decimal midpoint close and next-candle open; it verifies market submission, fill, state mark, protection edit, and manual close complete successfully. Unit tests also cover half-tick limit-range and protective-stop OHLC values, adverse fill rounding, and continued rejection of extra-precision user prices.
- In the built-in browser, Place order succeeded after the change. I canceled only the diagnostic order; the two existing working orders remain. I did not advance the live replay because those existing market orders would fill. The isolated route test covers that execution path.
- Full backend and frontend suites were not run for this backend-only fix.
