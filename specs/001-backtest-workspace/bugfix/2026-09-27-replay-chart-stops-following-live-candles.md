# Bug Fix: Replay chart stops following live candles

**Date:** 2026-09-27

## Bug

While a chart pane was snapped to the latest replay candle, the viewport did not advance as replay revealed new candles. Expected behavior is for an attached pane to keep the latest revealed candle at its real-time edge.

## Root Cause

The chart library reports visible-range changes without identifying their source. Appending replay candles and changing the chart layout can emit the same notification as a user pan. The synchronization hook treated those programmatic updates as navigation, marked the pane detached, and then skipped subsequent replay scrolling because follow mode was off.

## Fix

Track pointer, wheel, keyboard, and double-click input. Only treat a range change as user navigation while one of those gestures is active; handle synchronized ranges explicitly. When a replay cursor update completes, refresh each pane against its latest replay-bounded candle and scroll panes that remain in follow mode to the live edge. Keep scrolling coalesced and non-animated, and retain the latest-candle timestamp guard for in-place higher-timeframe updates.

## Verification

- TypeScript check (`tsc --noEmit`): passed.
- ESLint on the changed frontend files: passed.
- Follow-state unit tests: 8 passed.
- `git diff --check`: passed (Git reported existing LF-to-CRLF conversion warnings).
- Browser replay was exercised in the user's existing browser tab. On the old `localhost:5173` build, Step Forward detached the chart and exposed the snap-to-live control. The tab was then pointed to `localhost:5174`, serving the current workspace source: four manual Step Forward commands advanced 07:41 to 07:45 without exposing the snap-to-live control; automatic Play also advanced candles while follow remained active. The replay was paused and returned to 07:41.
- Scope limitation: `localhost:5173` still serves an older WSL build, so the fixed workspace source was verified on `localhost:5174` in that same tab. The older server was left untouched.
