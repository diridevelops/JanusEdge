# Bug Fix: Keep pending-order labels on their price lines

**Date:** 2026-10-03

## Bug

With multiple working orders on a replay chart, later order labels and cancel buttons appeared below their corresponding price lines. The supplied screenshot shows the lower pending sell limit's label and cancel button displaced from its line.

## Root Cause

`BacktestWorkingOrderOverlay` added `(index % 3) * 14` pixels to each label's vertical position to stagger labels. The order line remained at the price coordinate, so the label and cancel control could appear detached from their order.

## Fix

Removed the index-based vertical offset. Each working order's text and cancel button now share a clamped position centered on that order's price line.

## Verification

- `git diff --check` passed for the changed overlay and this report.
- Frontend tests and a live browser check were not run.
