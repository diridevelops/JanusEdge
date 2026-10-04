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

## Configured Manual Trade Instrument and Conversion Snapshot

An ordinary Real manual `Trade` created from a Settings mapping retains the canonical configured `symbol` and the user's entered `raw_symbol`. The saved calculation snapshot includes `base_currency`, `quote_currency`, `pip_size`, `price_precision`, `contract_size`, `pip_value_per_standard_lot`, `tick_size`, `min_lots`, and `lot_increment`, together with `native_pnl`, `native_pnl_currency`, `quote_to_usd_rate`, and `quote_currency_unit_scale`. Conversion provenance is stored in `instrument_mapping_source`, `conversion_rate_source` (`identity`, `historical`, or `manual`), `conversion_rate_time`, and `conversion_route`. Historical conversion uses completed one-minute route candles no later than exit time, searched on the event UTC date and preceding seven UTC dates. The saved values preserve the Settings sizing rules and rate used at creation if mappings later change.

## BacktestRun

One user-owned replay request and its metadata-only manifest of immutable shared candle references. Store run metadata in MongoDB; candle bytes remain in the user-scoped source cache or imported manual dataset.

| Field | Type | Description |
|---|---|---|
| id | ObjectId/string | Run identity. |
| user_id | ObjectId | Authenticated owner. |
| instrument | string | Canonical Dukascopy catalog instrument or configured Settings instrument. |
| instrument_metadata | object | Immutable calculation contract captured from current JanusEdge instrument mapping at run creation: instrument type, base/quote currencies, pip size, price precision, and contract size (100,000 base units per standard lot when no pair-specific override exists). |
| requested_start_date | local date/null | Inclusive manual or worker-selected calendar date; null while random selection is pending. |
| requested_end_date | local date/null | Inclusive manual or worker-selected calendar date; null while random selection is pending. |
| period_selection | enum | `manual` or `random`. |
| period_months | integer/null | Random duration in calendar months: 1, 3, 6, or 12; null for manual runs. |
| blind_mode | boolean | Immutable run-creation option; defaults to false for existing and new non-blind runs. True requires random period selection. |
| initial_balance_usd | decimal | Starting simulation balance in USD; defaults to 10,000 and is fixed for the run. Current balance is initial balance plus the committed net cash effect of fills, with each execution cost counted once and partial exits reflected when committed; unrealized P&L on open quantity is excluded. |
| risk_percent | decimal | Per-entry risk budget as a percentage of current balance; defaults to 1.0. USD budget is `current_balance_usd * risk_percent / 100`. Used for the default one-standard-lot stop distance and optional auto-sizing. |
| normalized_reference_price | number/null | For a ready blind run, the open of the first available candle at or after the replay start; null for non-blind or unresolved runs. |
| selection_as_of_date | local date/null | Fixed “yesterday” cutoff captured in the configured display timezone when a random request is accepted. |
| display_timezone | IANA timezone | Timezone used for Dukascopy candidate dates, Dukascopy warm-up calculation, and presentation; Manual import date calculations use HistData's fixed UTC−5 calendar. |
| warmup_days | integer | Nonnegative shared-form setting for the number of local calendar days of source context requested before replay start; defaults to 0. |
| context_start_date | local/source date | `requested_start_date - warmup_days`, using the configured display timezone for Dukascopy and HistData's fixed UTC−5 calendar for Manual import. |
| context_start_utc_ms | integer | Inclusive UTC instant at the start of `context_start_date`; earliest requested source-data boundary. |
| start_utc_ms | integer | Inclusive UTC start instant of the user-selected replay period. |
| end_utc_ms | integer | Exclusive UTC end instant of the user-selected replay period. |
| source | enum | `dukascopy` or `manual`. |
| source_side | enum | Dukascopy: COMB represented as component-wise midpoint OHLC. Manual: BID. |
| price_mode / volume_semantics | enum | Dukascopy: `combined_midpoint` and two-sided quoted liquidity. Manual: `imported_bid` and source-provided volume. |
| manual_dataset_revision | ObjectId/string/null | Immutable manual dataset revision pinned by a manual-source run. |
| manual_quote_to_usd_fallback | decimal/null | Optional editable USD per quote-currency unit used only if eligible historical conversion data is unavailable; absent for Dukascopy and USD quote currencies. |
| portable_origin | object/null | Stable source user/run identity used to reuse a run and its links on repeated backup restore. |
| source_interval_minutes | integer | Fixed at 1. |
| price_precision / lot_precision | integer | Frozen price/quantity display and validation precision when supplied by the Settings instrument mapping. |
| status | enum | selecting_period, preparing, ready, complete, or deleting. Failed/no-data runs are reported and deleted per the feature requirements. |
| progress | object | Current preparation stage and a percentage when measurable; otherwise indicates indeterminate progress. |
| account_id | ObjectId/null | The single associated Backtest account; null until the selected source period is resolved. |
| preparation_job_id | ObjectId/string | The durable worker job associated with this run. |
| snapshot | object | Backward-compatible API field containing the metadata-only candle manifest described below; present when ready or complete. Contains references, never replay candle bytes. |
| coverage | object | Available candles, fully empty dates, and partial-gap summaries for the selected replay period only. Present when ready or complete. |
| warmup_coverage | object | Available context candles and any empty dates or partial gaps in the requested warm-up window; may be empty and does not affect readiness. Present when ready or complete. |
| replay_cursor | object | Saved current and furthest available-candle indexes/timestamps into the manifest's ordered candle references. Initialized to `snapshot.replay_start_source_index` and the first eligible candle when the run becomes ready. |
| simulation_control | object | Bounded CAS fields: committed operation sequence, control revision, reset generation, whether an order has ever been accepted in the current generation, and nullable pending operation id. It shares the run document with the canonical replay cursor/status so a commit can advance the cursor, sequence, and completion state atomically. Full operation results and simulation entities remain separate documents. |
| deletion_requested_at | UTC timestamp/null | Set when the owner confirms permanent deletion; the deleting state is the durable cleanup marker until associated resources are purged. |
| deletion_requested_by | ObjectId/null | Authenticated owner who confirmed deletion. |
| created_at / updated_at | UTC timestamps | Lifecycle timestamps. |

