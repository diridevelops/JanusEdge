# Bug Fix: Allow Plus Signs in Base Asset Labels

**Date:** 2026-10-03

## Bug

Saving instrument sizing settings with `DUK+` in the Base Asset / Unit field failed with “Base asset/unit for DUKPLUS-EUR must be a short label.” The backend label validator already accepted `+`.

## Root Cause

The Settings page used a narrower character allowlist than the backend. Its regular expression allowed letters, digits, periods, underscores, spaces, and hyphens, but excluded plus signs.

## Fix

Added `+` to the Settings page base-asset/unit character allowlist. Instrument-code validation is unchanged.

## Verification

Static source inspection confirmed both frontend and backend now allow `+` in base-asset/unit labels. Automated tests, build, and browser save interaction were not run for this focused fix.
