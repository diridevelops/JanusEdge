# Bug Fix: Workspace tab flicker and interrupted drag

**Date:** 2026-09-27

## Bug

Selecting or dragging a chart tab caused the workspace to flash and interrupted the drag, preventing the tab from being attached to another section. The browser console also reported `SyncEngine: group "g1" not found` during tab interaction.

## Root Cause

Two lifecycle faults contributed to this workspace bug:

- `BacktestChartWorkspace` passed a new inline `onReady` callback on every render. CandleKit treats that callback as an adapter lifecycle dependency, so rerenders could re-register the workspace driver and rehydrate the layout while a tab interaction was in progress.
- `useBacktestChartSync` created its group during render. React Strict Mode replayed the effect cleanup, deleting the group, but the memoized render value did not recreate it for the next setup. Sync operations then referenced a missing group.

## Fix

Stabilized the workspace-ready callback with `useCallback`. Assigned the sync group a stable ID and moved group creation and deletion into the same effect setup/cleanup lifecycle.

## Verification

- Frontend headless tests: 42 passed across 7 files.
- TypeScript check and production build passed.
- Lint completed with no errors; three warnings were in unrelated pages.
- Browser UI interaction testing was not run, per the user's instruction.
