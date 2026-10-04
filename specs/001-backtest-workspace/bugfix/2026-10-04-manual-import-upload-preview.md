# Bug Fix: Manual import preview rejects selected CSVs

**Date:** 2026-10-04

## Bug

Selecting a HistData CSV showed its filename, but run creation reported that no CSV or cached import was available. The uploaded file’s candle date coverage was also not shown.

## Root Cause

The preview result is required before uploaded dates can be used. The preview request could fail, but submitting the form cleared that preview error and replaced it with the generic “select files” validation message. The upload requests also relied on the API client’s default JSON content type even though the Flask endpoints expect multipart form fields and files.

## Fix

Set multipart content type on manual preview, run creation, and replay cache-recovery uploads. Keep preview failures visible beside the file input and preserve the specific error when submission is attempted. Prevent a failed new upload from silently using an older cached dataset. After a successful preview, show the uploaded files’ date range separately from the merged cached coverage.

## Verification

- `npm run build` from `frontend`: passed, including TypeScript checking and Vite production build.
- `git diff --check`: passed; only existing line-ending conversion warnings were emitted.
- UI upload against the user’s selected local CSV was not rerun in this session, so the actual file’s parse result remains unverified.
