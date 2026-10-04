# Bug Fix: Maximized replay uses the available viewport

**Date:** 2026-10-05

## Bug

In maximized replay, a large part of the viewport below the chart and replay controls was unused. Collapsing the trading sidebar removed the chart workspace entirely.

## Root Cause

The replay page was wrapped in a normal block `.space-y-3` container with automatic height. The maximized replay child used `h-full`, but its parent had no definite height, so the percentage height could not fill the main viewport. When the sidebar was collapsed, the chart workspace had `min-height: 0` and no intrinsic height, so the auto-sized grid shrank to the replay controls' height.

## Fix

In maximized mode, the replay page wrapper is now a full-height flex column. The replay view grows as a flexible child, and its simulation grid receives an explicit flexible row. The entry-order panel grows to use available sidebar height while keeping a 240px minimum.

## Verification

- Inspected the running replay page in the in-app browser before and after the change.
- Before the fix, collapsed mode measured a 96px replay and a 0px chart workspace. After the fix, the replay occupied the full 836px viewport area; the chart workspace measured 740px and replay controls 86px.
- Collapsed the trading sidebar and confirmed the chart workspace remained 740px high; expanded it again and confirmed the chart and entry-order panel filled the available space.
- `git diff --check` passed.
- Automated frontend tests and build were not run.
