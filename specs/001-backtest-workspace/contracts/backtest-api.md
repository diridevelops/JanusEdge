# Backtest API Contract

This contract describes the authenticated Flask API used by the React Backtest pages, Settings backup flow, and CandleKit adapters. Endpoints use JanusEdge's existing API prefix and error conventions.

## Authentication and ownership

All endpoints require the existing JWT bearer authentication. The backend derives user_id from the JWT and applies owner filtering to every run, preparation job, candle, account, trade, execution/fill, simulation operation, order, position, cost-profile, replay-position, deletion, and drawing operation. Request bodies never accept a user_id. Access to another user’s resource returns the same not-found behavior as an unknown id.

Timestamps are UTC epoch milliseconds. Candle bars are returned in chronological order with one-minute source interval.

## Supported instruments

### GET /api/backtest/instruments

Returns the current supported-instrument codes exposed by the pinned Dukascopy downloader (`dukascopy_market_data.instruments.fetch_instrument_codes`). The run form uses this response as its selector source.

~~~json
{
  "instruments": ["EUR-USD", "GBP-USD"]
}
~~~

If the catalog source is unavailable, return a service error and create no run or account. Run creation validates the submitted code against the same current catalog; a code not present in it uses the existing validation-error format.

### GET /api/backtest/manual-instruments

Returns the current user's supported Settings instrument mappings with complete sizing rules. The manual selector does not use the Dukascopy catalog. Rows include canonical instrument, base/quote currency, tick/price precision, contract size, minimum lot, lot increment, quote-unit scale, and whether a historical conversion route is supported.

### GET /api/backtest/manual-datasets/{instrument}

Returns the authenticated user's active manual dataset revision and coverage for a configured instrument: revision id, sorted available source dates, candle count, and first/last dates. A missing dataset returns an empty coverage result.

### POST /api/backtest/manual-import/preview

Accepts multipart form data containing `instrument` and one or more `files` (HistData CSVs). Parses without writing cache data and returns revision/expected_revision, cached_dates, incoming_dates, available_dates, candle_count, overlap_count, conflict_count, conflicting_dates, overlap_dates, and `requires_confirmation`. The uploaded data is headerless semicolon-separated one-minute timestamp, bid OHLC, and volume. Timestamps are interpreted at fixed UTC−5 without DST.

## Create a run

### POST /api/backtest/runs

Request:

~~~json
{
  "instrument": "EUR-USD",
  "start_date": "2026-01-01",
  "end_date": "2026-01-10",
  "display_timezone": "Europe/Rome",
  "initial_balance_usd": 10000,
  "risk_percent": 1.0
}
~~~

This Dukascopy endpoint validates the instrument against the current downloader catalog, the selected replay date range, timezone, and inclusive one-calendar-year limit. `initial_balance_usd` and `risk_percent` default to 10,000 and 1.0; both must be finite and positive, and risk percent cannot exceed 100. `warmup_days` is a nonnegative integer shared with Manual import and defaults to 0. For a February 29 start, February 28 of the following year is the latest permitted end date. The selected local-day boundaries define the replay window. The backend calculates the context start by subtracting `warmup_days` in the configured display timezone, then converts context and replay boundaries to UTC. The run is created with a metadata-only manifest over shared cache references; a worker uses the per-user Dukascopy cache rather than writing a per-run candle object. Preparation does not run in the HTTP request.

For Dukascopy, random selection instead sends:

~~~json
{
  "instrument": "EUR-USD",
  "display_timezone": "Europe/Rome",
  "period_selection": "random",
  "period_months": 3,
  "initial_balance_usd": 10000,
  "risk_percent": 1.0
}
~~~

`period_months` must be 1, 3, 6, or 12; `start_date` and `end_date` are omitted. Balance and risk fields use the same defaults and validation as a manual run. The backend captures yesterday in the configured display timezone when accepting the request, then creates a `selecting_period` run with null dates and no account and enqueues a durable selection job. Its initial response is:

~~~json
{
  "run": {
    "id": "run-id",
    "instrument": "EUR-USD",
    "period_selection": "random",
    "period_months": 3,
    "initial_balance_usd": 10000,
    "risk_percent": 1.0,
    "current_balance_usd": 10000,
    "requested_start_date": null,
    "requested_end_date": null,
    "status": "selecting_period",
    "account_id": null,
    "account_label": null,
    "progress": {"stage": "selecting_period", "percent": null}
  }
}
~~~

The worker chooses eligible years randomly without replacement and probes at most ten distinct random eligible dates per year. A probe fetches the UTC day or days intersecting that local date and accepts a candidate only when a COMB one-minute candle falls inside the exact replay local-day UTC bounds. After ten empty probes, it discards the year and selects another untried eligible year. It does not treat provider errors as empty days. On a hit, it persists the final local dates, creates the one account using FR-009's label rules, and enters the normal warm-up/preparation flow. The inclusive end is the day before adding the selected calendar months with month-end clamping. If every year is exhausted, the run/account/job are removed and a dismissible notice identifies the instrument and duration. A start-day hit does not guarantee candles later in the selected period; existing coverage, gap, and readiness rules still apply. The cutoff and attempts remain fixed/durable across worker restart, and deleting a selecting-period run fences account creation.

