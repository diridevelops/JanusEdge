# Data Model: Backtest Candle Replay

The models below extend the current JanusEdge user, trade-account, market-data, and storage boundaries. Authentication supplies user identity; clients must not select another user by sending a user identifier.

## WorkspaceMode

The current workspace selection for a user.

| Field | Type | Description |
|---|---|---|
| user_id | ObjectId | Owner. |
| active_mode | enum | real or backtest. |
| updated_at | UTC timestamp | Last selection change. |

Real remains the default for existing users and existing records. Every trade-facing query uses the active mode and excludes records from the other mode. Existing trade-account documents without a mode remain Real during migration.

## BacktestRun

One user-owned replay request and the saved one-minute candle selection for that request. Store run metadata in MongoDB. The run references its immutable candle artifact in MinIO.

| Field | Type | Description |
|---|---|---|
| id | ObjectId/string | Run identity. |
| user_id | ObjectId | Authenticated owner. |
| instrument | string | Exact supported Dukascopy instrument code. |
| requested_start_date | local date | Inclusive user-selected calendar date; part of the one-year maximum in the configured display timezone. |
| requested_end_date | local date | Inclusive user-selected calendar date; must precede the start date's one-year anniversary. |
| display_timezone | IANA timezone | Timezone used to convert selected date boundaries to UTC. |
| start_utc_ms | integer | Inclusive UTC start instant. |
| end_utc_ms | integer | Exclusive UTC end instant. |
| source | enum | dukascopy. |
| source_side | enum | COMB, represented as component-wise midpoint OHLC. |
| source_interval_minutes | integer | Fixed at 1. |
| status | enum | preparing or ready. Failed/no-data runs are reported and deleted per the feature requirements. |
| progress | object | Current preparation stage and a percentage when measurable; otherwise indicates indeterminate progress. |
| account_id | ObjectId | The single associated Backtest account. |
| preparation_job_id | ObjectId/string | The durable worker job associated with this run. |
| snapshot | object | Immutable snapshot metadata described below. Present when ready. |
| coverage | object | First/last available candle, candle count, fully empty dates, and summaries of partial gaps. Present when ready. |
| replay_cursor | object | Saved available-candle index and UTC timestamp. Initialized to index zero and the first available candle timestamp in the same MongoDB update that marks the run ready. |
| created_at / updated_at | UTC timestamps | Lifecycle timestamps. |

Invariants:

- Unique ownership and run identity. Every lookup and mutation filters by both user_id and run id.
- One Backtest account per run, enforced by a unique user_id/run_id association.
- One durable BacktestPreparationJob per active or ready run, enforced by a unique run_id association.
- A ready run always references one complete immutable snapshot containing at least one candle.
- The snapshot never changes after the run is ready; refreshes create a new run and snapshot.
- A preparing run may be retried or recovered after interruption without creating a second job, run, or account. Completed UTC-date checkpoints are durable; only an incomplete date may need to be fetched again.
- The run's status-ready transition and initial cursor (source_candle_index zero, first available timestamp, revision zero) are persisted together in the run document.
- Cursor position is an index into the immutable ordered list of available one-minute candles. It may not point to an unavailable or later-than-current candle.
- The current position is persisted as the newest requested cursor, with server-side versioning or ordered writes preventing an older in-flight update from replacing a newer one.

## BacktestPreparationJob

Durable MongoDB job claimed by the separate preparation worker. MongoDB is both the job store and lease coordinator; v1 adds no external queue service. Public stage and percentage are stored on BacktestRun, while this record owns recovery state and date checkpoints.

| Field | Type | Description |
|---|---|---|
| id | ObjectId/string | Job identity. |
| user_id | ObjectId | Authenticated owner; matches the associated run. |
| run_id | ObjectId/string | Unique associated run. |
| state | enum | queued, running, or completed. |
| lease_owner | string/null | Worker identity currently holding the claim. |
| lease_expires_at | UTC timestamp/null | Expiry after which another worker may atomically reclaim the job. |
| attempt_count | integer | Number of worker claims. |
| completed_utc_dates | array | Ordered checkpoints; each item records a UTC date, empty/data outcome, and staged MinIO object key when data exists. |
| staging_prefix | string | Run-scoped MinIO prefix containing completed per-date results until final snapshot assembly. |
| created_at / updated_at | UTC timestamps | Job lifecycle and checkpoint update times. |