Invariants:

- Unique ownership and run identity. Every lookup and mutation filters by both user_id and run id.
- One Backtest account per resolved run, enforced by a unique user_id/run_id association. Random selection does not create an account until a candidate start date with candles is found.
- One durable BacktestPreparationJob per selecting-period or preparing run, enforced by a unique run_id association. A completed job may remain with a ready or complete run, but it is transient and is not exported in a Settings backup. Cache recovery status, lease, and progress are durable on the run and reclaimed after worker restart. Deletion removes only run-owned job/state; source cache entries and manual revisions remain.
- A random run remains in `selecting_period` with null dates and account until the worker finds a candle-bearing candidate and commits its final dates.
- A blind run is immutable, requires `period_selection=random`, and retains raw candle/run values in storage and API responses; only rendered Backtest views apply the masking and normalization rules.
- Pip size, price precision, contract size, base currency, and quote currency used by simulation are copied into the run and never re-read from mutable symbol mappings during replay.
- A ready blind run has one immutable `normalized_reference_price`, taken from the open of its first available replay-period candle. Warm-up and every interval use that same reference. A zero or non-finite reference prevents readiness and follows terminal failure cleanup; a negative reference uses the exact specified ratio even though it reverses normalized direction, with transformed candle highs/lows reordered to preserve a valid range.
- Blind account labels contain the instrument and “blind”, omit dates, and use a short unique suffix when needed. Other runs retain their instrument/date-range labels.
- The random selection cutoff is immutable across worker retries. Candidate starts are local dates from 2005-01-01 through the latest date whose clamped duration end is no later than the captured cutoff.
- The selected inclusive end is the day before adding the configured calendar months with destination-month clamping. A probe verifies candles on the start date only; later selected-period gaps and empty dates continue through normal coverage and readiness rules.
- A ready run's manifest references every available source day spanning the requested context and replay bounds and contains at least one candle in the selected replay period. Warm-up candles alone do not satisfy readiness.
- `context_start_utc_ms` is calculated from `requested_start_date - warmup_days` in the source's date convention, before conversion to UTC. The selected replay date range and one-year validation do not include this additional context.
- The manifest and its cache-version/manual-revision references never change after readiness. New Dukascopy cache versions or manual imports do not retarget an existing run. Explicit recovery may bind refreshed contents for a missing reference; it preserves committed simulation state and discloses that source history may differ.
- A selecting-period or preparing run may be retried or recovered after interruption without creating a second job, run, or account. Random year order, tried dates, and a pending probe are durable; completed empty probes are not counted again. Completed preparation UTC-date checkpoints are durable; only an incomplete date may need to be fetched again.
- A deleting run is non-playable and cannot transition to ready. Its status is a temporary durable cleanup marker, not a soft-delete outcome; the run record is removed only after all run-owned resources have been physically purged.
- Once deletion is requested, its account and trades may be excluded from Backtest views while cleanup is pending. This interim hiding is not completion. Cleanup is limited to the account identified by this run and the trades linked to that account.
- Completed deletion leaves no run, account, run-owned preparation/replay/workspace/drawing/simulation records, linked trades or trade-owned dependent data. Shared Dukascopy cache objects and manual dataset revision data remain available.
- The run's status-ready transition, `snapshot.replay_start_source_index`, and initial cursor (index of the first available source candle at or after `start_utc_ms`, its timestamp, revision zero) are persisted together in the run document.
- Cursor position is an index into the manifest's ordered list of available one-minute candles, including warm-up candles. It may not point before `snapshot.replay_start_source_index` or after the persisted furthest reached index. Recovery rebuilds indexes and maps saved times to the latest available candle at or before each saved timestamp.
- The current position is persisted as the newest requested cursor, with server-side versioning or ordered writes preventing an older in-flight update from replacing a newer one.
- All replay-cursor movement, order mutations, cancellations, cost-profile changes, and reset use the same run-level CAS operation gate. Each accepted action has a unique operation id and monotonically increasing sequence; the operation record and deterministic effects are persisted before the run's committed sequence advances. Orders, positions, and cost profiles are versioned records; readers select the latest version at or below the run's committed sequence and current reset generation. Do not overwrite the prior committed version while a mutation is pending. Recovery resumes an operation marked pending and retries return its original result.
- `complete` is reached only after processing the final available replay-period candle, canceling pending entry orders, and closing all open exposure at that candle's close with costs. A completed run is inspectable but cannot accept orders or cursor movement. Reset atomically starts a new generation and returns to the first eligible replay candle; old-generation records become invisible immediately and are physically purged idempotently before the pending reset gate is cleared. The latest cost settings remain as run configuration.
- Once any simulated order has been accepted in the current generation, a backward step/seek is rejected until the owner confirms reset. Before the first accepted order, the user may seek backward as replay navigation permits.

