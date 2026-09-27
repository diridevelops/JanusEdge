# Quickstart: Backtest Candle Replay

This guide describes validation to run after implementation. It was not executed during planning because this task generated design artifacts only.

## Prerequisites

- Python 3.12 and uv.
- Node.js 20 or later and npm.
- Docker Compose for MongoDB and MinIO, or equivalent local services.
- A configured JanusEdge environment and an authenticated user.
- Network access for the pinned Dukascopy downloader dependency and selected historical downloads.
- Network access to the supported-instrument catalog exposed by the pinned downloader.

## Start the application

From the repository root, start supporting services:

~~~powershell
docker compose up mongo minio -d
~~~

Start the backend:

~~~powershell
cd backend
uv sync
uv run flask run --port 5000
~~~

In a second terminal, start the durable preparation worker. It uses the same backend environment and MongoDB/MinIO services as the API:

~~~powershell
cd backend
uv run python -m app.backtests.worker
~~~

In a third terminal, start the frontend:

~~~powershell
cd frontend
npm ci
npm run dev
~~~

Alternatively, run the full stack with Docker Compose according to the repository README; the `backtest-worker` service must start separately from the API service.

## End-to-end validation scenarios

1. Sign in and switch to Backtest mode. Confirm Real trade, account, import, and report data do not appear in Backtest; return to Real mode and confirm the existing Real behavior remains available.
2. Confirm the instrument selector is populated from `GET /api/backtest/instruments`. Create a run with one listed instrument and an inclusive display-timezone date range within one calendar year; confirm a code outside the current downloader catalog is rejected without creating a run or account. Confirm the run list shows a progress stage and a percentage when measurable (otherwise indeterminate progress), and that the generated Backtest account identifies the instrument and range. Check the February 29 boundary rule.
3. Use ranges with fully empty dates, partial gaps, all-no-data, and provider failure. Confirm gap summaries do not introduce synthetic candles; no-data/failure results remain dismissible on the run-list page after the run/account are deleted and offer the specified next action.
4. Use a range with available candles. Confirm the ready run has coverage and gap summaries, and its stored candle snapshot is run-specific. Refresh shared market data and reopen the run; the replay must still read its original snapshot.
5. Open a newly ready run. Confirm its workspace initializes to exactly one 1m chart pane, persists a stable chart id, and restores after reload. Confirm the compact, chart-styled timeframe dropdown is overlaid at the upper-left inside the plot and its standard presets appear before Custom. Select Custom; confirm a popup opens, enter a valid whole-minute interval, and confirm that interval (such as 7m) appears directly in the dropdown and persists after reload. Confirm invalid values show an error without replacing the last valid interval. Add another chart with the tab-row `+` button and confirm it is created and activated in the focused tab group; reorder tabs, move one to another group, drag it to a pane edge to create horizontal and vertical splits, resize the split panes, and close tabs while retaining at least one chart. Confirm no separate toolbar/instruction row or redundant chart header is shown. Confirm reload restores the full layout tree, split sizes/orientation, tab order, active tabs, chart ids, and selected intervals. Confirm CandleKit ReplayControls drive the one shared replay cursor for every panel. At 5m or another higher interval, step through source candles and verify the active bar updates from only the candles already replayed. Step backward and confirm later candles disappear.
6. Play at 1x, 5x, and 20x. Confirm each rate counts one-minute source candles per second regardless of chart interval. Seek to a gap and beyond the final candle; confirm the specified next-candle/completion behavior and that seeking pauses playback.
7. Test workspace migration and concurrency. For a run with legacy flat chart-tab records but no workspace document, confirm first open migrates them into visible sibling panes in saved order and preserves every id and interval; with no legacy records, confirm it creates one 1m pane. Confirm initialization is saved before workspace edits are enabled. Open the same run in two sessions, save a layout in the first, then attempt a stale save in the second; confirm the stale write returns 409 and does not overwrite the first. Confirm the second session retains its local draft and offers loading the remote layout or explicitly reapplying the draft against the latest revision. Add panels with different intervals and confirm replay position is shared and cannot be disabled. Confirm crosshair synchronization is enabled without a Chart sync section; when a target has no candle at the exact crosshair time, confirm it uses the nearest prior available candle (or no crosshair when none exists). Pan and zoom one pane and confirm other panes keep their own ranges. Move a panel while a drawing save is pending and confirm the save is flushed and replay/crosshair subscriptions are not duplicated.
8. Create, move, edit, and delete drawings. Navigate away and reopen the run; confirm drawings restore for the same user, run, and interval. Rewind and confirm the pinned CandleKit artifact's replay-aware visibility behavior; if absent, confirm drawings with any future anchor are hidden until all anchors are reached again. Under the fallback, also confirm a later-created drawing anchored entirely in the past remains visible after rewind. Open the run as another user and confirm the saved drawings are not visible.
9. Toggle JanusEdge light/dark mode. Confirm CandleKit canvas, drawing toolbar, replay controls, chart tabs, and the in-chart timeframe selector use JanusEdge colors, borders, and button styles.
10. Confirm the existing Real TradeDetail chart still shows its candlesticks, execution markers, average-entry/exit lines, interval selector, and light/dark colors after the Lightweight Charts 5.x compatibility update.
11. Exercise interrupted preparation and retry. Confirm retry reuses the same job/run/account and resumes after the latest completed UTC-date checkpoint; only an incomplete date may be fetched again. Restart the API backend while a run is preparing and confirm the separate worker continues. Restart the worker and confirm its expired lease is reclaimed from the last checkpoint. Failed/no-data run records and jobs are removed while the user-scoped preparation result remains dismissible.
12. While a run is preparing, confirm the run list refreshes progress every five seconds. During confirmed deletion, confirm the pending-deletion status refreshes too; polling stops only after the list has no preparing or deleting runs.
13. Confirm each chart pane initially snaps to the latest candle available at the saved replay cursor. Play and step forward/backward while following; verify the latest revealed candle stays at the right edge, including after a backward seek. Pan one pane backward and forward away from the latest candle; verify replay updates do not move its viewport and a lower-right return button appears. Confirm this does not change other panes. Select the button, double-click the time axis, or manually pan back to the latest edge; each action must restore follow and hide the button. Pan forward into future space and confirm follow reactivates when replay naturally catches up to the live edge. On a higher-timeframe chart, update the active bar with another source candle and confirm the horizontal range does not jump when no new chart bar is added.
14. In a test fixture, associate one or more Backtest trades with a run's dedicated account. Open the run list and select Delete; verify the confirmation identifies the run/account and warns that linked trades will be permanently removed. Cancel and confirm all resources remain. Confirm deletion and verify a 202 response is shown only as pending cleanup; the run is non-playable while pending and may be hidden from Backtest views. After completion, inspect storage and assert the run/deletion marker, account, linked trade documents and trade-owned dependent records/files, preparation job, replay cursor, chart layout, and drawings are physically absent, and listing the run's MinIO prefix returns zero objects (including staged, snapshot, and unreferenced objects). Repeat with a preparing run while the worker holds a lease and with a worker restart during cleanup; it must never become ready, cleanup must resume, and another run plus all Real records must remain unchanged. Confirm another user's request for the same run id receives the standard not-found response.
15. Create runs whose selected replay start is near a month end and a daylight-saving boundary. Confirm warm-up begins one calendar month before the selected local start date (clamped to the preceding month's final valid day), while the requested dates, one-year validation, account label, and replay-period coverage remain unchanged. With a complete, partial, and empty warm-up range, verify the run snapshot retains all available earlier candles as chart history; an incomplete warm-up does not block readiness if selected-period data exists. On first open, verify the saved cursor, replay controls, progress, and completion bounds start within the selected replay period, not in warm-up. Step backward at the initial cursor and seek to a pre-start timestamp; both must remain at the first eligible replay candle. Finally verify that a replay period with no candles is still reported as no-data even when warm-up candles exist, and that no later replay-period candle appears before the cursor reaches it.

## Automated checks

Run from the backend directory:

~~~powershell
uv run pytest
~~~

Run from the frontend directory:

~~~powershell
npm test
npm run lint
npm run build
~~~

The frontend build confirms the locked CandleKit and Lightweight Charts types resolve together. Browser validation is still needed for drawing persistence, cursor-bounded replay, multi-interval synchronization, follow/detach behavior, and visual styling.

