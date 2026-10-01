# Bug Fix: Round market entry close to instrument precision

**Date:** 2026-10-02

## Bug

The replay sidebar displayed a market entry at instrument precision, but sizing could reject that same entry with “Entry, stop, and target must be finite and use the instrument price precision.” The order button was then disabled even though the displayed bracket used valid prices.

## Root Cause

Entry sizing received the raw displayed candle close, while the input formatted it to the instrument precision. Source candle values can carry more decimal places than the instrument accepts, so the visible value and the value validated for sizing could differ.

## Fix

Round the current close to the instrument precision when deriving the entry price used by default bracket sizing and the entry panel. The chart’s market data and position prices remain unchanged.

## Verification

- In the replay browser, the previous precision validation message disappeared after the change. Entry `1.25120`, stop `1.25019`, and target `1.25221` produced a valid 1.001-lot preview and enabled **Place order**.
- The armed market preview submitted on the second click as a simulated pending order, which was canceled after verification.
- `BacktestEntryPanel.test.tsx`: 11 tests passed; `npm run build`: passed.
- Full frontend suite: 115 tests passed across 18 files.
