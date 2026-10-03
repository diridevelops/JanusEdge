# Bug Fix: Canonicalize Instrument Aliases in Settings

**Date:** 2026-10-03

## Bug

Saving the instrument sizing table failed with “Duplicate instrument mapping: AUD/USD.” The same Forex pair could be loaded from the unified catalog and legacy Forex section under dash and slash spellings. Built-in legacy Forex defaults were also being added during initial table population.

## Root Cause

The Settings page combined catalog defaults, saved instrument mappings, and legacy Forex mappings using their raw keys. It rendered `AUD-USD` and `AUD/USD` as separate rows, then the save builder normalized both to `AUD-USD` and rejected them as duplicates. Its legacy fallback also seeded built-in Forex defaults already present in the unified catalog.

## Fix

Canonicalized instrument keys to uppercase dash form before merging those sources into table rows. Removed unchanged built-in legacy Forex defaults from initial table seeding while keeping customized saved legacy values for migration. Saved unified tick size remains authoritative over a tick size migrated from a legacy override. The duplicate guard remains for genuinely separate duplicate rows.

## Verification

Static source review confirmed source keys are canonicalized before row generation and the save-time duplicate guard remains. `git diff --check` passed. Automated tests, build, and browser save interaction were not run for this focused fix.