## BacktestPreparationJob

Durable MongoDB job claimed by the separate preparation worker. MongoDB is both the job store and lease coordinator; v1 adds no external queue service. Public stage and percentage are stored on BacktestRun, while this record owns recovery state and date checkpoints.

| Field | Type | Description |
|---|---|---|
| id | ObjectId/string | Job identity. |
| user_id | ObjectId | Authenticated owner; matches the associated run. |
| run_id | ObjectId/string | Unique associated run. |
| state | enum | queued, running, completed, or cancelled. |
| lease_owner | string/null | Worker identity currently holding the claim. |
| lease_expires_at | UTC timestamp/null | Expiry after which another worker may atomically reclaim the job. |
| attempt_count | integer | Number of worker claims. |
| completed_utc_dates | array | Ordered checkpoints; each records a UTC date, empty/data outcome, and committed shared-cache reference when candles exist. |
| selection | object/null | Random-selection mode, fixed cutoff, eligible date bounds, remaining years, current year, tried dates, pending probe, selected dates, and stable account id. Present until random selection is committed. |
| manual_dataset_revision | ObjectId/string/null | Source revision pinned for a manual-source run. |
| created_at / updated_at | UTC timestamps | Job lifecycle and checkpoint update times. |

The worker atomically claims queued jobs or jobs with expired leases and renews its lease while working. A random Dukascopy job probes candidate days as described in the feature contract. Normal preparation calls the per-day cache service, which reuses hit and empty entries and coordinates misses across workers, then checkpoints the reference/outcome; it does not write per-run staging data. Checkpoints cover the UTC dates intersecting `[context_start_utc_ms, end_utc_ms)`, including partial or empty warm-up dates. Non-USD Dukascopy quote currencies reference the required direct/inverse conversion series from the same shared cache. Manual jobs read only the run-pinned manual revision. On recovery, preparation resumes from durable selection/date checkpoints. A completed job remains associated with a ready or complete run. No-data and terminal provider failure create a notice and remove run/account/job state. If the run enters `deleting`, the worker stops publishing readiness and resumes idempotent cleanup.

