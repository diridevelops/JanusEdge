# Bug Fix: Compact Position Risk Marker

**Date:** 2026-10-02

## Bug

The chart's position risk marker was wide and sat below the entry line, where it could cover the take-profit line and label.

## Root Cause

The marker displayed the full “Initial risk” label and stop-moved text, used generous vertical padding, and was positioned below every entry regardless of trade side.

## Fix

Shortened the visible label to “Risk” and “moved,” reduced vertical padding and line height, and placed the marker on the side of entry opposite the take-profit: above entry for shorts and below for longs. The full risk description remains available as a tooltip; BE and close controls retain their labels and actions.

## Verification

- Backtest position overlay tests: 10 passed, including compact layout and side-aware placement.
- Frontend production build: passed. Existing Browserslist, Tailwind module-loading, and bundle-size warnings remain.
- In-app replay page: visually confirmed the shorter marker sits above the short entry and leaves the take-profit line and label unobstructed.
- `git diff --check`: passed.