Blind mode adds `"blind_mode": true` to a random request:

~~~json
{
  "instrument": "EUR-USD",
  "display_timezone": "Europe/Rome",
  "period_selection": "random",
  "period_months": 3,
  "blind_mode": true
}
~~~

`blind_mode` is optional and defaults to false. It is valid only with random selection when true. Omitting it preserves existing manual and random request/response shapes; an explicit false is equivalent to omission. A blind run persists and returns `blind_mode: true`; once its snapshot is ready it also retains the fixed `normalized_reference_price`, equal to the first available replay-period candle's open. Zero or non-finite reference prices fail before readiness through the existing cleanup and dismissible-notice lifecycle. Negative reference prices use the exact `100 × P / referencePrice` mapping.

Accepted response:

~~~json
{
  "run": {
    "id": "run-id",
    "instrument": "EUR-USD",
    "initial_balance_usd": 10000,
    "risk_percent": 1.0,
    "current_balance_usd": 10000,
    "status": "preparing",
    "account_id": "account-id",
    "progress": {
      "stage": "downloading",
      "percent": null
    }
  }
}
~~~

Return 202 while preparation continues. Invalid input uses the app’s validation-error format. If the catalog cannot be fetched, return a service error and create no run/account. If preparation later returns no data or fails terminally, report the outcome with the instrument/range and remove the run, account, and job while retaining shared cache data. A worker restart or expired lease is recoverable interruption, not a terminal failure.

### POST /api/backtest/runs/manual

Accepts `multipart/form-data` with a JSON `settings` field and zero or more `files` fields. `settings` uses the same shared date/random/blind/`warmup_days`/balance/risk/cost fields, and adds `instrument`, optional `expected_dataset_revision`, `confirm_overwrite`, and `quote_to_usd_fallback_rate`. The instrument must have complete sizing data in the authenticated user's Settings table. If files are omitted, an active manual dataset must already exist. If files overlap the active dataset, the merge is rejected unless `confirm_overwrite` is true; conflict details identify affected dates. A successful upload merges the timestamp union into a new immutable dataset revision, with incoming values winning conflicting timestamps, then queues a run pinned to that revision. Manual dates and `warmup_days` boundaries use HistData's fixed UTC−5 calendar without DST. If the requested random period exceeds the imported date span, the run uses all available dates. The response is 202 with the new run. Manual account labels carry a `-manual` suffix; the form does not accept a run-name field.

The manual selection source offers only imported dates containing candles. Random periods are selected from those available dates; an oversized period uses the full imported range. Warm-up reads earlier candles from the pinned revision, limited by `warmup_days`. Bid OHLC and provided volume are passed through directly. A fallback quote-to-USD rate is accepted only for non-USD quote currencies and is used when eligible historical conversion data is unavailable; USD quote currencies use 1.

## List and inspect runs

### GET /api/backtest/runs

Returns the authenticated user’s selecting-period, preparing, ready, complete, and deleting runs, newest first. Each list entry includes id, instrument, period selection, nullable selected dates, nullable account label, status, and progress (`stage` plus a percentage when measurable, otherwise null); it includes `blind_mode` for new records, treating a missing value on legacy records as false. Until selection resolves, the frontend shows the instrument and selection status without dates or an account. For blind runs, the frontend omits dates and ranges in every run-list state and the account label contains “blind” without dates. The API continues returning canonical run dates and prices; this is rendered-UI masking, not API redaction. A deleting run is shown as pending cleanup and cannot be opened. The frontend polls this endpoint every five seconds while at least one run is selecting-period, preparing, or deleting and stops when none are. Progress is read from MongoDB state updated by the worker. Failed/no-data records are not retained.

### GET /api/backtest/runs/{run_id}

Returns the owned run detail, source, nullable account label/dates while selection is pending, frozen `instrument_metadata`, `initial_balance_usd`, `risk_percent`, current balance, source-specific manifest and coverage, pinned manual revision when applicable, saved current/furthest cursor, cache availability/recovery status, `blind_mode`, normalized reference, simulation summary, and status. A selecting-period, preparing, or deleting run remains on the list page and has no playable chart detail. A ready or complete run is inspectable only while its pinned data is available. When ready, its cursor starts at the first available replay candle; this index can exceed zero because the manifest references warm-up context. Readiness requires replay-period candles. The UI formats replay timestamps in the configured timezone and applies Blind rendering rules; source-candle API values remain canonical. Chart workspace state loads from its dedicated routes.

### GET /api/backtest/runs/{run_id}/cache-status