## BacktestCandleManifest

Metadata-only, immutable per-run description of the selected one-minute candle sequence. The existing `snapshot` response field continues to serialize this metadata shape; it contains references to shared cache data, not candle bytes.

| Field | Type | Description |
|---|---|---|
| source | enum | `dukascopy` or `manual`. |
| cache_version | string | Dukascopy COMB cache namespace or manual dataset format version. |
| instrument | string | Canonical instrument for the source. |
| source_side / price_mode / volume_semantics | enums | Dukascopy COMB midpoint and two-sided quoted liquidity, or imported bid OHLC and file volume. |
| interval_minutes | integer | Fixed at 1. |
| first_time_ms / last_time_ms | integers | UTC epoch-millisecond timestamps of available candles. |
| context_start_utc_ms / start_utc_ms / end_utc_ms | integers | Inclusive warm-up boundary, inclusive replay start, and exclusive replay end. |
| replay_start_source_index | integer | Index of the first available candle at or after replay start. Rebuilt if cache recovery changes timestamps. |
| candle_count | integer | Number of available source candles. |
| available_utc_dates | date array/index | UTC dates containing one or more candles for the replay data source. |
| gap_dates | date array | Selected replay-period dates with no candles; no rows are synthesized. |
| warmup_gap_dates | date array | Warm-up dates with no candles; these are valid partial or absent context, not a preparation failure. |
| partial_gap_summary | object | Summaries of missing one-minute source intervals, partitioned between replay-period coverage and warm-up coverage. |
| days | array of cache references | Per source instrument/date/version, with cache key, content checksum, and empty-day outcome. Manual entries identify the pinned dataset revision and its day refs. |
| fx_conversion_series | array of series refs | Direct/inverse conversion instruments and their one-minute date references in the shared source cache. |

Rows are sorted and unique and constrained to `[context_start_utc_ms, end_utc_ms)`. Warm-up rows are context only and do not contribute to replay readiness/progress. Dukascopy cache references key by user, cache version, instrument, interval, side, and UTC date; empty days are cached too. The cache has no expiry, is isolated by user, and is never removed when a run is deleted. Manual dataset revisions are user-scoped and immutable; each revision refers to content-addressed manual candle-day objects. Existing runs stay pinned to their revision when later imports create a new active revision.

## BacktestCandleCacheEntry

Per-user shared cache record for one Dukascopy COMB instrument/date. The Mongo record tracks source/cache version, instrument, interval, side, UTC date, status (`loading`, `ready`, or `empty`), content-addressed MinIO object reference/checksum when non-empty, lease owner/expiry, and timestamps. A renewable lease prevents duplicate concurrent downloads. An unreadable or missing object is reported as unavailable rather than treated as an empty day; the user may explicitly request durable recovery. Shared objects are retained indefinitely and remain after run deletion.

## ManualCandleDatasetRevision

Immutable per-user HistData dataset revision for one configured Settings instrument. A dataset head identifies the active revision; each revision stores the sorted union of available source dates, candle count, per-date immutable cache references/checksums, source format/version, and import timestamp. Preview is read-only and reports available date coverage plus overlap/conflict dates. A confirmed merge creates new referenced date content and a new revision, with incoming rows winning timestamp conflicts; an existing run's revision is not mutated. HistData timestamps are interpreted at fixed UTC−5 without DST; bid OHLC and supplied volume are preserved directly.

## PortableBacktestBackup

Settings backup format 1.1 includes ready and complete runs and their committed linked records. Exported runs carry stable `portable_origin` source-user/source-run identity for idempotent reimport, minimal source/cache manifest metadata, and no candle bytes or source-instance object keys. Exported state includes linked Backtest accounts/trades/executions, committed simulation orders/fills/positions/cost profile, cursor and furthest timestamp, chart workspace/tabs, and drawings. Preparation/recovery jobs, leases, and unfinished runs are omitted. Restore accepts format 1.0 as a backup with no Backtest records and reports created/reused run counts. It binds references to destination-user cache entries when present; missing Dukascopy days use explicit recovery, and missing manual revisions require original CSV re-upload.

