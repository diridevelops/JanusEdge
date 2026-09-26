# Quickstart: Backtest Candle Replay

This guide describes validation to run after implementation. It was not executed during planning because this task generated design artifacts only.

## Prerequisites

- Python 3.12 and uv.
- Node.js 20 or later and npm.
- Docker Compose for MongoDB and MinIO, or equivalent local services.
- A configured JanusEdge environment and an authenticated user.
- Network access for the pinned Dukascopy downloader dependency and selected historical downloads.

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

In another terminal, start the frontend:

~~~powershell
cd frontend
npm ci
npm run dev
~~~

Alternatively, run the full stack with Docker Compose according to the repository README.

## End-to-end validation scenarios

1. Sign in and switch to Backtest mode. Confirm Real trade, account, import, and report data do not appear in Backtest; return to Real mode and confirm the existing Real behavior remains available.
2. Create a run with one supported instrument and an inclusive display-timezone date range within one calendar year. Confirm the run list shows a progress stage and a percentage when measurable (otherwise indeterminate progress), and that the generated Backtest account identifies the instrument and range. Check the February 29 boundary rule.
3. Use ranges with fully empty dates, partial gaps, all-no-data, and provider failure. Confirm gap summaries do not introduce synthetic candles; no-data/failure results remain dismissible on the run-list page after the run/account are deleted and offer the specified next action.
4. Use a range with available candles. Confirm the ready run has coverage and gap summaries, and its stored candle snapshot is run-specific. Refresh shared market data and reopen the run; the replay must still read its original snapshot.
5. Open the ready run. Confirm the persisted chart tabs and selected intervals restore after reload, that invalid custom intervals leave the last valid interval selected, and that one shared replay cursor drives all tabs. At 5m or another higher interval, step through source candles and verify the active bar updates from only the candles already replayed. Step backward and confirm later candles disappear.
6. Play at 1x, 5x, and 20x. Confirm each rate counts one-minute source candles per second regardless of chart interval. Seek to a gap and beyond the final candle; confirm the specified next-candle/completion behavior and that seeking pauses playback.
7. Add tabs with different intervals. Confirm replay position is shared and cannot be disabled. Confirm crosshair, pan, and zoom sync start enabled; toggle each independently. When a target has no candle at the exact crosshair time, confirm it uses the nearest prior available candle (or no crosshair when none exists); verify pan/zoom ranges use the same UTC bounds rounded outward to target intervals.
8. Create, move, edit, and delete drawings. Navigate away and reopen the run; confirm drawings restore for the same user, run, and interval. Rewind and confirm the pinned CandleKit artifact's replay-aware visibility behavior; if absent, confirm drawings with any future anchor are hidden until all anchors are reached again. Under the fallback, also confirm a later-created drawing anchored entirely in the past remains visible after rewind. Open the run as another user and confirm the saved drawings are not visible.
9. Toggle JanusEdge light/dark mode. Confirm CandleKit canvas, drawing toolbar, replay controls, chart tabs, and sync controls use JanusEdge colors, borders, and button styles.
10. Confirm the existing Real TradeDetail chart still shows its candlesticks, execution markers, average-entry/exit lines, interval selector, and light/dark colors after the Lightweight Charts 5.x compatibility update.
11. Exercise interrupted preparation and retry. Confirm retry reuses the same run/account; failed/no-data run records are removed while the user-scoped preparation result remains dismissible.

## Automated checks

Run from the backend directory:

~~~powershell
uv run pytest
~~~

Run from the frontend directory:

~~~powershell
npm run lint
npm run build
~~~

The frontend build confirms the locked CandleKit and Lightweight Charts types resolve together. Browser validation is still needed for drawing persistence, cursor-bounded replay, multi-interval synchronization, and visual styling.

