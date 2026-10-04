# Bug Fix: Blind manual replay chart price format

**Date:** 2026-10-05

## Bug

Opening a replay created from manual HistData candles with Blind mode enabled caused the chart to repeatedly throw `Uncaught Error: unexpected base` from Lightweight Charts. The browser log showed the error while the replay chart initialized and while its series options were updated.

## Root Cause

Blind mode scales the instrument's executable tick size by `100 / referencePrice`. The result can be a non-decimal increment whose reciprocal contains prime factors other than 2 and 5. The frontend passed that transformed execution tick as Lightweight Charts' `priceFormat.minMove`; its price-scale tick calculator cannot represent that base and throws. The exact transformed tick is still needed for simulated order input and rounding, so it must remain separate from chart label formatting.

## Fix

The replay chart now sets its formatter `minMove` to `10 ** -displayPrecision`, a decimal-compatible display increment. The existing exact Blind tick calculation remains in the order and simulation price paths.

## Verification

- `npm run build` in `frontend/` passed: TypeScript checking and Vite production build completed.
- `git diff --check` passed.
- Browser reproduction and automated tests were not run.