## BacktestAccount

The account selector record associated with exactly one BacktestRun. Store this as a trade_accounts record extended with Backtest metadata rather than as a real account. Fully closed simulated trades use this account; working orders and open positions do not become `Trade` documents.

| Field | Type | Description |
|---|---|---|
| id | ObjectId/string | Account identity. |
| user_id | ObjectId | Authenticated owner. |
| workspace_mode | enum | backtest. Existing records default to real. |
| backtest_run_id | ObjectId/string | Unique associated run. |
| account_name | string | System-generated account value. Manual-source runs include a `-manual` discriminator; blind runs include instrument and “blind” and omit dates. |
| display_name | string | Non-blind Dukascopy: instrument and date range; manual: same generated label with `-manual`; blind: instrument and “blind” without dates. Labels use a short unique suffix when needed. |
| starting_balance_usd | decimal | Run's initial USD balance, copied from BacktestRun for account-facing balance displays. |
| risk_percent | decimal | Immutable per-entry risk percentage copied from BacktestRun. |
| status | enum | active for a preparing, ready, or complete run; deleting while confirmed run cleanup is pending; removed when deletion completes. |

A Backtest account is dedicated to one run and has no Real trades. Current balance is derived from the starting USD balance plus the committed net cash effect of fills, with each execution cost counted once; partial exits update it when their operation commits, while unrealized P&L on open quantity does not. A fully closed simulated position creates one conventional closed `Trade` under this account, linked to its stable simulation position/trade id; open exposure remains only in BacktestPosition. Such Trade documents include `backtest_run_id`, `simulation_generation`, `simulation_operation_sequence`, and stable simulated-position id. Existing Backtest Journal and analytics queries include a closed simulated Trade only when its generation matches the run and its operation sequence is no greater than the run's committed sequence; this keeps effects staged for an unfinished operation invisible while preserving existing active-account scoping. A unique constraint on run/generation/simulated-position prevents duplicate publication. Aggregate `gross_pnl`, `fee`, `net_pnl`, and `native_pnl` retain exact USD/native totals; linked execution/fill documents retain each exit's own conversion rate and realized P&L. Do not multiply aggregate native P&L by one scalar `quote_to_usd_rate` to reconstruct a multi-exit Backtest trade's history; leave the legacy scalar null when multiple event rates cannot be represented faithfully. Blind-run Journal rendering derives privacy from `backtest_run_id`: show weekday/time and normalized entry/exit values, never complete dates or raw prices. When account status is `deleting`, the account and its trades may be hidden from Backtest trade-facing queries while cleanup is pending; this is not deletion completion. Deletion physically removes every trade linked by `trade_account_id` and all trade-owned dependent data, then removes the account. On completion, neither the account nor its trades or dependents remain in storage.

## BacktestSimulationOperation

An idempotent journal record for one order, cancellation, manual position close, cost update, replay advancement/rewind, or reset request. The run document holds only the bounded CAS gate and committed sequence; operation details/effects are separate records.

| Field | Type | Description |
|---|---|---|
| id | ObjectId/string | Operation identity. |
| user_id / run_id | ObjectId/string | Owner and run scope. |
| client_operation_id | string | Client-generated retry key unique within user/run. |
| sequence | integer | Intended monotonic committed operation sequence. |
| reset_generation | integer | Generation to which this operation belongs. |
| kind | enum | submit_order, cancel_order, close_position, modify_protection, update_costs, advance, rewind, reset. |
| state | enum | pending, cleanup_pending, committed, rejected. |
| request | object | Validated command fields, excluding redundant user identity. |
| result | object/null | Stable result returned for retries. |
| created_at / committed_at | UTC timestamps | Operation lifecycle timestamps. |

Unique indexes cover `(user_id, run_id, client_operation_id)` and `(run_id, sequence)`. The operation record and deterministic entity effects are written before the run document advances `simulation_control.committed_sequence`; reads ignore uncommitted sequence values. A restarted request/worker resumes `pending` operations. Reusing an operation key with a different request returns conflict.