Checks the run manifest against the authenticated user's source cache and reports availability or recovery progress. Missing/unreadable references identify instrument, UTC date, and source kind. Opening a run does not start downloads. A ready or complete run with unavailable references is gated from replay until recovery finishes.

### POST /api/backtest/runs/{run_id}/cache-recovery

Requires the user's explicit recovery action. Enqueues durable recovery for only missing Dukascopy references, including conversion instruments; cache hits and known-empty dates are reused. Returns an accepted job/status and the frontend polls `cache-status` for progress. Refreshed data may differ; successful recovery preserves committed orders, fills, positions, balance, and operation state, rebuilds candle indexes, remaps the cursor to the latest candle at or before its saved timestamp, and shows a dismissible changed-history warning. This endpoint does not recover missing manual data; manual runs use the upload route below.

### POST /api/backtest/runs/{run_id}/manual-cache-recovery

Accepts multipart HistData files for a manual run. Files must reproduce the run-pinned manual revision content; a mismatching upload is rejected. A valid re-upload restores missing references and resumes replay without changing simulation state. The missing-data view offers this action for portable/manual runs instead of fetching Dukascopy data.

### DELETE /api/backtest/runs/{run_id}

Permanently deletes an owned selecting-period, preparing, ready, or complete run. The frontend must require explicit confirmation before calling this endpoint and explain that the run's dedicated Backtest account, if created, all simulated orders/fills/open positions, and all closed trades linked to it will also be removed. The request has no user or account identifier; the server derives ownership and the one-to-one account association from the run record.

Accepted response:

~~~json
{
  "run": {
    "id": "run-id",
    "status": "deleting"
  }
}
~~~

Return 202 after the durable run state changes to `deleting`; this means cleanup was accepted, not that deletion completed. The run immediately becomes non-playable, and the associated account and trades may be excluded from Backtest views while cleanup is pending, but hiding them is only an interim state. A repeated request while cleanup is pending returns the same pending state. A missing or non-owned run returns the standard 404 behavior.

The worker treats `deleting` as a cancellation fence for run-owned preparation/replay/simulation/chart writes and resumes cleanup after restart. Cleanup removes preparation and recovery jobs, replay cursor, simulation control/operation/order/fill/position/cost data, run-tagged executions, chart workspace/tabs, drawings, trades and trade-owned dependent files, and the dedicated account. It does not delete shared Dukascopy cache entries or manual dataset revisions/objects. The run disappearing from `GET /api/backtest/runs` is the completion signal. Cleanup is idempotent and does not affect other runs or Real records.

## Preparation result notices

### GET /api/backtest/notices

Returns the authenticated user's undismissed no-data and failure notices, newest first. Manual notices include their instrument and selected date range. Random-selection notices include their instrument and requested duration, even though no date range or account was resolved. Notices remain after the failed/no-data run and any account are deleted.

### DELETE /api/backtest/notices/{notice_id}

Dismisses the owned notice. This does not restore or retain the deleted run or account.

## Persist the dockable chart workspace

### GET /api/backtest/runs/{run_id}/chart-workspace

Returns the owned run's saved workspace and revision. The MongoDB document is stored in `backtest_chart_workspaces`, unique by authenticated user and run. If no layout has been initialized yet, `workspace` is null, top-level `revision` is zero, and `legacy_tabs` contains the old flat `backtest_chart_tabs` records in position order. The frontend creates a visible sibling-pane layout from legacy records while preserving each chart id and interval. With no legacy records, it initializes a one-chart, 1m layout. Before mounting the editable workspace, the client saves that initialized layout through the PUT below. Concurrent initializers use `expected_revision: 0`; a loser receives 409 and reloads the saved workspace.

Example, initialized run:

~~~json
{
  "workspace": {
    "schema_version": 1,
    "layout_engine": "flexlayout-react",
    "id": "run-123",
    "name": "default",
    "created_at": "2026-09-26T10:00:00Z",
    "updated_at": "2026-09-26T10:00:00Z",
    "revision": 4,
    "tree": {
      "global": {},
      "borders": [],
      "layout": {
        "type": "row",
        "weight": 100,
        "children": [{
          "type": "tabset",
          "weight": 100,
          "children": [{
            "type": "tab",
            "id": "chart-1",
            "name": "Chart 1",
            "component": "backtest-chart",
            "config": {"id": "chart-1", "kind": "backtest-chart", "config": {"interval_minutes": 1}}
          }]
        }]
      }
    },
    "panels": {
      "chart-1": {"id": "chart-1", "type": "backtest-chart", "interval_minutes": 1}
    }
  },
  "revision": 4,
  "legacy_tabs": []
}
~~~

The `tree` is the FlexLayout JSON blob serialized by CandleKit's workspace adapter. The `panels` map is JanusEdge chart metadata, mapped to CandleKit panel instances by the frontend `LayoutPersistence` adapter. Ownership fields are never accepted from the client.

