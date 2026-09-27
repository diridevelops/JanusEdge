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
| status | enum | preparing, ready, or deleting. Failed/no-data runs are reported and deleted per the feature requirements. |
| progress | object | Current preparation stage and a percentage when measurable; otherwise indicates indeterminate progress. |
| account_id | ObjectId | The single associated Backtest account. |
| preparation_job_id | ObjectId/string | The durable worker job associated with this run. |
| snapshot | object | Immutable snapshot metadata described below. Present when ready. |
| coverage | object | First/last available candle, candle count, fully empty dates, and summaries of partial gaps. Present when ready. |
| replay_cursor | object | Saved available-candle index and UTC timestamp. Initialized to index zero and the first available candle timestamp in the same MongoDB update that marks the run ready. |
| deletion_requested_at | UTC timestamp/null | Set when the owner confirms permanent deletion; the deleting state is the durable cleanup marker until associated resources are purged. |
| deletion_requested_by | ObjectId/null | Authenticated owner who confirmed deletion. |
| created_at / updated_at | UTC timestamps | Lifecycle timestamps. |

Invariants:

- Unique ownership and run identity. Every lookup and mutation filters by both user_id and run id.
- One Backtest account per run, enforced by a unique user_id/run_id association.
- One durable BacktestPreparationJob per preparing or ready run, enforced by a unique run_id association. Deletion removes the job during cleanup; after that, the run's `deleting` status remains the durable marker until the rest of the purge completes and the run record is removed last.
- A ready run always references one complete immutable snapshot containing at least one candle.
- The snapshot never changes after the run is ready; refreshes create a new run and snapshot.
- A preparing run may be retried or recovered after interruption without creating a second job, run, or account. Completed UTC-date checkpoints are durable; only an incomplete date may need to be fetched again.
- A deleting run is non-playable and cannot transition to ready. Its status is a temporary durable cleanup marker, not a soft-delete outcome; the run record is removed only after all run-owned resources have been physically purged.
- Once deletion is requested, its account and trades may be excluded from Backtest views while cleanup is pending. This interim hiding is not completion. Cleanup is limited to the account identified by this run and the trades linked to that account.
- Completed deletion leaves no run, account, preparation/replay/workspace/drawing records, linked trades or trade-owned dependent data, or objects under the run's MinIO prefix. The worker verifies the run prefix is empty before removing the run record and its deletion marker.
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

The worker atomically claims queued jobs or jobs with expired leases, renews its lease while working, writes non-empty date candles to MinIO, then persists the date outcome (including empty) in `completed_utc_dates`. On recovery it skips committed dates and may repeat only the current incomplete date. A completed job remains associated with its ready run. No-data and terminal provider failure create a notice, delete the run/account/job, and remove staged data. If the run enters `deleting`, the worker must stop preparation and resume idempotent deletion cleanup instead of publishing a snapshot or ready state.

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
| status | enum | active for a ready/preparing run; deleting while confirmed run cleanup is pending; removed when deletion completes. |

A Backtest account is dedicated to one run and has no Real trades. Trade recording and simulated orders remain unavailable in this version. If Backtest trades are associated with this account, they are exclusively owned by this run for deletion purposes. When account status is `deleting`, the account and its trades may be hidden from Backtest trade-facing queries while cleanup is pending; this is not deletion completion. Deletion physically removes every trade linked by `trade_account_id` and all trade-owned dependent data, then removes the account. On completion, neither the account nor its trades or dependents remain in storage.

## ReplayCursor

The shared playback position used by all chart tabs for one BacktestRun. Store durable position on BacktestRun and instantiate one CandleKit ReplayController per active run in the browser.

| Field | Type | Description |
|---|---|---|
| source_candle_index | integer | Index into the immutable available one-minute candle sequence. |
| time_ms | integer | Timestamp of the selected source candle in UTC epoch milliseconds. |
| revision | integer | Monotonic version to reject stale writes. |
| updated_at | UTC timestamp | Last persisted cursor update. |

