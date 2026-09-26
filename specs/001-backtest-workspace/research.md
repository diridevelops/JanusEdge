# Research: Backtest Candle Replay

Research for the implementation plan was based on the active feature specification, the JanusEdge source tree, the CandleKit repository documentation, and the sibling Dukascopy downloader package documentation. No application implementation or dependency installation was performed.

## Decisions

### 1. Use CandleKit’s React integration for the Backtest chart surface

**Decision**: Use the CandleKit 0.1.1 React entry for ChartView and its replay and drawing overlays, including ReplayControls and DrawingToolbar. Use CandleKit’s replay and synchronization engines through a narrow JanusEdge adapter.

**Rationale**: CandleKit exposes candlestick charting, a deterministic replay controller, multi-chart synchronization, and drawing tools/state through one toolkit. The README documents the React entry, ChartView, ReplayControls, DrawingToolbar, and DrawingController. The user specifically selected CandleKit for the Backtest charting, replay, synchronization, and drawing-state responsibilities. Bind the specified 1x/5x/20x playback choices to its replay controller; adapt the React control composition if the package component does not expose those exact choices.

**Alternatives considered**: Keep building directly on Lightweight Charts and create custom replay, drawing, and sync systems. Rejected because it would duplicate the responsibilities the user assigned to CandleKit. Continue using the existing Real trade chart unchanged at the feature level; only adapt its direct Lightweight Charts API use as required by the shared dependency upgrade.