### PUT /api/backtest/runs/{run_id}/chart-workspace

Creates or replaces the user's entire workspace for an owned, ready run. `id` is the stable run-scoped workspace id and `name` is `default`; the server sets timestamps and derives user ownership. Request:

~~~json
{
  "expected_revision": 4,
  "workspace": {
    "schema_version": 1,
    "layout_engine": "flexlayout-react",
    "id": "run-123",
    "name": "default",
    "tree": {
      "global": {},
      "borders": [],
      "layout": {
        "type": "row",
        "weight": 100,
        "children": [
          {"type": "tabset", "weight": 50, "children": [{"type": "tab", "id": "chart-1", "name": "Chart 1", "component": "backtest-chart", "config": {"id": "chart-1", "kind": "backtest-chart", "config": {"interval_minutes": 1}}}]},
          {"type": "tabset", "weight": 50, "children": [{"type": "tab", "id": "chart-2", "name": "Chart 2", "component": "backtest-chart", "config": {"id": "chart-2", "kind": "backtest-chart", "config": {"interval_minutes": 60}}}]}
        ]
      }
    },
    "panels": {
      "chart-1": {"id": "chart-1", "type": "backtest-chart", "interval_minutes": 1},
      "chart-2": {"id": "chart-2", "type": "backtest-chart", "interval_minutes": 60}
    }
  }
}
~~~

The server derives user_id, validates that the workspace id matches the run, and validates the workspace schema, supported layout engine, tree shape, unique chart ids, chart panel type, interval range (whole minutes 1 through 1,440), active tabs, split weights, and correspondence between tree nodes and panel metadata. A layout must contain at least one chart panel and no fixed v1 maximum applies. A valid matching revision is atomically saved and incremented; return the saved workspace and new revision. A stale `expected_revision` returns 409 with the current revision and does not change stored state. Invalid layout data uses the existing validation-error shape, and any rejected write leaves the last valid workspace unchanged.

The frontend implements CandleKit's `LayoutPersistence` interface over this authenticated API. It debounces and coalesces layout events and serializes writes. If a bootstrap or migration write conflicts, it reloads the winner. If a user edit conflicts, the client preserves the local draft and offers either loading the remote layout or explicitly reapplying the draft against the latest revision; it never automatically retries a stale layout. Local browser storage is not authoritative. Legacy flat records are migrated through the same revision-zero write and may be deleted only after successful workspace persistence; the old records remain read-only migration input until that succeeds.

## Settings backup and restore

### GET /api/auth/export

Downloads a Settings ZIP backup. Format 1.1 includes ready and complete Backtest run metadata and committed state: associated accounts and linked trades/executions, orders, positions, fills, costs, workspaces/tabs, and drawings. It omits preparation/recovery jobs and worker state, candle bytes, shared-cache objects, and source-instance object keys. Existing imported market-data dataset export is unchanged.

### POST /api/auth/restore

Accepts multipart field `file` containing a 1.0 or 1.1 archive. A 1.0 archive restores without Backtest records. A 1.1 restore maps runs and linked records into the authenticated destination account, assigns stable source identities for idempotent re-import, and binds candle manifest references to matching destination-owned cache days when available. Missing references remain unavailable until explicit source-appropriate recovery. The result and Settings summary include Backtest run `created` and `reused` counts.

## Retry an interrupted run

### POST /api/backtest/runs/{run_id}/retry

Requeues the existing owned preparing run’s durable job and returns 202 with that same run id and account id. This operation is idempotent with respect to job/run/account creation. The worker resumes after the latest completed UTC-date checkpoint and may fetch again only an incomplete date. Worker recovery after an expired lease uses the same checkpoint without requiring this endpoint. Retry does not permit a ready run.

## CandleKit ReplayDataSource

The frontend adapter exposes the following CandleKit source operations through the authenticated API.

### GET /api/backtest/runs/{run_id}/candle-dates?before={utc_date}&after={utc_date}

Returns the sorted UTC dates containing candles in the pinned run source, including warm-up dates. This supports CandleKit’s day-oriented listDatesBefore/listDatesAfter behavior. Empty dates are omitted from this list and not replaced by synthetic candles. The selected replay start remains separately identified by run detail and replay-start index. Dates remain canonical in this API for blind runs; the UI must apply its masking rules.

Example response:

~~~json
{
  "dates": ["2026-01-02", "2026-01-05", "2026-01-06"]
}
~~~

### GET /api/backtest/runs/{run_id}/candles?date={utc_date}

Returns one UTC day of one-minute candles resolved from the run's pinned Dukascopy shared cache or manual dataset revision. An empty array is valid for a requested empty date. A date outside `[context_start_utc_ms, end_utc_ms)` returns validation/not-found per the existing API error convention. Warm-up candles are historical context; the frontend filters replay-period candles after the current cursor. If data references are missing, replay is gated and the UI offers explicit recovery. For blind runs, normalize before display and never render raw timestamps/prices; API-level redaction is not part of this contract.

