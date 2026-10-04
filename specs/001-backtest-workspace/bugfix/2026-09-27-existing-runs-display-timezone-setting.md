# Bug Fix: Existing replay runs ignore Display Timezone changes

**Date:** 2026-09-27

## Bug

Changing Display Timezone in Settings did not change chart, crosshair, replay-control, or coverage timestamp labels for runs that had already been created.

## Root Cause

The replay page and chart workspace formatted timestamps using `run.display_timezone`, which is a snapshot saved when the run was created. The app separately refreshes the current user profile after saving Settings, but the replay page did not read that live profile value.

## Fix

Read the current authenticated user's `display_timezone` (falling back to their account timezone and then the run's saved timezone) on the replay page, and pass it to chart panels. Keep the run's saved timezone for the date-range semantics used when the run was created; only timestamp presentation follows the current setting.

## Verification

- Frontend TypeScript check (`tsc --noEmit`) passed.
- Targeted ESLint for the affected replay page and workspace components passed.
- Browser/UI validation and frontend tests were not run, per the user's instruction not to test the UI for now.
