# Research: Backtest Candle Replay

Research for the implementation plan was based on the active feature specification, the JanusEdge source tree, the published CandleKit npm artifact, and the sibling Dukascopy downloader package. The CandleKit tarball was downloaded and inspected in a temporary directory; no application dependency has been installed yet.

## Decisions

### 1. Use CandleKit’s React integration for the Backtest chart surface

**Decision**: Use the published CandleKit 0.1.0 React entry for ChartView and its replay and drawing overlays, including ReplayControls and DrawingToolbar. Use CandleKit’s replay and synchronization engines through a narrow JanusEdge adapter.

**Rationale**: The npm registry returned E404 for `@getcandlekit/charts@0.1.1`; its package page lists one published version, 0.1.0. I inspected the 0.1.0 tarball (`sha512-E7TQWwcRi5uLJoOrSIoRHvBmrP9FhXUa9QfN5hcj1kitSnYaOmXiMrwO4Hpa5HF1aU9EFC49j1y9XJmkcYaLVQ==`). Its declarations export `ChartView`, `ReplayControls`, `DrawingToolbar`, `ReplayDataSource`, `SyncEngine`, `DrawingEngine`, and `DrawingController`. `ReplayControls` accepts a `speeds` prop, so the required `[1, 5, 20]` rates can be supplied without replacing its speed selector. The user selected CandleKit for the Backtest charting, replay, synchronization, and drawing-state responsibilities, and 0.1.0 satisfies those required APIs.

**Alternatives considered**: Keep building directly on Lightweight Charts and create custom replay, drawing, and sync systems. Rejected because it would duplicate the responsibilities the user assigned to CandleKit. Continue using the existing Real trade chart unchanged at the feature level; only adapt its direct Lightweight Charts API use as required by the shared dependency upgrade.