Example response:

~~~json
{
  "candles": [
    {
      "time_ms": 1767308400000,
      "open": 1.1721,
      "high": 1.1728,
      "low": 1.1719,
      "close": 1.1724,
      "volume": 1234
    }
  ]
}
~~~

The adapter maps time_ms to CandleKit’s UTC epoch-millisecond Bar time. API availability of future historical rows does not authorize the chart to render them: each chart update remains bounded by the shared replay cursor.

For Dukascopy, `open`, `high`, `low`, and `close` are component-wise arithmetic midpoints of corresponding COMB BID/ASK OHLC; independent side extrema make midpoint high/low estimates. `volume` is summed bid and ask quoted liquidity, not executed trade volume. For Manual import, bid OHLC and source volume are returned directly.

### GET /api/backtest/runs/{run_id}/chart-candles?start={iso}&end={iso}&interval={1m|5m|15m|1h}

Returns run-derived candles for a linked Backtest trade chart within the request's UTC time bounds, clipped to the run's context/replay range and the furthest reached replay candle. `end` is exclusive; the furthest timestamp is the opening time of a one-minute candle, so the effective end cannot exceed `furthest_time_ms + 60,000`. Older cursors without a furthest timestamp use their saved `time_ms`. Rewinding the current cursor does not shorten this high-water cap. For intervals above 1m, aggregate only the included one-minute rows using UTC buckets, first open, maximum high, minimum low, last close, and summed volume; a final bucket may be partial. Response shape remains `{"candles":[{"time_ms":0,"open":0,"high":0,"low":0,"close":0,"volume":0}]}`. Manual/non-Backtest trade charts retain their current source.

## Save the shared replay position

### PUT /api/backtest/runs/{run_id}/replay-position

Request:

~~~json
{
  "source_candle_index": 1234,
  "time_ms": 1767308400000,
  "expected_revision": 8,
  "client_operation_id": "op-uuid"
}
~~~

The server validates that the run is ready and the index/time pair matches its resolved pinned source. A valid replay cursor MUST be at or after `manifest.replay_start_source_index` and no later than the last candle in the selected replay period; warm-up indexes are not valid cursor positions. Forward movement MUST use `POST /simulation/advance` so each intervening source candle is processed in order. This endpoint permits only a backward step/seek before an order has ever been accepted in the current reset generation. Once an order is accepted, backward movement returns 409 until an explicit confirmed reset. A stale revision returns 409. The client clamps a seek before the selected replay start to the first eligible replay candle and sends unique operation ids so an older/retried request cannot overwrite a later selection.

When a run first becomes ready, the server persists `source_candle_index: replay_start_source_index`, the first eligible replay candle’s `time_ms`, and revision zero in the same run-document update that changes status to ready. The frontend uses this stored cursor and starts playback paused. All resolved source candles before this index are loaded as historical chart context but do not contribute to replay progress, forward/backward stepping, seeking, or completion. Accepted order and candle-advance operations share a run-level compare-and-swap sequence; the run cursor, committed sequence, and final `complete` status change atomically.

## Persist drawing state

### GET /api/backtest/runs/{run_id}/drawings?interval_minutes={n}

Returns the owned drawing payload for the given interval, or null when no saved set exists.

Example response:

~~~json
{
  "interval_minutes": 5,
  "candlekit_version": "0.1.0",
  "schema_version": 1,
  "revision": 3,
  "serialized_state": null
}
~~~

### PUT /api/backtest/runs/{run_id}/drawings?interval_minutes={n}

Request:

~~~json
{
  "candlekit_version": "0.1.0",
  "schema_version": 1,
  "expected_revision": 3,
  "serialized_state": "[]"
}
~~~

The server validates interval limits, ownership, payload size, and JSON shape, then upserts the opaque exported string by user/run/interval. CandleKit 0.1.0 exports drawings as a JSON array; the API also accepts a JSON object-shaped empty state. Return the persisted payload and incremented revision. A revision conflict returns 409 so another open tab cannot silently overwrite a newer drawing set. An empty drawing set is a valid saved state. Preserve replay-aware drawing visibility if provided by the pinned CandleKit artifact; otherwise the frontend filters drawings with any time anchor later than the replay cursor and shows them again when all anchors are at or before it. This fallback does not use drawing creation or edit time and does not alter the persisted payload.

## Simulation orders, execution, and account results

Cursor movement, order, cancel, manual-close, protection-modification, cost, and advance mutations require authentication, owner/run filtering, a ready run, the run-level simulation CAS revision, and a unique client-generated `client_operation_id`. Reset is available on ready or complete runs. Repeating the same key with the same request returns the stored result; reusing it with a different request returns 409. Simulation effects are durable and become visible only when the operation sequence is committed on the run. A pending operation is resumed idempotently after restart. Every command is fenced when deletion begins.

