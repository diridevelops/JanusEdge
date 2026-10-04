# Bug Fix: Entry bracket appears only after arming

**Date:** 2026-10-02

## Bug

On the backtest replay page, a temporary entry bracket appeared on the chart before the user requested one. Clicking **Place order** submitted immediately, so there was no review step. The expected flow is to reveal the bracket on the first click, change the action to **Submit order**, and submit only on the second click.

## Root Cause

`BacktestReplayPage` marked its preview visible whenever the current close and bracket prices existed. `BacktestEntryPanel` sent its only primary action directly to the submit callback and always labeled it **Place order**.

## Fix

Added explicit preview-armed state. The first action arms the chart bracket; the panel then shows **Submit order** and **Cancel preview**. The submit callback runs only in that armed state. Canceling or a successful submit clears the preview.

## Verification

- `BacktestEntryPanel.test.tsx`: 11 tests passed, including the two action states.
- `npm run build`: passed TypeScript and Vite production build.
- Browser on the replay route: before the first click there was no temporary entry bracket; the first click displayed the bracket and **Submit order**, with no working order. The second click created one simulated pending market order; canceling it returned the run to no pending orders.
- Browser checks also armed and canceled short-market, limit-short with edited entry, and limit-long with manual 0.25-lot sizing and edited stop/target prices. The page was restored to market-long, auto-size mode.
- Full frontend suite: 115 tests passed across 18 files.
