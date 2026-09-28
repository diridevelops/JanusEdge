# Bug Fix: Hide dates in blind account labels

**Date:** 2026-09-28

## Bug

The Backtest Runs page could display a date-bearing account label for a blind run. The browser report showed `Backtest 0005.HK-HKD 2023-11-16 to 2023-12-15 (...)`; blind account labels should contain the instrument and a `blind` suffix without period dates.

## Root Cause

The run-list component rendered `run.account_label` verbatim. The API serializer also preferred the linked account's persisted label, so accounts created before blind-aware labels were introduced could continue exposing their old date-bearing label.

## Fix

The run API now derives a canonical date-free account label from the blind run's instrument and run ID, regardless of a stale linked account label. The run-list component also derives that safe label itself for blind runs and displays it even if the account label field is absent. Added regression coverage with a legacy date-bearing account label.

## Verification

- `backend/.venv/Scripts/python.exe -m pytest tests/test_backtests/test_blind_mode.py -q` — 7 passed.
- `npm test -- src/components/backtest/BacktestRunList.test.tsx` — 9 passed.
- `git diff --check` — passed.
- Live browser verification was not run after this fix; the run-list rendering regression is covered by the component test.
