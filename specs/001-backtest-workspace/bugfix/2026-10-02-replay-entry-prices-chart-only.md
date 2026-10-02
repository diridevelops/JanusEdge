# Bug Fix: Use Chart Lines for Replay Price Levels

**Date:** 2026-10-02

## Bug

The replay entry panel exposed text boxes for entry, stop-loss, and take-profit values even though those levels should be set by dragging chart lines.

## Root Cause

`BacktestEntryPanel` rendered editable price fields and maintained local text drafts, in addition to the existing chart-line callbacks.

## Fix

Removed the three price fields and their draft parsing/state from `BacktestEntryPanel`. Added a short chart-drag instruction. Kept the price values in sizing calculations and retained the replay page's chart-line callbacks, so chart-based edits continue to drive the preview. Updated the existing panel checks for the new controls.

## Verification

- Inspected the live replay accessibility tree: the price fields are absent; chart-line guidance, market/limit and long/short choices, position sizing, and Place order remain.
- Viewed the live replay screenshot at `%TEMP%/janusedge-replay-chart-only-price-controls.png` to confirm the controls are removed from the sidebar.
- `git diff --check` completed without whitespace errors. Automated tests and the production build were not run.