The worker atomically claims queued jobs or jobs with expired leases, renews its lease while working, writes non-empty date candles to MinIO, then persists the date outcome (including empty) in `completed_utc_dates`. On recovery it skips committed dates and may repeat only the current incomplete date. A completed job remains associated with its ready run. No-data and terminal provider failure create a notice, delete the run/account/job, and remove staged data.

## BacktestCandleSnapshot

Immutable one-minute OHLCV selection for one run, stored as Parquet in MinIO.

| Field | Type | Description |
|---|---|---|
| run_id | ObjectId/string | Owning run. |
| object_key | string | Unique MinIO key under the user/run namespace. |
| sha256 | string | Content checksum used to verify the selected data is unchanged. |
| instrument | string | Exact source instrument. |
| source_side | enum | COMB. |
| price_mode | enum | combined_midpoint. |
| volume_semantics | enum | two_sided_quote_liquidity, not executed trade volume. |
| interval_minutes | integer | Fixed at 1. |
| first_time_ms / last_time_ms | integers | UTC epoch-millisecond timestamps of available candles. |
| candle_count | integer | Number of available source candles. |
| available_utc_dates | date array/index | UTC dates containing one or more source candles for CandleKit’s day-oriented data source. |
| gap_dates | date array | Requested dates with no candles; no rows are synthesized. |
| partial_gap_summary | object | Summaries of missing one-minute source intervals between available candles within populated dates. |
| fetched_at | UTC timestamp | Source acquisition completion time. |

Each candle has a UTC timestamp in epoch milliseconds, open, high, low, close, and optional volume. For COMB, each midpoint OHLC field is the arithmetic mean of the corresponding BID and ASK field. The source does not synchronize the intraminute extrema, so midpoint high/low are estimates. Volume is the sum of bid and ask quoted liquidity and is not executed trade volume. Time rows are sorted, unique, and constrained to the requested UTC range. MinIO objects are addressed by user and run; shared market-data refresh operations never overwrite them.

## BacktestAccount

The account selector record associated with exactly one BacktestRun. Store this as a trade_accounts record extended with Backtest metadata rather than as a real account.

| Field | Type | Description |
|---|---|---|
| id | ObjectId/string | Account identity. |
| user_id | ObjectId | Authenticated owner. |
| workspace_mode | enum | backtest. Existing records default to real. |
| backtest_run_id | ObjectId/string | Unique associated run. |
| account_name | string | Stable system-generated value. |
| display_name | string | Instrument and selected date range, with a short unique suffix when needed. |
| status | enum | active for a ready/preparing run; removed when the run is deleted after failure/no-data. |

A Backtest account has no real trades. Trade recording and simulated orders remain unavailable in this version. The account is a way to identify the run in Backtest trade-facing screens.

## ReplayCursor

The shared playback position used by all chart tabs for one BacktestRun. Store durable position on BacktestRun and instantiate one CandleKit ReplayController per active run in the browser.

| Field | Type | Description |
|---|---|---|
| source_candle_index | integer | Index into the immutable available one-minute candle sequence. |
| time_ms | integer | Timestamp of the selected source candle in UTC epoch milliseconds. |
| revision | integer | Monotonic version to reject stale writes. |
| updated_at | UTC timestamp | Last persisted cursor update. |

Play/pause/speed are live transport state. When the run becomes ready, the persisted cursor is index zero at the first available candle; on reload, restore the saved cursor and start paused. Every tab observes the same CandleKit controller and cursor. Backward seek rebuilds the display from data no later than the selected cursor.

## ReplayChartTab

Persisted chart-tab configuration for one BacktestRun. Tabs are user-owned, restored across navigation/reload, and have no fixed v1 maximum.

| Field | Type | Description |
|---|---|---|
| id | UUID/string | Stable chart-tab identity within the run. |
| user_id | ObjectId | Authenticated owner. |
| run_id | ObjectId/string | Shared run. |
| position | integer | Display order among the run's tabs. |
| interval_minutes | integer | 1 through 1,440; includes the standard intervals listed in the feature specification. |
| candle_grouping | enum | Fixed UTC-aligned, start-inclusive/end-exclusive. |
| created_at / updated_at | UTC timestamps | Tab configuration lifecycle. |

