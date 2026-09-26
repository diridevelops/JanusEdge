# Implementation Plan: Backtest Candle Replay

**Branch**: feature/backtester (Spec Kit feature slug: 001-backtest-workspace) | **Date**: 2026-09-26 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification plus the user’s planning direction: use CandleKit for Backtest charting, replay, synchronization, and drawing state; use CandleKit’s React components and style them to match JanusEdge.

## Summary

Add the Backtest workspace described in the feature specification, with one immutable Dukascopy one-minute candle snapshot per run, one shared replay cursor, and a persisted, unbounded chart-tab set per run. CandleKit is the required chart and interaction layer: its React ChartView, ReplayControls, and DrawingToolbar components host the charts and controls; its replay and sync engines provide the replay and chart-interaction mechanisms. JanusEdge remains authoritative for run data, saved replay position, chart-tab configuration, and user-scoped drawing persistence.

The integration must preserve the no-look-ahead rule. CandleKit’s replay source reads the run’s one-minute snapshot, and a JanusEdge adapter aggregates only the source candles exposed through the current replay cursor into each tab’s selected interval. Crosshair and visible-range synchronization pass through CandleKit’s SyncEngine, with an adapter that translates between logical bar indexes and UTC timestamps so tabs at different timeframes remain aligned.

## Technical Context

**Language/Version**: Python 3.12; TypeScript 5.6; React 19.

**Primary Dependencies**: Flask 3.1.1, MongoDB, MinIO, Pandas, PyArrow; CandleKit React bindings from @getcandlekit/charts 0.1.1; lightweight-charts 5.x as required by CandleKit.

**Storage**: MongoDB for user-scoped Backtest run/account metadata, replay position, and drawing documents. MinIO for immutable run-owned one-minute Parquet snapshots. CandleKit holds live chart/controller state in the browser.

**Testing**: Backend pytest suite; frontend ESLint and TypeScript/Vite production build; focused API, replay-adapter, synchronization, and browser scenarios described in quickstart.md. This planning task did not run tests.

**Target Platform**: Existing self-hosted web application; Flask API and React/Vite frontend in supported evergreen browsers.

**Project Type**: Full-stack web application.

**Performance Goals**: The specification sets playback at 1, 5, or 20 one-minute source candles per second. The user chose no fixed chart-tab maximum and no additional chart-tab capacity or rendering-performance target for v1. Use CandleKit’s incremental bar update for normal playback and rebuild cursor-bounded data after seek or step-back; avoid routing every candle through React component state. The specified playback rates remain product requirements, but no separate responsiveness guarantee is defined across an unbounded number of tabs.

**Constraints**: One instrument and one-minute source bars per run; maximum one-year date range; UTC-aligned, left-closed/right-open chart buckets; no synthetic candles; no future bars rendered; Real and Backtest data remain separate; authenticated resources are scoped to the requesting user. CandleKit’s current repository describes the package as early-stage, so pin versions and isolate it behind a JanusEdge adapter.

**Scale/Scope**: Per-user runs of up to one calendar year of one-minute candles; any number of persisted chart tabs per ready run, with one shared replay controller per open run; independent crosshair, pan, and zoom synchronization controls.

## Constitution Check

**Constitution status**: .specify/memory/constitution.md is still the Spec Kit placeholder template: its principles and gates contain bracketed placeholder text. It does not define ratified project rules, so this plan cannot honestly claim a pass or identify a constitution violation. The feature requirements below are used as the design gates until the project constitution is completed.

**Pre-design feature gates**:

- No-look-ahead: chart data is derived from the immutable run snapshot only through the shared replay cursor.
- Workspace isolation: every run, account, candle read, replay-position write, and drawing read/write is scoped to the authenticated user and Backtest mode.
- Run immutability: refreshed market data cannot replace the snapshot already assigned to a ready run.
- Time correctness: source instants stay UTC; interval membership uses fixed UTC boundaries; display timezone affects formatting only.
- CandleKit boundary: the React/chart adapter isolates version-specific library APIs and style overrides.

**Post-design check**: The proposed model and contracts preserve each feature gate. Implementation must verify package compatibility and the chart adapter against the locked dependency artifacts before building feature flows. The user resolved the drawing-visibility and capacity questions: preserve replay-aware drawing behavior if present in the pinned CandleKit artifact; otherwise use anchor-only visibility, with no creation/edit-time history, and impose no additional tab cap or performance SLA (checklist CHK006 and CHK020). Anchor-only visibility means a drawing created later but anchored entirely in the past may remain visible after rewind; this is an accepted v1 trade-off.

## Architecture and Data Flow

