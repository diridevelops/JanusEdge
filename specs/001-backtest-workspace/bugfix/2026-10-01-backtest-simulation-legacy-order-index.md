# Bug Fix: Replay entry controls remain blocked by a stale simulation index

**Date:** 2026-10-01

## Bug

On replay run `6abeae8a62756cbe232d7207`, the Run status was `ready` but the entry panel stayed in `Placing…` state, with order entry and other mutation controls disabled. The worker was running, yet the pending order operation did not complete.

## Root Cause

The worker logs showed `DuplicateKeyError` on the obsolete unique index `(run_id, generation, record_id, sequence)` in `backtest_simulation_orders`. Current versioned order documents no longer populate those fields, so MongoDB treated each as null and rejected the recovered order write as a duplicate. The same legacy index shape could also block writes to simulation positions. Since the operation is durable and retryable, the failure left `pending_operation_id` set; the replay page correctly disabled mutations while it was pending.

## Fix

Added a startup migration in `backend/app/db.py` that detects and drops only unique indexes with the exact obsolete key pattern from the simulation orders and positions collections. It preserves documents and then creates/retains the current versioned indexes. Added index migration coverage in `backend/tests/test_db_indexes.py`.

## Verification

- `pytest -q tests/test_db_indexes.py tests/test_backtests/test_simulation_service.py`: 8 passed.
- `npm run test -- src/components/backtest/BacktestEntryPanel.test.tsx src/components/backtest/BacktestBracketPreview.test.tsx`: 16 passed.
- `npm run build`: passed; emitted existing dependency-data, bundle-size, and Tailwind module-format warnings.
- `git diff --check`: passed.
- In the built-in browser on the affected replay, verified entry-type and direction toggles, entry/stop/target edits, auto-size/manual-lot controls, chart bracket handles, collapse/reopen, and cancel preview. Submitted and canceled one test market order and one test limit order. The previously stuck operation recovered after the index migration, the Place order control became enabled, and no browser errors were recorded.
- The focused index test uses `mongomock`; the full backend and frontend test suites were not run. The migration also ran during the local Docker-backed development session, after which the worker completed the pending operation.
