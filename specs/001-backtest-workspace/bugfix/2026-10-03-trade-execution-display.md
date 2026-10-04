# Bug Fix: Preserve execution price precision and side colors

**Date:** 2026-10-03

## Bug

The trade details execution table rendered execution prices as USD currency with two decimals, losing configured Forex and CFD price precision. Backtest executions with lowercase `buy`/`sell` values were both styled as sells because the buy check was case-sensitive.

## Root Cause

`ExecutionList` used `formatCurrency(exec.price)` regardless of instrument metadata and only compared `exec.side` to the exact string `Buy`. Backtest execution side values can be lowercase, while the trade already exposes its frozen `price_precision`.

## Fix

Pass the trade's `price_precision` into `ExecutionList` and format execution prices to that precision. Normalize side casing before choosing badge colors so buys are green and sells are red; unknown values use a neutral style. Accept lowercase buy/sell values in the execution type.

## Verification

- Browser check of the affected EUR-USD trade showed execution prices `1.14727` and `1.14758`; the buy badge rendered green and the sell badge red.
- Automated tests and type checking were not run.
