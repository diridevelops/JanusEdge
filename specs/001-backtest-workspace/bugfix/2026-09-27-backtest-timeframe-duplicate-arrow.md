# Bug Fix: Duplicate timeframe dropdown arrows

**Date:** 2026-09-27

## Bug

The chart timeframe dropdown displayed two downward arrows instead of one in the replay workspace. The expected behavior is one clear dropdown indicator.

## Root Cause

The control was a native `<select>` with its browser-provided arrow, and the component also rendered a separate `ChevronDown` icon over it. The runtime showed both indicators.

## Fix

Removed the overlaid icon and restored the native select appearance so the browser draws a single indicator. The compact dimensions and chart-specific colors remain applied in `frontend/src/styles/backtest-candlekit.css`.

## Verification

- `npx tsc --noEmit` completed successfully.
- `git diff --check` completed successfully.
- Inspected the open replay tab's accessibility tree: the timeframe controls are present, and each of the three chart tab strips has an adjacent Add chart button.
- The screenshot's arrow glyph count was not independently checked after the change; no chart layout was changed during inspection.
- Automated tests were not run.
