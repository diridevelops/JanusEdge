# Bug Fix: Maximized replay charts disappear at smaller viewports

**Date:** 2026-10-02

## Bug

At a 1159×668 viewport, maximizing replay left the chart workspace with no height while replay controls and the trading sidebar remained visible. The expected behavior is for charts to occupy the available maximized area at smaller widths.

## Root Cause

The maximized layout sizing rules only applied at widths of at least 1280px. Below that breakpoint, the layout used intrinsic single-column grid sizing. The chart workspace's `h-full flex-1` therefore resolved to zero height. Before the fix, live DOM measurements showed a 0px workspace and 72px chart panels at 1159px width.

## Fix

Added maximized sizing for widths from 1024px, using side-by-side charts and trading controls. Below 1024px, maximized replay now uses a stacked grid with a reserved chart row and a scrollable trading row. The collapsed trading sidebar keeps a 42px row on narrow screens.

## Verification

- Focused Vitest stylesheet tests passed: 3 tests.
- Frontend production build passed; Vite emitted Browserslist age and bundle-size warnings.
- In-app browser at 1159×668: both chart panels rendered at about 497px high in the maximized side-by-side layout.
- In-app browser at 800×668: the stacked layout rendered both chart panels at about 237px high; collapsing trading expanded them to about 443px.
- `git diff --check` was clean before the final log was written.
- No cross-browser checks or viewport widths below 800px were tested.
