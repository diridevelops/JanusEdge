# Bug Fix: Candle Cache Lease Outlived Its Worker

**Date:** 2026-10-03

## Bug

After a worker stopped during a cache fetch, the next worker could wait much longer than the preparation job's lease before retrying that UTC day.

## Root Cause

The cache used a fixed 900-second lease while backtest jobs could be reclaimed after a shorter worker lease. An abandoned cache claim therefore continued blocking a replacement worker after its job was already available.

## Fix

Initialize the worker lease first and pass that duration to its candle cache, so both abandoned claims become reclaimable on the same schedule.

## Verification

- `pytest tests/test_backtests/test_random_period_selection.py -q`: 19 tests passed, including restart recovery after a probe interruption.