Each tab derives bars from source candles already emitted through the replay cursor. A higher-timeframe bar uses the first revealed open, maximum revealed high, minimum revealed low, latest revealed close, and sum of available revealed volume. Gaps stay empty; no synthetic bars are produced. Timestamps remain UTC epoch milliseconds and are formatted for the configured display timezone.

The unique ownership key includes user_id/run_id/id. Interval changes update the existing tab configuration. All changes are scoped to the authenticated owner; tabs do not create independent replay cursors.

## ChartSyncSettings

Page-level transient settings for the open run detail.

| Field | Type | Description |
|---|---|---|
| sync_crosshair | boolean | Defaults to true. |
| sync_pan | boolean | Defaults to true. |
| sync_zoom | boolean | Defaults to true. |
| replay_shared | constant | Always true; there is no control to disable shared replay. |

CandleKit SyncEngine routes the visual sync events. The JanusEdge adapter translates visible logical ranges and crosshair locations through absolute UTC times before applying them to a chart at another interval. Raw logical indexes are never copied directly between timeframes.

If a target chart has no candle at the crosshair's UTC time, it uses the nearest available candle at or before that time; if none exists, it shows no synchronized crosshair. Pan and zoom preserve the same UTC bounds and round outward to the target chart's interval boundaries.

## ChartDrawingState

Persisted CandleKit drawing model for one authenticated user, run, and chart interval. Store the exported drawing JSON in MongoDB, separate from real trade notes or annotations.

| Field | Type | Description |
|---|---|---|
| id | ObjectId/string | Drawing document identity. |
| user_id | ObjectId | Authenticated owner. |
| run_id | ObjectId/string | Owning BacktestRun. |
| interval_minutes | integer | Chart interval represented by these drawings. |
| candlekit_version | string | CandleKit artifact version used to serialize the payload. |
| schema_version | integer | JanusEdge wrapper/schema version for migration handling. |
| serialized_state | string | Opaque JSON string returned by CandleKit DrawingEngine export. |
| revision | integer | Monotonic version for write ordering/conflict detection. |
| updated_at | UTC timestamp | Last successful save. |

The unique key is user_id/run_id/interval_minutes. All tabs with the same run and interval load the same drawing set; different intervals have independent drawing state. The standard v1 drawing tool set supports creating, selecting, repositioning, editing, and removing drawings. The frontend must finish loading and import before enabling drawing edits. DrawingEngine change notifications trigger debounced saves; edits and removals survive reloads. Pause, seek, and route exit flush any pending save. Preserve replay-aware drawing visibility if provided by the pinned CandleKit artifact; otherwise filter a drawing while any of its time anchors is after the replay cursor and show it again when all anchors are at or before the cursor. This fallback does not use creation or edit time and does not mutate the persisted payload, so a later-created drawing anchored entirely in the past may remain visible after rewind. CandleKit’s synchronous local KVStore is not used as the durable source of truth.

## BacktestPreparationNotice

User-scoped result message for a failed or no-data preparation. It is separate from BacktestRun so the run and account can be deleted immediately while the user can still read and dismiss the result.

| Field | Type | Description |
|---|---|---|
| id | ObjectId/string | Notice identity. |
| user_id | ObjectId | Authenticated owner. |
| instrument | string | Instrument that was requested. |
| requested_start_date / requested_end_date | local dates | Selected inclusive date range. |
| outcome | enum | no_data or failed. |
| next_action | enum | edit_range or start_new_run. |
| created_at | UTC timestamp | Notice creation time. |

Notices are visible on the run-list page until dismissed and do not cause failed/no-data runs or accounts to remain in the run list.

## Relationships

- One user owns many BacktestRuns.
- Each BacktestRun has exactly one BacktestAccount and one immutable BacktestCandleSnapshot.
- Each preparing or ready BacktestRun has exactly one durable BacktestPreparationJob; completed jobs remain for the lifetime of their ready run.
- Each BacktestRun has one durable ReplayCursor shared by all active chart tabs.
- Each BacktestRun has zero or more persisted ReplayChartTab configurations and may have zero or more BacktestPreparationNotices for completed failures/no-data outcomes.
- Each BacktestRun may have zero or more ChartDrawingState documents, one per interval.
- Real accounts and trades are excluded from Backtest queries; Backtest accounts are excluded from Real queries.


