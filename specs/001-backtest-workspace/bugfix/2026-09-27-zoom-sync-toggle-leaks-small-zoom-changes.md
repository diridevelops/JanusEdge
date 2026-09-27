# Bug Fix: Zoom sync remains active when disabled

**Date:** 2026-09-27

## Bug

Disabling Zoom in the replay chart sync controls could still synchronize some zoom gestures to sibling panes.

## Root Cause

The source classified viewport changes by comparing visible-range spans. Span changes below `max(0.5 bars, 1% of the prior span)` were classified as pans. A small zoom gesture could therefore pass the Zoom-off check while Pan remained enabled. This cause is supported by the classifier and broadcast path; the interaction was not reproduced in the browser during this turn.

## Fix

Replay chart ranges now remain pane-local: the SyncEngine group enables replay cursor and crosshair events only, with no `timeRange` flag or range broadcast/apply path. Removed the Chart sync section and its unused component. Crosshair sync remains enabled, while chart pan and zoom continue to work locally without syncing to other panes.

## Verification

- Source review confirmed the replay sync group is created with only `cursor` and `crosshair`; no `timeRange` synchronization path remains in the replay sync hook.
- Automated tests and browser UI checks were not run in this turn because the request did not ask for verification.