Sources: [CandleKit npm package and published versions](https://www.npmjs.com/package/%40getcandlekit/charts), [CandleKit 0.1.0 artifact](https://registry.npmjs.org/@getcandlekit/charts/-/charts-0.1.0.tgz), [CandleKit README](https://github.com/rohanbeingsocial/candlekit-charts/blob/main/README.md).

### 2. Align JanusEdge on Lightweight Charts 5.x and pin CandleKit

**Decision**: Add CandleKit at exact version 0.1.0 and use one locked Lightweight Charts 5.x dependency across the frontend. Adapt the existing direct Lightweight Charts trade-detail wrapper to the 5.x API without changing its user-facing behavior.

**Rationale**: CandleKit package metadata declares Lightweight Charts 5.x as a peer dependency. JanusEdge currently depends on 4.2.1 and its Real trade chart uses the 4.x addCandlestickSeries API. Loading two major versions in one application would add bundle and type-resolution complexity; one shared version with a small compatibility migration is simpler.

CandleKit’s README describes the project as early-stage and advises pinning the version. The registry currently publishes only 0.1.0; 0.1.1 cannot be installed. The 0.1.0 metadata declares MIT licensing, React 18/19 support, Lightweight Charts 5.x, and additional peers for indicator and workspace features. Pin 0.1.0 and keep it behind the adapter so later upgrades remain deliberate.

**Alternatives considered**: Keep Lightweight Charts 4.x in Real mode and install a second 5.x copy for Backtest. Rejected because it creates duplicate runtimes and leaves package-manager peer resolution and type compatibility more complex. Float CandleKit to latest. Rejected because the upstream project explicitly recommends pinning.

Sources: [CandleKit npm metadata](https://www.npmjs.com/package/%40getcandlekit/charts), [CandleKit README and maturity/license notes](https://github.com/rohanbeingsocial/candlekit-charts/blob/main/README.md).

### COMB midpoint and volume semantics

The user selected Dukascopy COMB data represented as midpoint OHLC. Compute each open/high/low/close by averaging the corresponding BID and ASK value from the same minute. Dukascopy COMB files aggregate BID and ASK separately, so averaging the side highs/lows is an estimate and cannot reproduce exact tick-level midpoint extrema without synchronized tick data. Sum `bidVolume` and `askVolume` for the one available chart-volume value; the downloader documents these fields as quoted liquidity at the best bid/ask, not executed trade volume. Keep this meaning available in accessible chart text without a persistent visible note.

Source: [Dukascopy downloader README](https://github.com/diridevelops/dukascopy-market-data-cli#decoding-and-aggregation).

### 3. Use an immutable run-owned one-minute snapshot as replay truth

**Decision**: Keep Dukascopy source candles separate from JanusEdge’s imported-tick market-data store. Save each ready run’s exact selection in a user- and run-scoped immutable MinIO Parquet object and store its coverage, gaps, checksum, and source metadata in MongoDB.

**Rationale**: The existing /market-data/ohlc route reads candles derived from locally imported ticks. It does not download Dukascopy data or guarantee an immutable replay selection. A run-owned snapshot prevents later refreshes from changing historical replay. The sibling dukascopy-market-data package documents both an importable Python API and Parquet output, so the Flask service can use the API directly and stage output without launching a subprocess.

The sibling package requires PyArrow 25 or later, while JanusEdge currently pins PyArrow 18.1.0. Dependency resolution must reconcile that difference and validate the current Pandas combination. Its `instruments.fetch_instrument_codes` function fetches the current catalog and returns validated, sorted codes; its `candles.run_downloads` function processes one requested UTC date, which supports durable per-date checkpoints. Run-form options and server validation use the same live catalog source.

**Alternatives considered**: Reuse /market-data/ohlc or its shared cache. Rejected because those datasets are generated from imported tick files and can be rebuilt. Download candles in the browser. Rejected because user credentials, persistence, ownership checks, progress, and immutable snapshots belong at the authenticated backend boundary. Duplicate the downloader implementation inside JanusEdge. Rejected because a maintained package API already exists in the adjacent project.

Sources: [JanusEdge market-data route](../../backend/app/market_data/routes.py), [sibling downloader README](../../../dukascopy-market-data-cli/README.md), [sibling downloader project metadata](../../../dukascopy-market-data-cli/pyproject.toml).

### 4. Let CandleKit drive replay while JanusEdge enforces cursor-bounded display

**Decision**: Implement CandleKit’s ReplayDataSource over the immutable run snapshot, returning only requested UTC-day data and available-date lists. Keep one ReplayController per active run. Send ordinary forward-bar events to each chart through incremental updates. Rebuild visible chart data from the cursor after seek or step-back.

**Rationale**: CandleKit documents a day-oriented replay data source, deterministic cursor, playback controls, per-bar callbacks, and efficient updateBar handling for normal playback. A shared controller naturally preserves the specification’s one-cursor-across-tabs behavior. JanusEdge must own the session calendar and gaps. It must not initialize higher-timeframe charts with pre-aggregated bars that include candles beyond the current cursor.

Each higher-timeframe candle is aggregated from the one-minute source events seen so far, using the existing UTC-aligned, left-closed/right-open boundaries. Chart time values remain UTC epoch milliseconds. Display timezone is applied by formatting, not by shifting times before aggregation or drawing.

**Alternatives considered**: Give each chart tab an independent replay controller. Rejected because tabs could diverge. Feed full higher-timeframe history and hide bars by styling. Rejected because active-bar high, low, and close values could reveal future source candles.

Sources: [CandleKit replay documentation](https://github.com/rohanbeingsocial/candlekit-charts/blob/main/docs/replay-system.md), [CandleKit architecture](https://github.com/rohanbeingsocial/candlekit-charts/blob/main/ARCHITECTURE.md).

### 5. Use CandleKit SyncEngine for crosshair synchronization

**Decision**: Use CandleKit SyncEngine for crosshair event routing only. Convert the emitting chart’s logical index to a UTC time value and map that timestamp into the receiving chart’s logical range. Keep replay synchronization in the one shared ReplayController; panning and zooming remain local and have no sync switches.

**Rationale**: CandleKit’s SyncEngine is framework-independent and requires the host to attach chart members and route events. Different intervals have different logical spacing, so broadcasting a logical index directly would misalign crosshairs. The JanusEdge adapter preserves the app’s absolute-time synchronization contract. The selected product behavior synchronizes crosshairs while keeping each pane's horizontal range independent.

**Alternatives considered**: Broadcast logical indexes without conversion. Rejected because a position such as bar 100 on a one-minute chart does not represent the same time as bar 100 on a one-hour chart. Synchronize pan and zoom. Rejected because the clarified behavior keeps each pane's range local. Write an unrelated custom sync engine. Rejected because CandleKit handles crosshair event routing and the adapter only needs the time conversion.

Sources: [CandleKit sync contracts](https://github.com/rohanbeingsocial/candlekit-charts/blob/main/src/sync/types.ts), [CandleKit architecture](https://github.com/rohanbeingsocial/candlekit-charts/blob/main/ARCHITECTURE.md).

### 6. Persist CandleKit drawings through JanusEdge’s authenticated API

**Decision**: Use CandleKit DrawingController and DrawingEngine for live state and toolbar behavior. Load and save the serialized export/import payload through an authenticated API document keyed by user, run, and timeframe. Do not use the built-in local storage key as the durable source of truth.

**Rationale**: CandleKit documents DrawingEngine export/import and drawing-change notifications. Its custom key-value store is synchronous, while JanusEdge API writes are asynchronous. An app adapter can hydrate before enabling edits and debounce backend writes after changes. This keeps drawing state in the same per-user context as the run and allows it to survive browser reloads and user devices.

The inspected 0.1.0 artifact exposes drawing anchors and DrawingEngine import/export but no replay-cursor visibility behavior. Apply the specified anchor-only filter and do not add drawing creation/edit-time history. This fallback means a drawing created later but anchored entirely in the past may remain visible after rewind, an accepted v1 trade-off.

**Alternatives considered**: Use CandleKit localStorage as the only persistence. Rejected because it is browser-local and does not follow authenticated user/run ownership. Pass JanusEdge’s asynchronous API directly as CandleKit’s KVStore. Rejected because the documented KVStore contract is synchronous. Keep drawings only in memory. Rejected because leaving and reopening a replay would lose the drawing state.

Sources: [CandleKit drawing guide](https://github.com/rohanbeingsocial/candlekit-charts/blob/main/docs/drawing-tools.md), [CandleKit drawing persistence interface](https://github.com/rohanbeingsocial/candlekit-charts/blob/main/src/drawing/persistence.ts), [CandleKit architecture](https://github.com/rohanbeingsocial/candlekit-charts/blob/main/ARCHITECTURE.md).

### 7. Theme CandleKit through the existing app theme

**Decision**: Pass ThemeContext’s light/dark choice and mapped chart palette into CandleKit, import its React overlay stylesheet once, then apply scoped CSS overrides under the Backtest chart subtree using JanusEdge tokens.

**Rationale**: The frontend already uses React 19, Tailwind, a shared ThemeContext, and brand/profit/loss colors. CandleKit supports custom themes and styles its React overlays with .ck-* CSS variables. This uses the app’s existing visual language rather than exposing a separate CandleKit theme toggle.

**Alternatives considered**: Keep CandleKit’s default theme and overlay styles. Rejected because it would not match the user’s request. Globally rewrite the library stylesheet. Rejected because a subtree-scoped override limits side effects and keeps vendor styles auditable.

Sources: [CandleKit architecture](https://github.com/rohanbeingsocial/candlekit-charts/blob/main/ARCHITECTURE.md), [JanusEdge ThemeContext](../../frontend/src/contexts/ThemeContext.tsx), [JanusEdge global styles](../../frontend/src/styles/globals.css).

### 8. Persist preparation jobs and recover them through MongoDB leases

**Decision**: Run preparation in a worker process separate from the Flask API. Store one preparation job per run in MongoDB, claim jobs with atomic expiring leases, and checkpoint completed UTC-date outcomes after writing their staged data to MinIO. Keep the worker as a dedicated Docker Compose service and do not add an external queue service for v1.

**Rationale**: A MongoDB-backed job record survives API and worker restarts and uses persistence and infrastructure already required by JanusEdge. A separate process lets a backend API restart occur without interrupting active downloads. If the worker itself stops, an expired lease permits another worker instance to reclaim the job. Per-date checkpoints match the downloader API and limit recovery to re-fetching only an incomplete date.

**Alternatives considered**: Run downloads in the request process or start an in-memory background thread. Rejected because process restart loses active work and queue state. Add Redis or another broker. Rejected for v1 because durable job state and atomic claim operations can use the existing MongoDB deployment without another service.

Sources: [sibling downloader instrument catalog API](../../../dukascopy-market-data-cli/src/dukascopy_market_data/instruments.py), [sibling downloader per-day API](../../../dukascopy-market-data-cli/src/dukascopy_market_data/candles.py).

### 9. Use CandleKit's workspace adapter for dockable chart panels

**Decision**: Use the workspace APIs exported by the pinned CandleKit 0.1.0 artifact with `FlexLayoutAdapter`, and register a JanusEdge chart panel that wraps the existing Backtest chart adapter. A workspace has a versioned layout tree plus chart panel configuration keyed by stable chart ids. Use `buildSingleChartLayout()` for the initial one-chart/1m layout. An accessible `+` button in the tab row creates and activates a tab in the focused tab group; dragging an existing tab to a pane edge moves it into a split and must not clone its chart identity or shared replay controller. Each panel places a compact, chart-styled timeframe dropdown inside the chart area, with standard presets before Custom. Custom opens an integer-minute popup, and the chosen interval is then displayed directly in the dropdown.

**Rationale**: The installed 0.1.0 declaration exports `createWorkspace`, `WorkspaceProvider`, `FlexLayoutAdapter`, `buildSingleChartLayout`, `buildDefaultLayout`, workspace management/subscription APIs, and custom panel registration. `buildDefaultLayout()` starts with two side-by-side charts, which contradicts the clarified one-pane default. The linked example demonstrates the intended workspace composition, but its current `main` branch is newer than the pinned package: it imports `ReplayPanel`, which the installed 0.1.0 declarations and bundle do not expose. Therefore use the pinned package's workspace adapter, not copy the current example verbatim, and retain JanusEdge's existing chart/replay implementation inside the custom panel rather than using the example's generic `ChartPanel`.

`FlexLayoutAdapter` needs `flexlayout-react` as an optional peer, but it is absent from JanusEdge's current frontend install and lockfile. Add a direct, exact dependency compatible with the pinned CandleKit peer when implementation begins, then lock and build against that pair. Do not float either package. The application should persist the serializable layout through authenticated JanusEdge endpoints; the example's `LocalStoragePersistence` is browser-local and cannot enforce user/run ownership or synchronize across devices.

For runs with the existing flat `backtest_chart_tabs` records and no workspace document, build a visible sibling-pane layout in existing position order and retain each tab's stable id and interval. This preserves the current behavior of seeing all saved charts together; the old records contain no split topology to recover. If there are no legacy records, initialize a single 1m pane. Persist this initial layout before enabling workspace edits, so a reload cannot generate a different chart id. Validate each saved tree and its panel metadata, including at least one chart, unique ids, supported chart type, valid intervals, and positive split weights. Use a revision-checked write to prevent one open replay page from silently replacing another's newer topology.

Layout operations only manage panel placement and chart identity. All panels remain attached to the run's single replay controller; chart sync and drawing state continue to use the existing UTC and run/timeframe contracts. Moving a panel may unmount it, so implementation must flush pending drawing saves and unregister chart sync/replay listeners during panel lifecycle cleanup before registering the same stable id in its new location.

**Alternatives considered**: Copy the linked latest example wholesale. Rejected because it imports a `ReplayPanel` not in pinned 0.1.0 and would substitute example chart/replay behavior for JanusEdge's cursor-bounded COMB replay. Use `buildDefaultLayout()` as the first-run layout. Rejected because it opens two panes despite the user's explicit one-pane default. Keep the flat CSS grid and add ad hoc drag handlers. Rejected because this duplicates docking, tab-group, split, resize, and serialization behavior already exported by CandleKit. Save the layout only in browser storage. Rejected because layouts are per authenticated user/run application state.

Sources: [CandleKit workspace example](https://github.com/rohanbeingsocial/candlekit-charts/blob/main/examples/workspace/main.tsx), [CandleKit workspace declarations in the pinned 0.1.0 artifact](https://registry.npmjs.org/@getcandlekit/charts/-/charts-0.1.0.tgz), [CandleKit npm metadata](https://www.npmjs.com/package/%40getcandlekit/charts).

### 10. Derive replay follow mode from each chart pane's viewport

**Decision**: Initialize each pane at the latest chart bar exposed by the saved replay cursor. Track follow independently per pane by comparing its `scrollPosition()` with the pane's normal real-time offset. While it is snapped to the latest bar, keep it at that offset as the cursor changes; when it is horizontally navigated away, retain that range until the user returns to latest. Provide a lower-right return-to-latest action and keep the existing time-axis double-click gesture. Do not add a backend endpoint or persisted follow flag.

**Rationale**: The frontend routes time-scale changes through `useBacktestChartSync`. The Lightweight Charts 5.2 `ITimeScaleApi` exposes `scrollPosition()`, `scrollToPosition(position, animated)`, `scrollToRealTime()`, and visible-logical-range change subscriptions, which support detecting each pane's position and restoring its live edge. `scrollToRealTime()` is always animated, so use it for one-time initialization and user snap actions; coalesce continuous replay updates and reposition without animation so 20x playback does not keep restarting animations. Deriving follow from each pane's effective viewport avoids a second boolean that can disagree with the actual chart. Crosshair synchronization does not alter viewport ranges; panning and zooming remain pane-local. Follow must use the newest bar exposed by the replay cursor, not the run's full snapshot, to preserve the no-look-ahead contract.

**Alternatives considered**: Always scroll every pane to the newest bar. Rejected because it prevents inspection of earlier or future-empty ranges. Use one run-wide follow toggle. Rejected because panes can be panned independently. Synchronize pan and zoom across panes. Rejected because the chart interaction contract keeps each pane's viewport local. Persist a follow boolean separately from the viewport. Rejected because chart remounts can make that value stale; follow is a property of the actual time scale position.

Source: [Lightweight Charts 5.2 ITimeScaleApi](https://tradingview.github.io/lightweight-charts/docs/api/interfaces/ITimeScaleApi) (`scrollPosition`, `scrollToRealTime`, and visible logical range notifications).

### 11. Delete a run through a durable, owner-scoped cleanup state

**Decision**: Require confirmation before permanent deletion. Mark the owned run `deleting` as a temporary durable cleanup marker, immediately stop replay, and let the existing worker resume cleanup after restarts. Hiding the run/account/trades from queries is only an interim pending state. Fence preparation publication and all replay/workspace/drawing writes once deletion starts. Physically remove every trade linked through the run's one-to-one account and all trade-owned dependent records/files using the existing trade cleanup path; remove all run-owned MongoDB data and every object under the run's MinIO prefix, including staged, immutable snapshot, and unreferenced objects; verify the prefix is empty; then remove the account and the run record carrying the marker last. Only that completed purge counts as deletion. Repeated requests and cleanup passes are idempotent. Trade creation remains out of scope.

**Rationale**: A run may be preparing while the worker owns a lease, and its staged or final candle objects live outside MongoDB. A durable lifecycle marker prevents a late worker from publishing a deleted run and allows interrupted cleanup to resume. The dedicated account's `backtest_run_id` and each trade's `trade_account_id` provide a narrow cascade boundary that preserves other runs and Real records. Reusing the existing trade deletion path avoids leaving trade-owned media or other dependent records behind.

**Alternatives considered**: Delete all resources synchronously in the HTTP request. Rejected because a process or object-store failure can interrupt the cascade, and an in-flight preparation worker still needs a cancellation fence. Introduce a second standalone deletion queue. Rejected because the run's durable `deleting` status already serves as the work marker and avoids duplicate lifecycle state. Soft-delete with a restore action. Rejected because the requested behavior is permanent removal of the run, account, and linked trades.

Sources: [`BacktestRun` ownership and worker cleanup](../../backend/app/backtests/repository.py), [preparation-worker terminal cleanup](../../backend/app/backtests/worker.py), [trade deletion cascade](../../backend/app/trades/service.py).

### 11. Keep one calendar month of chart context outside the replay window

**Decision**: Calculate the context boundary as one calendar month before the user-selected local start date in the configured display timezone, clamping to the final valid day of the preceding month, then convert the context and selected replay boundaries to UTC. Fetch and retain every available one-minute source candle from that context boundary through the selected end in the run's immutable snapshot. Store the first snapshot index at or after the selected replay start separately. Use only selected-period candles for readiness, replay cursor movement, progress, gap reporting, and completion; show available earlier candles as chart history at the initial cursor. Missing or partial context is valid, but context-only data does not make a run ready.

**Rationale**: The user's requested date range remains the period being replayed and continues to define the inclusive one-year limit, account label, and run-list coverage. Prior candles supply visual context without shifting the replay clock or making earlier candles playable. Calendar-month subtraction follows the selected local date and has deterministic end-of-month behavior; UTC conversion then preserves the existing instant and candle-boundary contracts. Because the source data can begin later than the requested context boundary, warm-up availability is best-effort and must not be a new preparation-success condition.

**Alternatives considered**: Treat the preceding 30 days as warm-up. Rejected because it does not consistently mean one calendar month and can misalign on month boundaries. Move the replay cursor to the earliest candle in the expanded snapshot. Rejected because it starts playback before the date the user selected. Fail preparation unless a full month is available. Rejected because the user explicitly requested that available partial history be used.

## Implementation-Time Validations

- The requested CandleKit 0.1.1 version is not published. The 0.1.0 tarball's declarations confirm ChartView, ReplayControls, DrawingToolbar, ReplayDataSource, SyncEngine, DrawingEngine export/import, and configurable speed choices; no replay-aware drawing visibility API is present.
- Lock a single Lightweight Charts 5.x version and confirm the existing TradeDetail chart still builds and retains its marker, price-line, and theme behavior.
- Resolve PyArrow >=25 from the Dukascopy package against the backend’s other locked dependencies.
- Pin the sibling downloader at Git revision `e8dd0b7fc01631e5d519b92b6eea34ed2f156957`. Its `fetch_instrument_codes` catalog API and per-UTC-date `run_downloads(instrument, "COMB", date, 1, ...)` API are present. This revision requires PyArrow >=25.0, so the backend's 18.1.0 pin must be raised and locked consistently.
- Exercise worker lease expiry and recovery after API and worker restarts; verify completed UTC-date staging across the extended context-plus-replay range is reused and the ready transition writes the first replay-period candle cursor with the ready status.
- Verify the run-list polling stops when no run is preparing or deleting and makes no more than five seconds elapse between refreshes while either state continues.
- Verify confirmed deletion fences an in-flight preparation lease, resumes after API/worker restart, and treats pending hiding/202 responses as incomplete. On completion, assert that only the target run's trades and trade-owned data, account, run-owned MongoDB records, and every object in its MinIO prefix (including unreferenced objects) are physically removed, that the prefix is empty, and that no deletion marker remains.
- Verify sync mapping on tabs with different chart intervals and empty/gap dates.
- Verify the pinned CandleKit 0.1.0 workspace adapter with the exact locked `flexlayout-react` peer, custom JanusEdge chart panel registration, layout serialization, split/move/reorder/resize operations, and cleanup/re-registration of replay, sync, and drawing subscriptions when a panel moves.
- Verify one-pane 1m initialization, legacy flat-tab migration into visible sibling panes, and revision-conflict handling on concurrent layout saves. The current upstream example's `ReplayPanel` import must not be assumed available in 0.1.0.
- Verify drawing load completes before edits are accepted; save and restore state by authenticated user, run, and timeframe.
- Inspect the pinned drawing implementation for replay-aware visibility; if absent, verify the anchor-only filter hides drawings with future anchors and restores them when all anchors are reached, without creation/edit-time filtering.
- Verify one-calendar-month warm-up boundary calculation in the selected timezone, end-of-month clamping, partial/empty context handling, selected-period-only readiness and replay-cursor bounds, and chart rendering of available pre-start candles without allowing them to be replayed.
- Check CandleKit MIT and Lightweight Charts attribution requirements against the repository’s existing notices before release.



