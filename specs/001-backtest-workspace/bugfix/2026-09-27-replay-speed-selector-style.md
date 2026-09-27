# Bug Fix: Replay speed selector styling

**Date:** 2026-09-27

## Bug

The playback speed selector rendered with incorrect sizing and no clear dropdown indicator in the replay controls.

## Root Cause

The selector inherited global form-control styling, including 16px text and large padding, while CandleKit only set its height, text color, transparent background, and border. The inherited `appearance: none` removed the native arrow, leaving the selector visually unclear.

## Fix

Added explicit compact dimensions, typography, padding, theme colors, and a single CSS-drawn caret for the replay speed selector in `frontend/src/styles/backtest-candlekit.css`.

## Verification

- Inspected the open replay page after the change: the selector shows the current `1×` speed and a single dropdown caret.
- Confirmed the accessibility tree exposes the `1×`, `5×`, and `20×` options.
- Did not run the frontend or backend test suites for this UI change.