At fill time, a same-direction entry on the same instrument attaches to the oldest open position and its linked simulated trade. It appends the entry execution and updates weighted entry/reference price, remaining and maximum lots, costs, and risk while retaining the existing stop and target and resizing their protective order quantities. It creates no duplicate position or protective pair. If the position closes before a pending entry fills, that entry opens a new position using its own bracket. Opposite-side entries continue reducing open exposure FIFO; any reversal remainder opens a separately protected position. Closed trade detail shows the weighted entry and every execution.

### GET /api/backtest/runs/{run_id}/simulation

Returns current simulation state: committed cursor and operation sequence, reset generation, whether a mutation/reset cleanup is pending, whether backward navigation is locked, immutable initial balance and risk percentage, current balance, current versioned costs, working orders, fills, open positions, realized closed-trade summaries, and whether the run is ready or complete. Each open-position result includes its stable position id, side, remaining lots, weighted entry price, current stop-loss/take-profit prices and order ids, and derived `unrealized_pnl_usd` marked at the latest revealed candle close before hypothetical exit costs. Use the run's frozen instrument metadata and latest completed immutable quote-to-USD rate no later than the mark candle close. Unrealized P&L is display-only; it does not alter current balance or closed-trade analytics. The position id is the scope for that indicator's protection and close actions. Indicator sets are presentation state, not persisted user drawings. Results are bounded/paginated where collections can grow. Order/position/cost results select the latest version at or below the committed sequence and current generation; fills and closed Trades are filtered by committed sequence/generation. A complete run remains inspectable.

### POST /api/backtest/runs/{run_id}/simulation/orders

Submits one protected entry order. Both protective prices are required. Example auto-sized market request:

~~~json
{
  "client_operation_id": "op-uuid",
  "expected_revision": 12,
  "side": "buy",
  "order_type": "market",
  "auto_size": true,
  "stop_loss": 1.082,
  "take_profit": 1.09
}
~~~

`auto_size` is required in every entry request. The USD risk budget is current balance multiplied by run Risk% and divided by 100. The order-panel default stop distance is that budget divided by the instrument's USD pip value for one standard lot (`pip_size * contract_size * quote_to_usd_rate`), using frozen pip/contract metadata and the latest completed quote-to-USD conversion rate no later than the current cursor candle close; multiply the pips by pip size for a price offset. With `auto_size: true`, omit `lots`; the service calculates lots from the selected entry-to-stop distance, frozen pair metadata, as-of quote-to-USD rate, and active execution costs, then rounds down to a 0.001-lot increment. Preview lots update when entry or stop moves. If even the minimum lot would exceed the budget, reject without accepting the order. With `auto_size: false`, `lots` is required, positive in 0.001 increments, and at least 0.001; the response still reports projected USD risk and risk percent. The order-panel checkbox defaults to enabled. The request snapshots the current risk budget, sizing reference price, conversion rate, and sizing mode; a later balance change does not resize an already accepted working order. Report preview risk using the sizing reference, then recalculate actual initial risk from the executed fill price and event-time conversion after fill; an opening gap can make actual risk differ from preview. All entries require both finite stop-loss and take-profit prices at instrument precision, on the correct sides of the entry (long: stop below and target above; short: target below and stop above), after blind display values are converted to canonical prices. Do not require prices to be positive: the blind normalization reference and source price may be negative. Market orders use the close of the current revealed candle as their preview/reference price but remain pending until the next available unrevealed source-candle index and fill at that candle's open with active costs. They cannot fill against candle N or inspect fill-candle high/low/close. Limit requests require a finite `entry_price` at instrument precision and become eligible only on a later unrevealed candle; the future candle's high-low range must reach the limit price to trigger a fill. A gap opening through a limit without the candle range reaching it does not fill. When touched, the order fills at exactly the submitted `entry_price`, without price improvement. Spread/slippage amounts on a limit fill are accounted for separately under FR-045 and do not change the recorded fill price. If there is no later available candle because the run is at its final candle, reject with a conflict/validation error and do not accept an unfillable order. Only ready runs accept orders; complete runs require reset first. On the first order for a non-USD quote currency, reject if neither eligible historical conversion data nor a valid configured Manual fallback exists at the sizing event time.

Example manual-size limit request:

~~~json
{
  "client_operation_id": "op-uuid",
  "expected_revision": 13,
  "side": "sell",
  "order_type": "limit",
  "entry_price": 1.09,
  "auto_size": false,
  "lots": 0.1,
  "stop_loss": 1.095,
  "take_profit": 1.08
}
~~~

All user-facing order price inputs use the run's displayed price scale. For non-blind runs, this is the canonical source-price scale. For blind runs, the client submits normalized values and the backend maps them to canonical prices with `canonicalPrice = displayedPrice × normalized_reference_price / 100` before validation and persistence. API responses may retain canonical values; the blind Backtest UI must normalize every displayed value before rendering it.

