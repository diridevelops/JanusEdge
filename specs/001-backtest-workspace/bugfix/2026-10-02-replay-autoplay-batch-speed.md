# Bug Fix: Replay autoplay batches by selected speed

**Date:** 2026-10-02

## Bug

At 5×, autoplay advanced one one-minute source candle every 200 ms. On a five-minute chart, the current bar therefore appeared in five updates instead of arriving as a complete five-minute bar about once per second. Each update also required a separate simulation advance request.

## Root Cause

The simulation-driven replay timer always targeted `currentIndex + 1` and scaled the timer delay by the selected multiplier. The replay chart rebuilds its aggregate after each completed source-candle advance, exposing each partial five-minute aggregate.

## Fix

Autoplay now advances the selected number of one-minute source candles in a single simulation request and targets a one-second start-to-start cadence, accounting for request time. The simulation advance handler processes every intervening candle in order, preserving fills and protection checks.

## Verification

- `git diff --check` passed; Git reported only an LF-to-CRLF notice.
- Automated tests and a live browser playback check were not run.
