# Bug Fix: Buy Execution Markers Use Sell Styling

**Date:** 2026-10-03

## Bug

The trade-detail chart rendered lowercase `buy` executions with a red downward arrow and red label. Buy executions should use green upward markers.

## Root Cause

`CandlestickChart` compared execution sides only with title-case `Buy`. The API also returns lowercase `buy` and `sell`, so lowercase buys fell through to the sell styling.

## Fix

Normalize the side when choosing marker color, arrow direction, position, and label in `frontend/src/utils/executionMarkerStyle.ts`, and use that style in `CandlestickChart`.

## Verification

- `npm test -- src/utils/tradeChartData.test.ts src/utils/executionMarkerStyle.test.ts`: 6 tests passed.
- `npx tsc --noEmit`: passed.
- Manual browser visual verification was not run.