Play/pause/speed are live transport state. When the run becomes ready, the persisted cursor is index zero at the first available candle; on reload, restore the saved cursor and start paused. Every tab observes the same CandleKit controller and cursor. Backward seek rebuilds the display from data no later than the selected cursor.

## ReplayChartPanel

Chart-panel metadata embedded in a `ChartWorkspaceLayout`. A panel is a chart tab that belongs to exactly one tab group in the layout tree. It has no independent replay cursor.

| Field | Type | Description |
|---|---|---|
| id | UUID/string | Stable chart id, retained when a tab moves or its group is split. |
| type | enum | `backtest-chart` in v1. |
| interval_minutes | integer | 1 through 1,440; includes the standard intervals listed in the feature specification. |
| title | string, optional | User-visible tab title; defaults to the chart label. |
| chart_options | object, versioned | Supported chart-specific presentation options; must not contain user or run ownership. |

Each chart panel derives bars from source candles already emitted through the replay cursor. A higher-timeframe bar uses the first revealed open, maximum revealed high, minimum revealed low, latest revealed close, and sum of available revealed volume. Gaps stay empty; no synthetic bars are produced. Timestamps remain UTC epoch milliseconds and are formatted for the configured display timezone.

Panel ids are unique in a workspace. Moving a tab changes its tree parent and may unmount/remount its component, but preserves its panel id, interval, drawing scope, and shared replay position.

Follow state is not part of the persisted panel configuration. A newly mounted pane initializes at the latest bar visible through the run's saved replay cursor. Its live follow status is derived from the pane's time-scale scroll position relative to that pane's normal real-time offset; see `ReplayChartFollowState` below.

## ReplayChartFollowState (runtime only)

Transient state for one mounted chart pane. It is derived from that pane's actual chart time scale and cursor-bounded bars and is not written to MongoDB or the chart-workspace API.

| Field | Type | Description |
|---|---|---|
| panel_id | string | Stable id of the chart pane this runtime state belongs to. |
| follows_latest | boolean | Whether the latest revealed chart bar is at the pane's real-time edge. |
| latest_revealed_bar_index | integer/null | Rightmost bar index available from the current replay cursor and selected chart interval. |
| current_scroll_position | number | Time-scale distance from the visible right edge to the latest chart bar. |
| real_time_scroll_position | number | Pane's normal right-edge offset captured when it is snapped to real time. |

Invariants:

- Each mounted pane determines follow status independently; there is no run-level follow toggle or second replay cursor.
- After chart data is ready on first open or remount, the pane scrolls to the latest bar revealed at the current cursor, captures its normal real-time offset, and begins following.
- Follow status is derived by comparing the current scroll position with the captured real-time offset. While following, a replay cursor update keeps the latest currently revealed bar at that offset. A user horizontal navigation that places it away from that offset leaves the pane's selected range unchanged as replay advances; if replay naturally catches up to that offset, the pane is following again.
- Continuous replay updates use coalesced, non-animated repositioning; the initial and user-requested snap may use the chart's animated real-time scroll. A same-interval update to the active higher-timeframe bar does not change the pane's horizontal range or scale.
- The lower-right return-to-latest action and the existing double-click time-axis gesture scroll the pane to its latest revealed bar and restore follow. The action is hidden while the pane is snapped to that bar. Manual navigation back to the real-time offset also restores follow.
- Panning, zooming, and return-to-latest affect only the pane where the action occurs; crosshair synchronization does not alter another pane's viewport.
- Rewind and seek use only bars revealed at the new replay cursor.

## ChartWorkspaceLayout

The durable workspace document for one authenticated user and one ready BacktestRun. MongoDB stores one document in `backtest_chart_workspaces` per `(user_id, run_id)`; all API queries derive user_id from authentication.