## BacktestOrder

One market/limit entry, protective stop/target, or completed manual-close market order. Working order state is distinct from fills and positions. Stop-market is used only for protective stops, not as an entry type.

| Field | Type | Description |
|---|---|---|
| id | ObjectId/string | Stable order id. |
| user_id / run_id / reset_generation | ObjectId/string/integer | Owner, run, and reset epoch. |
| operation_sequence / entity_version | integer | Committing sequence and monotonically increasing version for this order state. Preserve old versions until no longer needed for committed reads/reset cleanup. |
| client_order_id | string | Stable user request identity within the run generation. |
| role / kind / side | enum | entry, protective_stop, protective_target, or manual_close; market/limit entries, stop_market protective stop, limit protective target, or market manual close; buy or sell. |
| lots | decimal | Positive filled/order quantity in 0.001-lot increments, minimum 0.001. For an entry this is either risk-calculated or manually entered according to sizing_mode. |
| entry_price | decimal/null | Submitted limit price for a limit entry; absent for a market entry. For a protective stop/target child it is the current trigger/limit price; for manual close it is the execution reference price. |
| sizing_reference_entry_price / sizing_quote_to_usd_rate | decimal | Risk preview reference: current revealed candle close for a market entry and submitted limit price for a limit entry; snapshot the latest completed USD-per-quote conversion rate no later than acceptance (1 for USD-quoted pairs). Actual position risk is recalculated from the executed fill price and event-time conversion. |
| stop_loss_price / take_profit_price | decimal/null | Immutable submitted bracket prices on an entry order; matching protective child orders are created when it fills and their current trigger/limit prices may be versioned after fill. |
| sizing_mode / risk_percent / risk_budget_usd | enum/decimal | For entries, `auto` or `manual`; entries snapshot the run risk percentage and current-balance-derived USD risk budget at submission. The preview's default stop distance is `risk_budget_usd / (pip_size * contract_size * sizing_quote_to_usd_rate)` pips, using the latest completed quote-to-USD rate at or before the current candle close. Auto entries calculate lots from the selected stop distance, pip/contract metadata, as-of rate, and costs; manual entries retain the entered lots and report their projected risk. |
| status | enum | pending, filled, or cancelled. V1 uses full fills; rejected commands remain in the operation log rather than creating orders. |
| eligible_source_index | integer | First available unrevealed candle index for market entries submitted after the current cursor; market fills use this candle's open. Limit entries become eligible only on or after this index. Protective orders are eligible only from the candle after their entry-fill candle is fully processed. Manual-close orders execute at the current cursor candle's close. |
| linked_position_id / oco_group_id | ObjectId/string/null | Filled-order position link and paired protective-order group. Manual-close orders link to the position being closed. |
| submitted_at / updated_at | UTC timestamps | Lifecycle times. |

At fill time, a same-direction entry attaches to the oldest open position on the instrument. It adds a distinct fill/execution, updates weighted entry/reference price, remaining and maximum lots, costs and risk, and retains the existing stop/target while resizing protection quantities. If no matching position remains open when it fills, the entry opens a new position with its own bracket. Opposing fills reduce existing positions FIFO; excess opens a separately protected reverse position. Each actual entry's submitted bracket is retained in its order/fill history. Protective orders activate only after the entry-fill candle is fully processed. If stop and target both trigger within one candle for the same OCO pair, the stop is selected deterministically. A manual close is executed at the current revealed candle close and atomically cancels both linked protective orders.

## BacktestFill

Immutable record of each position-allocation created by a simulated order fill after configured costs. Implement each allocation as an extended existing `Execution` document so it links to exactly one position and a reserved conventional Trade id from position creation. The Trade document itself is not inserted until the position fully closes, so no open Trade appears in Journal/analytics. One opposing order that reduces several FIFO positions is represented by separate allocation executions, plus one more if excess quantity opens a reverse position. The replay UI groups allocations by parent order/fill for display.