### POST /api/backtest/runs/{run_id}/simulation/orders/{order_id}/cancel

Cancels an owned pending entry order by operation key/revision. Filled orders and protective exits cannot be canceled through this entry-order action. The original order remains in history with cancelled status.

### POST /api/backtest/runs/{run_id}/simulation/positions/{position_id}/close

Manually closes the full remaining quantity of one owned open position at the close of the currently revealed cursor candle. Request contains `client_operation_id` and `expected_revision`; it does not advance the cursor. The fill uses the active cost profile and the latest completed immutable quote-to-USD conversion rate no later than the candle-close event. The same committed operation records a filled `manual_close` BacktestOrder, appends the closing Execution, cancels both linked stop-loss/take-profit OCO orders, updates the closed Trade/account result, and makes the position no longer open. Repeating the same operation id returns the original result. This action is unavailable for a closed position or a complete run.

### PUT /api/backtest/runs/{run_id}/simulation/positions/{position_id}/protection

Moves the active stop-loss, take-profit, or both on one owned open simulated position. The request contains `client_operation_id`, `expected_revision`, and at least one of `stop_loss` or `take_profit`; omitted levels remain unchanged. Prices must be finite, at instrument precision, and not already crossed at the current revealed close (long stop below and target above that close; short stop above and target below). The updated protection becomes eligible on the next available unrevealed one-minute candle and cannot use prior/current-candle high, low, or close. The OCO relationship remains intact and original initial risk/R-analysis basis is unchanged. A changed stop idempotently ensures a user tag named `stop-moved` exists; if absent, create it in the system `General` category. If the tag already exists, reuse it. Store the tag id with the open position and apply it to the conventional Journal Trade when the position fully closes. A target-only change does not add this tag. The response returns current protection prices, immutable initial risk, and tag state. A closed position cannot be modified.

The chart's BE action uses this endpoint for exactly one position, setting `stop_loss` to that position's weighted entry price; the ordinary side/crossed-price validation and next-candle activation rules still apply. Disable BE if the entry price has already been crossed by the current revealed close. Dragging a stop or target submits only that selected position's changed level.

The chart's X action uses the close endpoint above for exactly one position. It closes the selected position at the current revealed candle close; it does not close sibling positions that were opened by other entries.

### PUT /api/backtest/runs/{run_id}/simulation/costs

Replaces the per-run cost profile using nonnegative `total_spread_pips`, `slippage_pips`, and `commission_usd_per_lot_per_side`, plus operation key/revision. The response contains a new profile revision. Before the first edit, revision zero defaults all values to zero and the UI identifies costs as excluded. Buy/sell fills apply half the configured total spread on their respective side; slippage is adverse; commission is USD per lot per side. Only future fills use the new profile. Each fill retains the revision and exact applied costs. Cost changes are unavailable after complete until reset.

### POST /api/backtest/runs/{run_id}/simulation/advance

Advances to a later source candle index, for play, forward step, or forward seek. Request includes `target_source_index`, `client_operation_id`, and `expected_revision`. The target must be strictly later than the committed cursor, match an available resolved-manifest candle, and not exceed the last replay-period candle; backward movement uses the guarded replay-position route. The service processes every available one-minute candle after the current cursor through the target in pinned source order, including all pending fills, protective exits, costs, and position changes. No source candle is skipped because the UI made a jump; missing timestamps do not synthesize bars. Existing protective orders are checked on each eligible candle. Entry-fill candle range is not used for that entry's bracket. If both the stop and target of one OCO bracket are touched in one candle, the stop fills first. Simultaneous fills/order eligibility use persisted submission sequence, then stable order id as tie-break.

When the target is the final eligible replay-period candle, the operation first processes that candle, cancels remaining pending entry orders, closes remaining open positions at the final candle close with configured costs, persists resulting closed trades, and atomically marks the run `complete`. Completion is inspectable; further order submissions, cursor movement, and cost changes return conflict until reset or deletion.

### POST /api/backtest/runs/{run_id}/simulation/reset

Requires explicit `confirmed: true`, a unique operation key, and expected revision. The reset is idempotent. Its run-level CAS commit increments reset generation, clears the backward-navigation lock, preserves the latest cost profile and immutable initial balance/risk settings, resets derived current balance to the initial balance, sets status back to `ready`, and restores the first eligible replay-period cursor. Old-generation orders, fills/allocation Executions, positions, analytics outputs, and fully closed simulated Trades become invisible at that commit and are then physically removed idempotently; the internal operation-id journal is retained so retries remain idempotent. The run's pending-operation gate blocks new mutations until cleanup finishes. This action is available for ready or complete runs. A reset interrupted during cleanup resumes safely after restart, and retrying by operation key returns the same reset result.

### Forex conversion and closed Trade visibility

