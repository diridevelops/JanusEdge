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
5. Open a newly ready run. Confirm its workspace initializes to exactly one 1m chart pane, persists a stable chart id, and restores after reload. Add another chart and confirm it is created and activated in the focused tab group; reorder tabs, move one to another group, drag it to a pane edge to create horizontal and vertical splits, resize the split panes, and close tabs while retaining at least one chart. Confirm reload restores the full layout tree, split sizes/orientation, tab order, active tabs, chart ids, and selected intervals. Confirm CandleKit ReplayControls drive the one shared replay cursor for every panel. At 5m or another higher interval, step through source candles and verify the active bar updates from only the candles already replayed. Step backward and confirm later candles disappear.
6. Play at 1x, 5x, and 20x. Confirm each rate counts one-minute source candles per second regardless of chart interval. Seek to a gap and beyond the final candle; confirm the specified next-candle/completion behavior and that seeking pauses playback.
7. Test workspace migration and concurrency. For a run with legacy flat chart-tab records but no workspace document, confirm first open migrates them into visible sibling panes in saved order and preserves every id and interval; with no legacy records, confirm it creates one 1m pane. Confirm initialization is saved before workspace edits are enabled. Open the same run in two sessions, save a layout in the first, then attempt a stale save in the second; confirm the stale write returns 409 and does not overwrite the first. Confirm the second session retains its local draft and offers loading the remote layout or explicitly reapplying the draft against the latest revision. Add panels with different intervals and confirm replay position is shared and cannot be disabled. Confirm crosshair, pan, and zoom sync start enabled; toggle each independently. When a target has no candle at the exact crosshair time, confirm it uses the nearest prior available candle (or no crosshair when none exists); verify pan/zoom ranges use the same UTC bounds rounded outward to target intervals. Move a panel while a drawing save is pending and confirm the save is flushed and sync/replay subscriptions are not duplicated.
8. Create, move, edit, and delete drawings. Navigate away and reopen the run; confirm drawings restore for the same user, run, and interval. Rewind and confirm the pinned CandleKit artifact's replay-aware visibility behavior; if absent, confirm drawings with any future anchor are hidden until all anchors are reached again. Under the fallback, also confirm a later-created drawing anchored entirely in the past remains visible after rewind. Open the run as another user and confirm the saved drawings are not visible.
9. Toggle JanusEdge light/dark mode. Confirm CandleKit canvas, drawing toolbar, replay controls, chart tabs, and sync controls use JanusEdge colors, borders, and button styles.
10. Confirm the existing Real TradeDetail chart still shows its candlesticks, execution markers, average-entry/exit lines, interval selector, and light/dark colors after the Lightweight Charts 5.x compatibility update.
11. Exercise interrupted preparation and retry. Confirm retry reuses the same job/run/account and resumes after the latest completed UTC-date checkpoint; only an incomplete date may be fetched again. Restart the API backend while a run is preparing and confirm the separate worker continues. Restart the worker and confirm its expired lease is reclaimed from the last checkpoint. Failed/no-data run records and jobs are removed while the user-scoped preparation result remains dismissible.
12. While a run is preparing, confirm the run list refreshes progress every five seconds; confirm polling stops after the list has no preparing runs.

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

The frontend build confirms the locked CandleKit and Lightweight Charts types resolve together. Browser validation is still needed for drawing persistence, cursor-bounded replay, multi-interval synchronization, and visual styling.