1. The authenticated run-creation request validates instrument, dates, and display timezone, creates one preparing run and its associated Backtest account, then starts the Dukascopy provider.
2. The provider downloads one-minute candles and stores the exact result under a run-specific immutable MinIO object key. MongoDB records coverage, fully empty dates, summaries of partial source-candle gaps, checksum, staged progress, and ready status. A separate dismissible, user-scoped preparation notice survives deletion of a failed or no-data run and is removed when dismissed. The existing tick-derived /market-data/ohlc store is not the source for these runs.
3. One CandleKit replay controller per run reads the immutable snapshot through a ReplayDataSource adapter. The same controller and ReplayControls drive every chart tab.
4. Each persisted tab has a CandleKit ChartView and its own timeframe; its identity, order, and selected interval are restored with the run. The tab set has no fixed v1 limit. The chart adapter emits only the aggregate bar built from source candles seen through the current cursor. Forward playback uses incremental chart updates; seeking and stepping backward rebuild visible bars from the cursor-bounded source.
5. CandleKit’s SyncEngine routes chart interaction synchronization. A JanusEdge adapter maps source ranges and crosshair positions through UTC time before applying them to charts with different interval widths. A crosshair with no exact target candle snaps to the nearest available candle at or before the source time; synchronized visible ranges preserve UTC bounds and round outward to each target interval.
6. Each tab’s CandleKit DrawingController owns its live drawing model and exposes the standard drawing tools for create, select, reposition, edit, and remove. The app loads and saves DrawingEngine export/import payloads through authenticated, run- and timeframe-scoped API routes. Inspect the pinned CandleKit artifact for replay-aware drawing visibility and preserve that behavior if present; otherwise hide a drawing while any time anchor is beyond the replay cursor and show it again once all anchors are at or before the cursor. The fallback does not use creation/edit time or alter the saved drawing state; consequently, a later-created drawing anchored in the past may remain visible after rewind. Edits and removals are persisted.
7. ThemeContext selects CandleKit’s light/dark theme. Scoped CSS overrides and the chart theme palette map CandleKit controls and overlays to JanusEdge’s Tailwind gray, brand, profit, and loss colors.

## Project Structure

~~~text
backend/app/backtests/
├── __init__.py
├── routes.py
├── schemas.py
├── repository.py
├── service.py
├── dukascopy_provider.py
└── snapshot_store.py

frontend/src/
├── api/backtests.api.ts
├── types/backtest.types.ts
├── pages/BacktestRunListPage.tsx
├── pages/BacktestReplayPage.tsx
├── hooks/useBacktestReplay.ts
├── hooks/useBacktestChartSync.ts
├── components/backtest/
│   ├── BacktestRunForm.tsx
│   ├── BacktestRunList.tsx
│   ├── BacktestReplayControls.tsx
│   ├── BacktestChartTab.tsx
│   ├── CandleKitReplayChart.tsx
│   └── BacktestSyncControls.tsx
└── styles/backtest-candlekit.css

specs/001-backtest-workspace/
├── plan.md
├── research.md
├── data-model.md
├── contracts/backtest-api.md
└── quickstart.md
~~~

**Structure Decision**: Add a focused Flask backtests area and React Backtest pages/components. Keep the existing Real trade-detail chart component separate as a product surface; because CandleKit requires Lightweight Charts 5.x, upgrade the shared frontend dependency and make the minimal API adaptation needed to preserve the existing chart’s markers, price lines, and theme behavior. Keep CandleKit-specific APIs and styles behind the Backtest chart adapter.

## Design Decisions

- Use CandleKit’s React entry for chart views, replay controls, and the standard drawing toolbar. Bind the required 1x, 5x, and 20x speeds to the CandleKit replay controller; if ReplayControls cannot expose those exact choices, supplement its presentation with JanusEdge-styled React controls while keeping CandleKit as the transport engine. Do not build a second chart, replay, synchronization, or drawing engine or use CandleKit only as an invisible dependency.
- Pin CandleKit to 0.1.1 and lock a single Lightweight Charts 5.x version. Confirm the installed package artifact exports the required React, replay, sync, and drawing APIs before feature implementation; current repository documentation and npm artifact may differ. If a required core API is missing, stop the integration and select a compatible CandleKit release before proceeding; do not silently substitute another library for a required CandleKit responsibility.
- Use one ReplayController for the run, not one replay instance per tab. Persist the cursor on the run record, restore it on page open, and serialize and version cursor writes so stale requests cannot overwrite a later selected position, including an intentional step-back. Persist tab identity, order, and interval per run, without imposing a fixed tab count.
- Use CandleKit’s ReplayDataSource with day-level candle reads and its available-date methods. Do not pass a fully aggregated future timeframe series to ChartView. Aggregate from only the one-minute bars revealed by replay.
- Use CandleKit SyncEngine for cross-chart event routing, but never forward logical indexes unchanged between timeframes. Convert source logical ranges to UTC timestamps, snap crosshair sync to the nearest available prior target candle, and round synchronized visible ranges outward to target interval boundaries. Replay cursor sharing stays always-on and independent of the optional visual-sync switches.
- Use DrawingController and DrawingEngine as the source of live drawing geometry and the standard v1 drawing tool set. Persist exported state through the JanusEdge API keyed by user, run, and interval. Hydrate before enabling drawing edits, then debounce writes and flush on seek, pause, and route exit. Preserve replay-aware drawing visibility if present in the pinned artifact; otherwise filter by anchor time only. Do not add creation/edit-time visibility history in v1. Edits and deletions must persist. This gives authenticated state that survives reloads without treating CandleKit’s synchronous local KVStore as a backend adapter.
- Apply the app’s ThemeContext and theme colors to CandleKit, import its stylesheet once, and scope CSS overrides to the Backtest chart subtree. Keep chart toolbars and controls visually consistent with JanusEdge cards, buttons, borders, and dark mode.
- Integrate the existing dukascopy-market-data Python package through its importable API, pinned to a Git revision in uv.lock. Stage its result, then copy the exact one-minute selection to a run-owned immutable MinIO snapshot. Resolve the package’s PyArrow minimum against the backend’s current PyArrow 18.1.0 pin during dependency integration.

## Complexity Tracking

No constitution-defined complexity exception can be assessed because the constitution is uninitialized. The two adapters above are required by the feature’s different-timeframe synchronization contract and by CandleKit’s synchronous drawing storage interface; their rationale and alternatives are recorded in research.md.




