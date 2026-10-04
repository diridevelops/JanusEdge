# Bug Fix: Allow Profit-Locking Stops on Filled Positions

**Date:** 2026-10-02

## Bug

Open backtest positions could not move a stop-loss beyond entry through the chart drag control or Stop field, even when the latest revealed close left the stop on the safe side. Keyboard adjustments also lacked the current-close clamp.

## Root Cause

The chart drag handler bounded stops against entry, and the Stop field validated against entry. The backend already accepts favorable stop prices when they remain strictly beyond the normalized current close and makes edited protection eligible from the next source candle.

## Fix

Chart drag and keyboard stop adjustments now clamp to one instrument tick on the safe side of the current close, allowing stops to cross entry. If close data is unavailable, they retain the entry-side boundary. The Stop field now uses the frozen-precision current close supplied by the replay page, with entry-side validation as its fallback. Take-profit, break-even, close, and new-entry bracket rules are unchanged. No backend API or schema changed.

## Verification

- Frontend focused tests: 20 passed, including long and short chart-drag, keyboard, and Stop-field edits; current-close guards; missing-close fallback; and existing break-even, take-profit, and close controls.
- Frontend production build: passed. Existing warnings remain for outdated Browserslist data, Tailwind's experimental CommonJS-to-ESM loading, and a bundle chunk over 500 kB.
- Backend replay-route tests: 7 passed. They cover favorable long and short stop edits, rejection at the current close without changing protection, stop-moved tagging, next-candle eligibility, and adverse gap fill behavior.
- Backend simulation-engine tests: 19 passed, including protective-stop eligibility and gap-fill rules.
- `git diff --check`: passed.
- The in-app replay page was inspected and had no open positions, so a manual filled-position edit was not exercised there; creating one would have changed the persisted simulation run. The chart interaction was exercised by the frontend test.
