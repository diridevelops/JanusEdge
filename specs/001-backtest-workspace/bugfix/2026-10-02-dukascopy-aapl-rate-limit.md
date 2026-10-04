# Bug Fix: Handle Dukascopy Rate Limits During Run Preparation

**Date:** 2026-10-02

## Bug

Preparing an AAPL.US-USD run for 2026-09-21 through 2026-09-23 failed with the generic market-data preparation error. EUR/USD preparation succeeded in comparison.

## Root Cause

The Dukascopy combined BID/ASK download received HTTP 429 for the AAPL.US-USD ASK endpoint on 2026-09-21. The response did not include `Retry-After`. The pinned downloader's built-in retry delays were only 1 and 2 seconds, after which the worker terminally failed and cleaned up the run. Direct checks returned HTTP 200 for AAPL BID and EUR/USD ASK. A controlled retry through the updated adapter still received HTTP 429 after 30- and 60-second cooldowns, so the upstream refusal remains unresolved.

## Fix

Serialize this process's requests to Dukascopy at one request per second. Honor `Retry-After` when present, lengthen built-in 429 retry delays, and add bounded 30- and 60-second recovery attempts. Log provider failures with a traceback and the affected run/instrument so the upstream status is visible in backend logs. No fallback or synthetic ASK data is used.

## Verification

- Reproduced the AAPL.US-USD ASK HTTP 429 through the provider adapter; the final error retained the endpoint and HTTP status after the bounded retries.
- Confirmed earlier direct comparisons returned HTTP 200 for AAPL BID and EUR/USD ASK.
- Python source compilation and `git diff --check` passed.
- Automated test suites were not run. A successful AAPL preparation remains unverified because Dukascopy continued returning HTTP 429.
