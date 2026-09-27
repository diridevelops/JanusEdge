# Bug Fix: Preserve trade records when media deletion fails

**Date:** 2026-09-27

## Bug

When MinIO could not remove a trade media object, trade deletion logged and swallowed the error, then removed the media reference and trade record anyway. A Backtest run purge could therefore finish with an orphaned MinIO object.

## Root Cause

`TradeService._delete_trade_media` treated object-store failures as best-effort and continued deleting MongoDB references. The run cleanup worker could not detect the incomplete physical purge or retry it.

## Fix

Propagate MinIO client, bucket, and object-removal errors. Keep media references and the trade record until all owned media objects are removed, then confirm the references are gone. The run deletion worker leaves the run pending and releases its cleanup lease when cleanup fails, allowing another worker to retry.

## Verification

- Focused Backtest run deletion tests: 5 passed, including injected MinIO failure and recovery by a replacement worker.
- Complete backend pytest suite: 360 passed (the final focused rerun additionally covered the subsequent late-write and API-fence assertions).
- Complete frontend Vitest suite: 56 passed.
- ESLint: 0 errors; 3 existing React-hook warnings in AnalyticsPage, SettingsPage, and WhatIfPage.
- Production build: passed with workspace filesystem permission; Vite reported existing stale Browserslist data and bundle-size warnings.
- Browser UI validation was not run.