| Field | Type | Description |
|---|---|---|
| id | ObjectId/string | Stable fill id. |
| user_id / run_id / order_id / position_id | ObjectId/string | Owner and related simulation entities. |
| trade_id | ObjectId/string | Reserved closed-Trade id for the owning position; no Trade document exists at this id until full closure. |
| operation_sequence / source_candle_index / allocation_index | integer | Committed operation order, immutable source candle that triggered the fill, and deterministic allocation order within the parent fill. |
| time_ms | integer | UTC execution event instant. Market/open and OHLC-triggered fills use the source candle's opening timestamp; manual close uses the current cursor candle's close timestamp; final forced close uses the final candle's close timestamp. |
| side / lots | enum/decimal | Filled direction and quantity. |
| reference_price / fill_price | decimal | Source execution reference and effective fill. A limit entry or target fills only when an eligible future candle's high-low range reaches its submitted limit; an opening gap alone without range touch does not fill. When touched, `fill_price` equals the submitted limit exactly, regardless of candle open; spread/slippage are separately accounted for that fill. Market and protective stop-market fills may use cost-adjusted prices and adverse opening-gap prices. |
| cost_profile_revision | integer | Applied profile version. |
| spread_cost / slippage_cost | decimal | Applied price-cost amounts for this fill allocation. For market/stop fills they may be represented in the effective price; for limit fills deduct them separately from P&L so the exact recorded limit `fill_price` is preserved. Never account for either cost twice. |
| quote_currency | string | Instrument quote currency. |
| native_gross_pnl | decimal/null | Realized quote-currency P&L for a closing fill after spread/slippage and before USD commission. |
| usd_gross_pnl | decimal/null | USD realized P&L for a closing allocation after spread/slippage and before commission. Trade net P&L sums all closing gross values and subtracts commission from every linked entry/exit allocation. |
| commission_usd | decimal | USD commission charged on this fill. |
| quote_to_usd_rate | decimal/null | USD per one quote-currency unit at this event; required for USD risk/P&L. Each fill retains its own rate. |

Entry and exit allocation executions are append-only. Replaying the same operation cannot create a second allocation because ids are deterministic from run/generation/order/source-candle/operation sequence/allocation index. Existing Backtest Trade analytics use aggregate USD gross/net values; event-level native/USD trade-detail data uses the linked executions and each event's conversion rate rather than treating one trade-level scalar rate as universal.

## BacktestPosition

Current open exposure projection, owned by one run. Do not persist this as an open conventional `Trade`.

Fields include stable id, reserved `simulated_trade_id`, user/run/account ids, reset generation, instrument, side, open lots, maximum lots, weighted entry/reference prices, linked entry-fill ids, retained stop/target prices, current stop-loss and take-profit order ids/prices, initial risk in native quote currency and USD, entry conversion rate, realized partial-close P&L/costs accumulated so far, applied cost totals, pending Journal `tag_ids`, operation sequence/entity version, and open/update timestamps. Pip size, price precision, and contract size come from the run's immutable instrument metadata. Scale-in and reductions create a new position version with updated weighted entry, size, protection quantity, and accumulated partial-close results. A protection modification versions only the selected child order(s); initial risk and the existing bracket remain unchanged during scale-in. An actual stop-price change adds the user's `stop-moved` tag id to the position once; the tag is copied to its conventional Trade when the position fully closes. A manual close exits the full remaining lots at the current revealed candle's close and cancels both child orders atomically. A full close creates exactly one existing `Trade` at the reserved id with status `closed`; associated Execution records already reference that id. Its run/generation/sequence metadata gates visibility to the committed simulation state. Stable ids and a unique run/generation/position constraint prevent duplication after operation retry/recovery.

While open, the latest committed position projects one chart indicator set per chart pane in its run, keyed by stable position id. The projection uses the weighted entry price, current active protection prices, remaining quantity, and `unrealized_pnl_usd` marked at the latest revealed candle close before hypothetical exit costs, using frozen instrument metadata and the latest completed quote-to-USD rate no later than that close. This P&L is derived display data, not persisted position state, and does not change current balance or closed-trade analytics. The filled entry price is read-only, while stop and target use the existing protection mutation. Indicator lines and controls are presentation state derived from BacktestPosition and its child orders, not persisted ChartDrawingState. Reload and navigation rebuild them from committed simulation state; a fully closed position has no active indicator set.

## BacktestCostProfile

