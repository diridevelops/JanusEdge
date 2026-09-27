# Bug Fix: Sync the crosshair price across replay charts

**Date:** 2026-09-27

## Bug

Moving the pointer over one replay chart synchronized the crosshair time on sibling charts, but the horizontal price position snapped to the target candle's close. The expected behavior is to show the same hovered price level on each chart.

## Root Cause

The source chart broadcast the close/value from `seriesData` instead of converting the pointer's vertical coordinate into a price. The receiving chart also fell back to its candle close when no price was supplied. Both behaviors replaced the hovered price with a candle value.

## Fix

Convert the source pointer's Y coordinate with the source series `coordinateToPrice`, broadcast that price, and apply it on the target chart's series. Clear the crosshair when a valid timestamp and price are unavailable instead of substituting the target candle close.

## Verification

Reviewed the synchronization path and the chart API usage. Automated tests and browser UI checks were not run.
