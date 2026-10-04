# Bug Fix: Transient incomplete-snapshot warning on run open

**Date:** 2026-09-27

## Bug

Opening a replay run briefly displayed `The replay source did not load the complete immutable snapshot.` before the run eventually appeared.

## Root Cause

React Strict Mode replayed the replay-loading effect while both setups shared one CandleKit controller. The second setup could start a duplicate load while day fetches from the first were still in flight. CandleKit's in-flight fetch coalescing can return before those requests populate the cache, allowing the snapshot completeness check to run against an incomplete cache and show a false error.

## Fix

The hook now shares the in-flight load for the same run and attempt, scopes cancellation to each effect setup, and defers unloading until a replayed setup has had a chance to reuse the load.

## Verification

- TypeScript check passed.
- ESLint for `useBacktestReplay.ts` passed with no warnings.
- `git diff --check` passed.
- The test suite, production build, and browser UI were not rerun for this fix; UI testing remains deferred under the user's instruction.
