# Bug Fix: Random Backtest Selection Calendar Import

**Date:** 2026-10-03

## Bug

Creating a random-period backtest raised `NameError: name 'calendar' is not defined` while calculating the latest valid start date, so random selection could not proceed to its cached candle probes.

## Root Cause

`_add_calendar_months` calls `calendar.monthrange` but the service module did not import Python's `calendar` module.

## Fix

Import `calendar` in `backend/app/backtests/service.py`.

## Verification

- `pytest tests/test_backtests/test_random_period_selection.py -q`: 19 tests passed.
- `pytest tests/test_backtests -q -k "not pending_order_remains_working_and_obeys_eligibility_after_rewind"`: 140 passed, 1 unrelated existing test deselected.