Per-run versioned execution-cost configuration.

| Field | Type | Description |
|---|---|---|
| user_id / run_id | ObjectId/string | Owner and run scope. |
| revision | integer | Monotonically increasing profile version. |
| operation_sequence | integer | Commit sequence that made this immutable profile version active. |
| total_spread_pips | decimal | Nonnegative total spread; each side pays one half. |
| slippage_pips | decimal | Nonnegative adverse fill adjustment. |
| commission_usd_per_lot_per_side | decimal | Nonnegative commission in USD for each filled lot and side. |
| updated_at | UTC timestamp | Last accepted profile update. |

Each run starts with revision zero and all costs set to zero. An unset/zero profile is visibly reported as costs excluded, and gross equals net. Store immutable profile revisions and let readers select the latest revision at or below the run's committed sequence. Each fill snapshots the profile revision and actual applied amounts. Changes affect future fills only. Reset preserves the latest profile as run configuration.

## ReplayCursor

The shared playback position used by all chart tabs for one BacktestRun. Store durable position on BacktestRun and instantiate one CandleKit ReplayController per active run in the browser.

| Field | Type | Description |
|---|---|---|
| source_candle_index | integer | Index into the manifest's current ordered one-minute candle sequence, bounded below by `snapshot.replay_start_source_index`; warm-up indexes are not eligible replay positions. |
| time_ms | integer | Timestamp of the selected source candle in UTC epoch milliseconds. |
| furthest_source_candle_index / furthest_time_ms | integer | Persisted high-water mark for the furthest replay candle reached; remains unchanged by rewind and bounds linked Backtest trade charts. |
| revision | integer | Monotonic version to reject stale writes. |
| updated_at | UTC timestamp | Last persisted cursor update. |

Play/pause/speed are live transport state. When the run becomes ready, the persisted cursor points at the first available replay-period candle; on reload, restore the saved cursor and start paused. Every tab observes the same CandleKit controller and cursor. Backward seek rebuilds the display from warm-up context plus replay-period data no later than the selected cursor; it cannot move the cursor into warm-up history.

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
- Each resolved BacktestRun has exactly one BacktestAccount and each ready run has one BacktestCandleManifest over shared source-cache references. A random run has no account until its selection resolves.
- Each selecting-period or preparing BacktestRun has exactly one durable BacktestPreparationJob. A completed job may remain with a ready/complete run but is transient. Cache-recovery lease and progress are embedded in the run. Portable restores do not require preparation/recovery jobs until the user explicitly queues cache recovery.
- Each BacktestAccount belongs to exactly one BacktestRun and may be referenced by zero or more trades through `trade_account_id`; those trades are removed with the account when that run is deleted.
- Each BacktestRun has one durable ReplayCursor shared by all active chart tabs and one bounded simulation CAS gate; every cursor/order/cost/reset mutation shares its operation sequence.
- Each BacktestRun stores its immutable starting USD balance and risk percentage. Auto-sizing is enabled by default in the order-panel UI; the user's sizing checkbox selects either risk-derived lots or a manual lot amount for each submitted entry.
- Each simulation operation is unique by client operation id and run sequence. Orders, fills, open positions, cost profiles, and operation results are separate run-owned records with a reset generation and committed sequence.
- A fully closed simulated position produces exactly one conventional closed Trade under the run's BacktestAccount; open positions never appear as closed trades or in existing closed-only analytics.
- Each BacktestRun has zero or one ChartWorkspaceLayout before first open and exactly one after initialization, and may have zero or more BacktestPreparationNotices for completed failures/no-data outcomes.
- Each BacktestRun may have zero or more ChartDrawingState documents, one per interval.
- A confirmed deletion moves the run and account to `deleting`; hiding them from normal Backtest views is only an interim state. The run's durable deleting state resumes cleanup after interruption. Cleanup physically removes all account-linked trades and dependent data, every execution tagged to the run, the account, preparation job, replay cursor, simulation control and operation/order/fill/position/cost records, chart tabs/workspace, and drawings. It MUST NOT delete shared Dukascopy cache entries, shared manual revision data, or their MinIO objects. Repeated deletion and cleanup passes are safe.
- Real accounts and trades are excluded from Backtest queries; Backtest accounts are excluded from Real queries.


