# Bug Fix: Keep Replay Trading in a Right-Side Rail

**Date:** 2026-10-02

## Bug

At narrower viewport sizes, the replay trading controls could move below the charts. The account summary, entry panel, orders and positions, and reset action also did not consistently fill one sidebar width. When collapsed, the trading sidebar appeared as a small button instead of a full-height rail next to the charts.

## Root Cause

The replay layout used a single grid column by default and only switched to a chart-plus-sidebar arrangement at a wide desktop breakpoint. Maximized replay also had a stacked layout below 1024px. The entry panel kept a fixed width, while the containing sidebar and its other sections used different widths. A desktop `max-height` cap could also keep the sidebar rail shorter than the chart column.

## Fix

Updated `frontend/src/styles/backtest-candlekit.css` so normal and maximized replay always use a chart column followed by a right-side trading column. The expanded sidebar scales from 240px to 350px; its account summary, entry panel, orders and positions, and reset action fill that column. The collapsed layout reserves a 42px right-side rail that stretches to the chart row height, with a centered left chevron. Removed the sidebar height cap so expanded and collapsed states align with the chart column.

Updated `frontend/src/styles/backtest-candlekit.test.ts` to reflect the two-column layout, full-height collapsed rail, and full-width sidebar controls.

## Verification

- Inspected the live local replay at 1159×668: chart column and trading sidebar remained side-by-side; account summary, entry panel, and reset control each measured 348px wide.
- At 800×600 in regular replay, the 245px chart column remained to the left of the 240px trading sidebar. In maximized replay, the chart remained visible beside the sidebar.
- At 1450×900, collapsing the sidebar produced a 42px rail with the same 737px height as the chart column. At 1159×668 maximized, the 42px rail also matched the chart row height.
- Captured the expanded layout at `%TEMP%/janusedge-replay-sidebar-right-rail.png` and the collapsed rail at `%TEMP%/janusedge-replay-sidebar-collapsed.png`.
- Automated frontend tests and the production build were not run; this change was checked in the live browser and the user did not request a test run.
