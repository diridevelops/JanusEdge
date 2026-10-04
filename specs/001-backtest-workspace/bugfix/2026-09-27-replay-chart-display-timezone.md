# Bug Fix: Replay chart timestamps use UTC labels

**Date:** 2026-09-27

## Bug

The Backtest replay controls and run summary use the run's configured display timezone, but the chart x-axis and crosshair time label show UTC values instead.

## Root Cause

Replay candles correctly retain UTC epoch timestamps. The chart did not provide a timezone-aware Lightweight Charts `timeScale.tickMarkFormatter` or `localization.timeFormatter`, so CandleKit used its default UTC-based labels.

## Fix

Pass the run's saved display timezone to every chart panel and format x-axis ticks and crosshair timestamps with `Intl.DateTimeFormat` for that IANA timezone. Keep the candle timestamps, UTC interval aggregation, replay cursor, and synchronization values unchanged.

## Verification

- Frontend TypeScript check (`tsc --noEmit`) passed.
- Targeted ESLint for the chart formatter and affected replay components passed.
- Browser/UI validation and frontend tests were not run, per the user's instruction not to test the UI for now.