| Field | Type | Description |
|---|---|---|
| id | ObjectId/string | Workspace document identity. |
| user_id | ObjectId | Authenticated owner. |
| run_id | ObjectId/string | Owning ready BacktestRun. |
| schema_version | integer | JanusEdge workspace serialization version; v1 is `1`. |
| layout_engine | string | `flexlayout-react` adapter identifier for decoding the saved tree. |
| name | string | Stable workspace name, `default` in v1. |
| tree | object | Serializable dock tree containing split orientation/weights, tab groups, panel order, and each group's active panel. |
| panels | ReplayChartPanel map | Chart-panel configurations indexed by stable chart id. |
| revision | integer | Monotonic revision used for compare-and-swap writes. |
| created_at / updated_at | UTC timestamps | Workspace lifecycle and last successful save. |

Invariants:

- The unique owner key is `(user_id, run_id)`; the run must be ready and owned by that user.
- The tree contains at least one chart panel, references each panel id exactly once, and has no dangling panel metadata. Every panel map entry is present in the tree.
- Panel ids are unique; panel type and schema versions are supported; intervals are whole minutes from 1 through 1,440.
- Split weights are finite and positive, and each split has at least two children. Tab groups have a valid active chart tab. V1 has no fixed maximum tab count.
- Layout edits never create a second chart/replay controller for the run. Every panel observes the run's shared replay cursor.
- A write supplies the revision it read. A matching write persists the replacement and increments revision; a stale write is rejected with the latest revision and cannot silently discard newer layout changes.
- A new run's first workspace has one 1m chart panel. Closing a chart is rejected if it would leave no chart panel.
- The backend layout DTO is mapped by a CandleKit `LayoutPersistence` adapter to CandleKit's `WorkspaceLayout` (`id`, `name`, timestamps, tree, and panel instances); the FlexLayout tree and CandleKit runtime model remain isolated from API ownership and revision fields.

Legacy migration: if no workspace exists and `backtest_chart_tabs` contains flat records, translate them in position order into visible sibling chart panes, retaining each id and interval. Flat records contain no prior split topology or active-tab state. If there are no legacy records, create one 1m chart using the single-chart layout. Persist the initialized workspace before enabling workspace edits; concurrent initializations use revision zero compare-and-swap and the loser reloads the saved document.

## ChartSynchronization

Crosshair synchronization is active by default and shared replay position is always enabled. The replay detail has no Chart sync settings section. CandleKit SyncEngine routes crosshair locations only; the JanusEdge adapter translates them through absolute UTC time before applying them to another interval. Raw logical indexes are never copied directly between timeframes. If a target chart has no candle at the crosshair's UTC time, it uses the nearest available candle at or before that time; if none exists, it shows no synchronized crosshair. Pan and zoom remain local to each pane.

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
- Each preparing or ready BacktestRun has exactly one durable BacktestPreparationJob; completed jobs remain for the lifetime of their ready run. During deletion the job is physically removed as part of cleanup, while the run's `deleting` status remains the durable marker until all remaining resources are purged and the run record is removed last.
- Each BacktestAccount belongs to exactly one BacktestRun and may be referenced by zero or more trades through `trade_account_id`; those trades are removed with the account when that run is deleted.
- Each BacktestRun has one durable ReplayCursor shared by all active chart tabs.
- Each BacktestRun has zero or one ChartWorkspaceLayout before first open and exactly one after initialization, and may have zero or more BacktestPreparationNotices for completed failures/no-data outcomes.
- Each BacktestRun may have zero or more ChartDrawingState documents, one per interval.
- A confirmed deletion moves the run and account to `deleting`; hiding them from normal Backtest views is only an interim state. The run's durable deleting state resumes cleanup after interruption. Cleanup physically removes all account-linked trades and their dependent data, the account, preparation job, replay cursor, chart tabs/workspace, drawings, and every object under the run's MinIO prefix (including staged, snapshot, and unreferenced objects). After verifying no associated documents or MinIO objects remain, remove the run record and its deletion marker last. Repeated deletion and cleanup passes are safe.
- Real accounts and trades are excluded from Backtest queries; Backtest accounts are excluded from Real queries.


