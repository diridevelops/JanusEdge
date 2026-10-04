# Bug Fix: Replay step follows selected speed

**Date:** 2026-10-02

## Bug

A single forward or backward replay step advanced only one source candle regardless of the selected speed. The speed menu also offered only 1×, 5×, and 20× instead of the requested 1×, 2×, 5×, 15×, and 30×.

## Root Cause

The replay controls passed speed to playback timing, but both adapter step handlers moved by one source index. In the simulation-driven path, a step therefore requested only the adjacent one-minute candle.

## Fix

Set the available rates to 1×, 2×, 5×, 15×, and 30×. A manual step now advances the selected number of one-minute source candles in either direction, clamped to replay bounds. The simulation advance operation processes every candle between the current and target indices, preserving intermediate fills and protection checks.

## Verification

- `git diff --check` passed; Git reported only existing LF-to-CRLF notices.
- Frontend tests and live UI playback checks were not run.
