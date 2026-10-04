# Bug Fix: Recover Backtest Cache After MinIO Volume Reset

**Date:** 2026-10-04

## Bug

After the MinIO volume was removed and recreated, reopening a backtest could fail with HTTP 500 instead of offering cache recovery. A newly prepared run could also reference candle dates whose objects had disappeared with the volume.

## Root Cause

Cache reads translated `NoSuchKey` and `NotFound` into a recoverable missing-candle result, but a missing bucket returned `NoSuchBucket` and escaped as an internal error. Separately, a ready cache hit could return a process-local LRU frame without checking whether its MinIO object still existed, allowing preparation to publish a run manifest with a dangling cache reference.

## Fix

Treat `NoSuchBucket` as missing cache data, and verify object existence in MinIO before reusing a ready cache entry. If a cache write encounters a missing bucket, recreate it and retry; concurrent bucket creation is handled as success.

## Verification

- `python -m pytest -q tests/test_backtests` from `backend`: 146 passed, 8 existing `mongomock` deprecation warnings.
- After final test cleanup, `python -m pytest -q tests/test_backtests/test_backtest_candle_cache.py`: 5 passed.
- `git diff --check`: passed; Git reported only its line-ending conversion warnings.
- Browser/UI verification was not run; the cache-status and recovery behavior was exercised through backend tests.
