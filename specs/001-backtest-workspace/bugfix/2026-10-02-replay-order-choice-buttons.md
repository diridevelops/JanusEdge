# Bug Fix: Clarify replay order entry choices

**Date:** 2026-10-02

## Bug

The replay entry panel split order type and direction into separate segmented controls and included a panel-collapse button, an extra Simulation label, and chart-line guidance text. The user requested direct Buy/Sell Market/Limit choices and a shorter title row.

## Root Cause

`BacktestEntryPanel` represented type and direction as independent controls and rendered its own collapsible header and helper sentence. This made the requested order combinations less explicit and added controls and text that were not needed in the compact replay panel.

## Fix

Replaced the segmented selectors with four accessible combined choices. Each choice sets order type and direction together and uses green styling for Buy and red styling for Sell. Removed the panel-level collapse control, Simulation label, and chart-line guidance sentence; shortened the header to show only “Entry order”. The page resets any armed preview when the selection changes.

## Verification

- In the replay browser, clicked each of the four choices and confirmed that the matching button became active and pressed; restored Buy Market and did not submit an order.
- Confirmed the header shows only “Entry order”, all four choices are present, and the guidance sentence is absent.
- `npm test -- src/components/backtest/BacktestEntryPanel.test.tsx`: 9 tests passed.
- `git diff --check`: passed.
- Full frontend build was not run.
