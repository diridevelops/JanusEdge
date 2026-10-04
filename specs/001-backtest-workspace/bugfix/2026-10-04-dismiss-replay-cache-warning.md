# Bug Fix: Dismiss Replay Cache Warning

**Date:** 2026-10-04

## Bug

The warning shown after replay candles are restored had no way to dismiss it.

## Root Cause

The replay page rendered the cache-refresh notice as static status text without an interactive control or dismissal state.

## Fix

Added an accessible close button. Dismissal is scoped to the run and cache-refresh timestamp, so a subsequent restoration can show a new notice.

## Verification

- `git diff --check` — passed.
- Automated tests and browser UI checks — not run.
