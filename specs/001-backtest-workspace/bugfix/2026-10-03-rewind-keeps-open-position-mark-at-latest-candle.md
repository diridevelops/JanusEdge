# Bug Fix: Keep Open Position Mark at the Latest Candle During Rewind

**Date:** 2026-10-03

## Bug

Rewinding the replay changed an open position's displayed unrealized P&L and chart pips label to values from the earlier displayed candle. The order and fill remained committed, so the displayed mark did not match the simulation's latest reached bar.

## Root Cause

`BacktestSimulationEffects.get_state` calculated the quote-to-USD rate and each open position's unrealized P&L from `replay_cursor.source_candle_index`, which tracks the currently viewed candle. The chart overlay separately calculated P&L in instrument units from the displayed chart close. Rewind changes the cursor without reversing committed simulation history.

## Fix

Calculate the open-position mark and quote conversion from `furthest_source_candle_index`, falling back to the saved cursor for legacy runs, and expose the mark price to the chart overlay. The overlay uses that price for the pips label while retaining the displayed candle close for chart interactions and stop validation.

## Verification

- Backend replay-route file: 10 passed; simulation-service file: 7 passed when run separately. A combined invocation had an order-dependent failure in the pending-order eligibility test, which passes with the route file by itself.
- Frontend focused tests: 38 passed, including a chart-overlay test that marks pips from the latest price while the displayed close is earlier.
- Frontend production build passed. Browser visual verification was not run.
