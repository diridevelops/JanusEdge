# Backtest price axis repeats one rounded value

## Bug

The replay charts showed the same rounded value (for example, `1.03`) at multiple price-axis ticks and in the last-price marker, making nearby FX prices indistinguishable.

## Root Cause

CandleKit creates its main Lightweight Charts series with the library's default price format of two decimal places (`minMove: 0.01`). Backtest replay supplied prices without overriding that default, so FX values with smaller increments were rounded to identical labels.

## Fix

Set the series price format when a chart registers with the replay controller. Recognized fiat currency pairs use five fractional digits, or three for JPY-quoted pairs, and the matching `minMove`. Other instruments keep the two-decimal default.

## Verification

- Frontend TypeScript check (`tsc --noEmit`) passed.
- Targeted ESLint for the replay hook and price-format helper passed.
- Frontend tests and browser/UI validation were not run. UI validation remains deferred under the user's instruction.