Every closing fill preserves native quote-currency P&L. A `quote_to_usd_rate` is USD per one unit of the instrument's quote currency at that exit; USD-quoted instruments use 1. Initial risk uses the corresponding entry-event rate. Use the latest completed one-minute conversion candle with close time no later than the fill event; conversion source/date references are pinned by the run manifest. Manual-source runs may use their configured fallback rate when no eligible historical rate exists. Because OHLC does not reveal the exact intra-minute trigger time, timestamp wick/gap fills at the triggering candle's opening instant, manual close at the current cursor candle's close, and timestamp final forced closes at the final candle's close. Each extended `Execution` fill stores its own event rate and native/USD realized amounts; the conventional Trade stores exact aggregate gross/net totals. Do not use the Trade model's single scalar rate to recompute a Backtest trade's multiple exit conversions. If no valid as-of rate or permitted manual fallback exists, reject the affected order/close operation with a clear error; do not commit its candle advance or state change and never substitute a scalar latest rate or 1 for non-USD quote currency. Once a position fully closes, create one ordinary `Trade` with `status=closed` under the run's dedicated Backtest account and stable simulation id. Partially open exposure remains in simulation state and does not appear in Journal/closed-only analytics. Backtest Journal and analytics can then use existing closed-trade account scoping; Blind presentation is derived from the linked run.

## Configured manual trades

### GET /api/trades/conversion-rate

Requires authentication and the Real workspace. Query parameters are `symbol` and timezone-aware ISO 8601 `event_time`. The endpoint resolves a Settings instrument or supported legacy Forex symbol and returns HTTP 200 with `canonical_symbol`, `quote_currency`, `available`, `quote_to_usd_rate`, `quote_currency_unit_scale`, `rate_time`, `route`, and `reason`. An unavailable quote is represented by `available: false`, a null rate/time, and a user-facing reason; it is not an HTTP error. USD quote currency returns the identity rate of 1. Historical rates use the latest completed one-minute candle close at or before the event time. The lookup examines the event UTC date and up to the preceding seven UTC dates; every leg in a direct, inverse, or configured shortest route must have an eligible candle. A multi-leg result reports the oldest leg close as the conservative common `rate_time`, along with per-leg rates and times. Currency-unit scaling is applied to the returned USD-per-quote-unit rate.

Example response:

~~~json
{
  "canonical_symbol": "USD-JPY",
  "available": true,
  "quote_currency": "JPY",
  "quote_to_usd_rate": 0.00667,
  "quote_currency_unit_scale": 1,
  "rate_time": "2026-09-21T14:31:00+00:00",
  "route": [{
    "instrument": "USD-JPY",
    "from_currency": "JPY",
    "to_currency": "USD",
    "direction": "inverse",
    "rate": 0.00667,
    "rate_time": "2026-09-21T14:31:00+00:00"
  }],
  "reason": null
}
~~~

### POST /api/trades

Requires authentication and the Real workspace. The free-text `symbol` accepts a case-insensitive Settings symbol and slash/dash alias. If a configured mapping resolves, the server stores the canonical symbol and preserves the entered value in `raw_symbol`; it validates complete Settings sizing rules and uses configured contract size, minimum lots, lot increment, tick size, and precision. Submit `lot_size`, side, entry/exit prices and entry/exit timestamps, plus an optional positive `quote_to_usd_rate` for non-USD quote currencies. USD quotes use 1. A supplied rate remains a valid user override when historical data is unavailable; the server records it as historical only when it exactly matches the eligible historical result, otherwise as manual. If no rate is supplied, a historical rate must be available or the request is rejected. Native P&L is stored in quote currency and USD P&L uses the event-time quote conversion. The saved trade includes configured instrument metadata, raw/canonical symbols, conversion source/time/route, and quote-unit scale.

When no Settings mapping applies, preserve the existing legacy Forex and futures flows. Futures use `total_quantity` and the existing point-value calculation; `lot_size` and quote-rate overrides are only accepted for configured instruments. Incomplete or unsupported Settings rows are rejected instead of falling through to guessed sizing.

## Status and error behavior

- Selecting-period and preparing represent durable preparation; ready is playable; complete is retained, inspectable, and read-only; `deleting` is a temporary, non-playable state retained only while confirmed cleanup is pending.
- Interrupted preparation stays preparing. A separate worker claims durable MongoDB jobs with expiring leases; after a worker restart or lease expiry, the job resumes from the last completed UTC-date checkpoint. Manual retry requeues the same job.
- Failed and no-data runs are reported and then deleted with their account.
- A complete run rejects orders, cursor movement, and cost updates until reset. Reset preserves its cost profile and clears only that run's simulated data and closed simulated trades.
- Confirmed user deletion removes the dedicated account and its linked trades, while a durable `deleting` run state fences writes and lets the worker finish idempotent cleanup after restart.
- Invalid input and out-of-range requests use the existing validation error shape.
- Unknown or non-owned run resources return not found.
- Drawing revision conflicts return 409 with the latest revision.
- All writes are owner-checked and idempotent where retry/repeated save semantics require it.






