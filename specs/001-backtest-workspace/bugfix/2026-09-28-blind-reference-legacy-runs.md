# Bug Fix: Recover missing references for ready Blind runs

**Date:** 2026-09-28

## Bug

Opening a ready Blind run without `normalized_reference_price` stopped at “Replay unavailable.” The report indicated this affected existing Blind runs.

## Root Cause

The replay page correctly fails closed when its run response has no valid reference. Ready runs created before the reference metadata was added can have an immutable candle snapshot but no root-level reference field. The current preparation worker stores that field for newly prepared Blind runs; the ready legacy record has no automatic backfill.

## Fix

When an owned, ready Blind run is opened and its reference is missing, the service reads the immutable snapshot, selects the first replay-period candle at or after the saved start boundary, and stores that candle's open using an atomic missing-value update. It uses the existing fail-closed behavior if the snapshot contains no replay candle or its reference is zero/non-finite. Concurrent requests reuse the value another request persisted.

## Verification

- `backend/.venv/Scripts/python.exe -m pytest tests/test_backtests/test_blind_mode.py -q` — 8 passed, including legacy snapshot reference recovery and persistence.
- `git diff --check` — passed.
- Live browser verification was not run after this fix.
