# Bug Fix: Backtest entry price drafts reset while typing

**Date:** 2026-10-01

## Bug

Editing the limit entry, stop-loss, or take-profit price could interrupt normal multi-keystroke input. Each valid numeric edit updated the parent price, after which the panel replaced the in-progress text with a formatted value. The authenticated replay page could not be driven in this session, so this records the source-confirmed input bug rather than attributing an unobserved server error to it.

## Root Cause

`BacktestEntryPanel` cleared each local input draft whenever its corresponding price prop changed. The component also emitted every valid keystroke to the parent, so its own state update triggered that clearing effect.

## Fix

Track the last numeric value emitted by each price input. Preserve that input's draft when the parent echoes the emitted value, and continue clearing drafts when a chart or other external change supplies a different price. Added a regression check for both cases.

## Verification

- Focused frontend entry panel and chart preview tests: 16 passed.
- Frontend production build: passed.
- Backend simulation schema, engine, and exact limit-touch route tests: 26 passed.
- Live UI interaction was not run: opening the browser panel was queued, but the browser automation runtime failed to initialize (`failed to write kernel assets`), so the authenticated run and visible server error could not be inspected.