Sources: [CandleKit README](https://github.com/rohanbeingsocial/candlekit-charts/blob/main/README.md), [CandleKit API reference](https://github.com/rohanbeingsocial/candlekit-charts/blob/main/docs/api-reference.md).

### 2. Align JanusEdge on Lightweight Charts 5.x and pin CandleKit

**Decision**: Add CandleKit at exact version 0.1.1 and use one locked Lightweight Charts 5.x dependency across the frontend. Adapt the existing direct Lightweight Charts trade-detail wrapper to the 5.x API without changing its user-facing behavior.

**Rationale**: CandleKit package metadata declares Lightweight Charts 5.x as a peer dependency. JanusEdge currently depends on 4.2.1 and its Real trade chart uses the 4.x addCandlestickSeries API. Loading two major versions in one application would add bundle and type-resolution complexity; one shared version with a small compatibility migration is simpler.

CandleKit’s own README describes the project as early-stage and advises pinning the version. The package metadata lists version 0.1.1, MIT license, React 18/19 peer support, and optional peers for unrelated workspace/indicator features. The main-branch metadata does not establish that every currently documented API is identical to the released npm artifact, so the pinned artifact must be inspected before implementation relies on those APIs.

**Alternatives considered**: Keep Lightweight Charts 4.x in Real mode and install a second 5.x copy for Backtest. Rejected because it creates duplicate runtimes and leaves package-manager peer resolution and type compatibility more complex. Float CandleKit to latest. Rejected because the upstream project explicitly recommends pinning.

Sources: [CandleKit package metadata](https://github.com/rohanbeingsocial/candlekit-charts/blob/main/package.json), [CandleKit README and maturity/license notes](https://github.com/rohanbeingsocial/candlekit-charts/blob/main/README.md).

### 3. Use an immutable run-owned one-minute snapshot as replay truth

**Decision**: Keep Dukascopy source candles separate from JanusEdge’s imported-tick market-data store. Save each ready run’s exact selection in a user- and run-scoped immutable MinIO Parquet object and store its coverage, gaps, checksum, and source metadata in MongoDB.

**Rationale**: The existing /market-data/ohlc route reads candles derived from locally imported ticks. It does not download Dukascopy data or guarantee an immutable replay selection. A run-owned snapshot prevents later refreshes from changing historical replay. The sibling dukascopy-market-data package documents both an importable Python API and Parquet output, so the Flask service can use the API directly and stage output without launching a subprocess.

The sibling package requires PyArrow 25 or later, while JanusEdge currently pins PyArrow 18.1.0. Dependency resolution must reconcile that difference and validate the current Pandas combination.

**Alternatives considered**: Reuse /market-data/ohlc or its shared cache. Rejected because those datasets are generated from imported tick files and can be rebuilt. Download candles in the browser. Rejected because user credentials, persistence, ownership checks, progress, and immutable snapshots belong at the authenticated backend boundary. Duplicate the downloader implementation inside JanusEdge. Rejected because a maintained package API already exists in the adjacent project.

Sources: [JanusEdge market-data route](../../backend/app/market_data/routes.py), [sibling downloader README](../../../dukascopy-market-data-cli/README.md), [sibling downloader project metadata](../../../dukascopy-market-data-cli/pyproject.toml).

### 4. Let CandleKit drive replay while JanusEdge enforces cursor-bounded display

**Decision**: Implement CandleKit’s ReplayDataSource over the immutable run snapshot, returning only requested UTC-day data and available-date lists. Keep one ReplayController per active run. Send ordinary forward-bar events to each chart through incremental updates. Rebuild visible chart data from the cursor after seek or step-back.

**Rationale**: CandleKit documents a day-oriented replay data source, deterministic cursor, playback controls, per-bar callbacks, and efficient updateBar handling for normal playback. A shared controller naturally preserves the specification’s one-cursor-across-tabs behavior. JanusEdge must own the session calendar and gaps. It must not initialize higher-timeframe charts with pre-aggregated bars that include candles beyond the current cursor.

Each higher-timeframe candle is aggregated from the one-minute source events seen so far, using the existing UTC-aligned, left-closed/right-open boundaries. Chart time values remain UTC epoch milliseconds. Display timezone is applied by formatting, not by shifting times before aggregation or drawing.

**Alternatives considered**: Give each chart tab an independent replay controller. Rejected because tabs could diverge. Feed full higher-timeframe history and hide bars by styling. Rejected because active-bar high, low, and close values could reveal future source candles.

Sources: [CandleKit replay documentation](https://github.com/rohanbeingsocial/candlekit-charts/blob/main/docs/replay-system.md), [CandleKit architecture](https://github.com/rohanbeingsocial/candlekit-charts/blob/main/ARCHITECTURE.md).

### 5. Use CandleKit SyncEngine with a time-domain adapter

**Decision**: Use CandleKit SyncEngine for crosshair and visible-range event routing. Convert the emitting chart’s logical indexes to UTC time values and map those timestamps into the receiving chart’s logical range. Classify pan and zoom events so their independently controlled options remain separate. Keep replay synchronization in the one shared ReplayController, outside those optional switches.

**Rationale**: CandleKit’s SyncEngine is framework-independent and requires the host to attach chart members and route events. Its documented time-range payload uses logical bar indexes. Different intervals have different logical spacing, so broadcasting those indexes directly would misalign tabs. The JanusEdge adapter must preserve the app’s absolute-time synchronization contract.

**Alternatives considered**: Broadcast logical range indexes without conversion. Rejected because a position such as bar 100 on a one-minute chart does not represent the same time as bar 100 on a one-hour chart. Write an unrelated custom sync engine. Rejected because the user selected CandleKit for synchronization; only the time conversion and independent option behavior belong in the adapter.

Sources: [CandleKit sync contracts](https://github.com/rohanbeingsocial/candlekit-charts/blob/main/src/sync/types.ts), [CandleKit architecture](https://github.com/rohanbeingsocial/candlekit-charts/blob/main/ARCHITECTURE.md).

### 6. Persist CandleKit drawings through JanusEdge’s authenticated API

**Decision**: Use CandleKit DrawingController and DrawingEngine for live state and toolbar behavior. Load and save the serialized export/import payload through an authenticated API document keyed by user, run, and timeframe. Do not use the built-in local storage key as the durable source of truth.

**Rationale**: CandleKit documents DrawingEngine export/import and drawing-change notifications. Its custom key-value store is synchronous, while JanusEdge API writes are asynchronous. An app adapter can hydrate before enabling edits and debounce backend writes after changes. This keeps drawing state in the same per-user context as the run and allows it to survive browser reloads and user devices.

The current CandleKit repository documentation describes replay as cursor-bounded bar data and drawings as a separate plugin with data-space anchors and persistence. Its drawing guide does not document replay-cursor visibility or drawing-version history. The pinned 0.1.1 artifact must be inspected during integration; preserve any replay-aware visibility behavior it actually provides. If none exists, apply the specified anchor-only filter and do not add drawing creation/edit-time history. This fallback means a drawing created later but anchored entirely in the past may remain visible after rewind, an accepted v1 trade-off.

**Alternatives considered**: Use CandleKit localStorage as the only persistence. Rejected because it is browser-local and does not follow authenticated user/run ownership. Pass JanusEdge’s asynchronous API directly as CandleKit’s KVStore. Rejected because the documented KVStore contract is synchronous. Keep drawings only in memory. Rejected because leaving and reopening a replay would lose the drawing state.

Sources: [CandleKit drawing guide](https://github.com/rohanbeingsocial/candlekit-charts/blob/main/docs/drawing-tools.md), [CandleKit drawing persistence interface](https://github.com/rohanbeingsocial/candlekit-charts/blob/main/src/drawing/persistence.ts), [CandleKit architecture](https://github.com/rohanbeingsocial/candlekit-charts/blob/main/ARCHITECTURE.md).

### 7. Theme CandleKit through the existing app theme

**Decision**: Pass ThemeContext’s light/dark choice and mapped chart palette into CandleKit, import its React overlay stylesheet once, then apply scoped CSS overrides under the Backtest chart subtree using JanusEdge tokens.

**Rationale**: The frontend already uses React 19, Tailwind, a shared ThemeContext, and brand/profit/loss colors. CandleKit supports custom themes and styles its React overlays with .ck-* CSS variables. This uses the app’s existing visual language rather than exposing a separate CandleKit theme toggle.

**Alternatives considered**: Keep CandleKit’s default theme and overlay styles. Rejected because it would not match the user’s request. Globally rewrite the library stylesheet. Rejected because a subtree-scoped override limits side effects and keeps vendor styles auditable.

Sources: [CandleKit architecture](https://github.com/rohanbeingsocial/candlekit-charts/blob/main/ARCHITECTURE.md), [JanusEdge ThemeContext](../../frontend/src/contexts/ThemeContext.tsx), [JanusEdge global styles](../../frontend/src/styles/globals.css).

## Implementation-Time Validations

- Inspect the installed CandleKit 0.1.1 artifact and confirm ChartView, ReplayControls, DrawingToolbar, ReplayDataSource, SyncEngine, and DrawingEngine export/import APIs before using repository-main-only API assumptions.
- Lock a single Lightweight Charts 5.x version and confirm the existing TradeDetail chart still builds and retains its marker, price-line, and theme behavior.
- Resolve PyArrow >=25 from the Dukascopy package against the backend’s other locked dependencies.
- Verify sync mapping on tabs with different chart intervals and empty/gap dates.
- Verify drawing load completes before edits are accepted; save and restore state by authenticated user, run, and timeframe.
- Inspect the pinned drawing implementation for replay-aware visibility; if absent, verify the anchor-only filter hides drawings with future anchors and restores them when all anchors are reached, without creation/edit-time filtering.
- Check CandleKit MIT and Lightweight Charts attribution requirements against the repository’s existing notices before release.



