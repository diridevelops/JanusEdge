# Bug Fix: Narrow the Collapsed Replay Rail

**Date:** 2026-10-02

## Bug

The collapsed trading sidebar rail was 42px wide and took more chart width than the user wanted.

## Root Cause

The collapsed grid track and sidebar width were both set to 42px.

## Fix

Reduced the collapsed rail track and sidebar width to 28px. The full-height toggle and 16px chevron remain centered in the rail. Updated the stylesheet regression expectation to 28px.

## Verification

- In the live replay at 1159×668, maximized mode showed a 28px-wide rail at the far right, with a 620px height matching the chart workspace row. The chart area grew from 1105px to 1119px.
- Captured `%TEMP%/janusedge-replay-sidebar-collapsed-28px.png`.
- Automated frontend tests and the production build were not run.
