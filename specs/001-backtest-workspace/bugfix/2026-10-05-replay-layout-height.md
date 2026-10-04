# Bug Fix: Replay layout leaves unused height

**Date:** 2026-10-05

## Bug

In maximized replay, the chart and trading panel did not use the remaining viewport height. Collapsing the trading sidebar could also collapse the chart area, leaving only the replay controls visible.

## Root Cause

The maximized replay grid relied on implicit row sizing. When the sidebar content was hidden, the grid had no explicit flexible row to preserve the chart workspace's height. The entry-order panel also retained its fixed flex basis instead of sharing the available sidebar height.

## Fix

The maximized replay grid now defines a flexible `minmax(0, 1fr)` row. Its entry-order panel grows into available sidebar space while retaining a 240px minimum usable height. The grid row keeps the chart visible when the sidebar is collapsed.

## Verification

- `git diff --check` passed.
- Browser viewport and collapsed-sidebar behavior were not exercised after the CSS change.
