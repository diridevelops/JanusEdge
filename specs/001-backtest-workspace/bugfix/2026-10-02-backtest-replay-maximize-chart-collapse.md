# Bug Fix: Backtest Replay Charts Collapse When Maximized

**Date:** 2026-10-02

## Bug

On a desktop replay page, maximizing the replay hid the charts while leaving the sidebar and playback controls visible. The chart workspace had zero height.

## Root Cause

At desktop widths, the base simulation grid uses `align-items: start`. The maximized grid expanded to the viewport height but inherited that alignment, so its chart column stayed at its intrinsic height and the flex chart workspace collapsed to zero.

## Fix

Set `align-items: stretch` on the maximized simulation grid so its chart column and sidebar fill the available grid row. Added a stylesheet regression test for this layout contract.

## Verification

- `npm test -- src/styles/backtest-candlekit.test.ts` passed (1 test).
- In the in-app browser, restored and maximized the replay. In maximized mode both chart panels and their chart canvases had nonzero dimensions; restored mode also retained a nonzero chart workspace.
- `npm run build` passed. Vite reported existing stale Browserslist data, an experimental Tailwind module warning, and a large-chunk warning.
- `git diff --check` passed.
- No separate cross-browser automation was run; browser verification used the already-open in-app replay.
