# Backtest API Contract

This contract describes the authenticated Flask API used by the React Backtest pages and CandleKit adapters. Route names are feature-local planning decisions; implementation should follow JanusEdge’s existing API prefix and error conventions.

## Authentication and ownership

All endpoints require the existing JWT bearer authentication. The backend derives user_id from the JWT and applies owner filtering to every run, preparation job, candle, account, trade, replay-position, deletion, and drawing operation. Request bodies never accept a user_id. Access to another user’s resource returns the same not-found behavior as an unknown id.

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

## Create a run

### POST /api/backtest/runs

Request:

~~~json
{
  "instrument": "EUR-USD",
  "start_date": "2026-01-01",
  "end_date": "2026-01-10",
  "display_timezone": "Europe/Rome"
}
~~~

The backend validates the submitted instrument against the current catalog from the pinned downloader, along with the selected replay date range, timezone, and inclusive one-calendar-year limit. For a February 29 start, February 28 of the following year is the latest permitted end date. The selected local-day boundaries define the replay window. The backend also calculates a warm-up start one calendar month before the selected local start date, clamping to the final valid day of the preceding month, then converts the warm-up and selected replay boundaries to UTC. The user's dates and one-year limit are unchanged by this extra source interval. The API then creates the run, exactly one associated Backtest account, and one durable MongoDB preparation job. Preparation is handled by a separate worker process; the HTTP request does not run the download.

The manual request above remains unchanged. Random selection instead sends:

~~~json
{
  "instrument": "EUR-USD",
  "display_timezone": "Europe/Rome",
  "period_selection": "random",
  "period_months": 3
}
~~~

`period_months` must be 1, 3, 6, or 12; `start_date` and `end_date` are omitted. The backend captures yesterday in the configured display timezone when accepting the request, then creates a `selecting_period` run with null dates and no account and enqueues a durable selection job. Its initial response is:

~~~json
{
  "run": {
    "id": "run-id",
    "instrument": "EUR-USD",
    "period_selection": "random",
    "period_months": 3,
    "requested_start_date": null,
    "requested_end_date": null,
    "status": "selecting_period",
    "account_id": null,
    "account_label": null,
    "progress": {"stage": "selecting_period", "percent": null}
  }
}
~~~

The worker chooses eligible years randomly without replacement and probes at most ten distinct random eligible dates per year. A probe fetches the UTC day or days intersecting that local date and accepts a candidate only when a COMB one-minute candle falls inside the exact replay local-day UTC bounds. After ten empty probes, it discards the year and selects another untried eligible year. It does not treat provider errors as empty days. On a hit, it persists the final local dates, creates the one date-labeled account, and enters the normal warm-up/preparation flow. The inclusive end is the day before adding the selected calendar months with month-end clamping. If every year is exhausted, the run/account/job are removed and a dismissible notice identifies the instrument and duration. A start-day hit does not guarantee candles later in the selected period; existing coverage, gap, and readiness rules still apply. The cutoff and attempts remain fixed/durable across worker restart, and deleting a selecting-period run fences account creation.

Accepted response:

~~~json
{
  "run": {
    "id": "run-id",
    "instrument": "EUR-USD",
    "status": "preparing",
    "account_id": "account-id",
    "progress": {
      "stage": "downloading",
      "percent": null
    }
  }
}
~~~

Return 202 while preparation continues. Invalid input uses the app’s validation-error format. If the catalog cannot be fetched, return a service error and create no run/account. If preparation later returns no data or fails terminally, report the outcome with the instrument/range and remove the run, account, job, and staging data as specified by the feature requirements. A worker restart or expired lease is recoverable interruption, not a terminal failure.

## List and inspect runs

### GET /api/backtest/runs

Returns the authenticated user’s selecting-period, preparing, ready, and deleting runs, newest first. Each list entry includes id, instrument, period selection, nullable selected dates, nullable account label, status, and progress (`stage` plus a percentage when measurable, otherwise null). Until selection resolves, the frontend shows the instrument and selection status without dates or an account. A deleting run is shown as pending cleanup and cannot be opened. The frontend polls this endpoint every five seconds while at least one run is selecting-period, preparing, or deleting and stops when none are. Progress is read from MongoDB state updated by the worker. Failed/no-data records are not retained.

### GET /api/backtest/runs/{run_id}

Returns the owned run detail, nullable account label/dates while selection is pending, selected replay-period coverage, warm-up coverage, saved cursor, and status. A selecting-period, preparing, or deleting run remains on the list page and has no playable chart detail. When the run becomes ready, its persisted cursor is initialized to the snapshot index and timestamp of the first available candle at or after the selected replay start; this index can be greater than zero because the snapshot includes warm-up candles. Readiness requires at least one candle in the selected replay period. Chart workspace state is loaded through the dedicated chart-workspace routes below.

### DELETE /api/backtest/runs/{run_id}

Permanently deletes an owned selecting-period, preparing, or ready run. The frontend must require explicit confirmation before calling this endpoint and explain that the run's dedicated Backtest account, if created, and all trades linked to it will also be removed. The request has no user or account identifier; the server derives ownership and the one-to-one account association from the run record.

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

The worker treats `deleting` as a cancellation fence: preparation, replay-position writes, chart-workspace writes, and drawing writes return the existing conflict error for a run that is being deleted and cannot publish or mutate that run. It resumes cleanup after restart and physically removes every object under the run's MinIO prefix, including staged and immutable candle objects and any unreferenced objects, then verifies the prefix is empty. It also removes the preparation job, replay cursor, chart tabs/workspace, drawings, every trade linked to the dedicated account (including trade-owned dependent records and files), and the account. Remove the run record carrying the `deleting` marker only after all associated MongoDB records and MinIO objects are physically gone. The run disappearing from `GET /api/backtest/runs` is the completion signal; do not report success while cleanup is pending or resources are merely hidden. Cleanup is idempotent. It must not delete another run's or any Real account's records, even when labels or instruments match. User-initiated deletion does not create a preparation-failure notice.

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

## Retry an interrupted run

### POST /api/backtest/runs/{run_id}/retry

Requeues the existing owned preparing run’s durable job and returns 202 with that same run id and account id. This operation is idempotent with respect to job/run/account creation. The worker resumes after the latest completed UTC-date checkpoint and may fetch again only an incomplete date. Worker recovery after an expired lease uses the same checkpoint without requiring this endpoint. Retry does not permit a ready run.

## CandleKit ReplayDataSource

The frontend adapter exposes the following CandleKit source operations through the authenticated API.

### GET /api/backtest/runs/{run_id}/candle-dates?before={utc_date}&after={utc_date}

Returns the sorted UTC dates that contain one or more candles in the immutable snapshot, including the preceding warm-up period. This supports CandleKit’s day-oriented listDatesBefore/listDatesAfter behavior. Dates with no data are omitted and are not replaced by synthetic candles. The snapshot's selected replay start remains separately identified by the run detail and replay-start index.

Example response:

~~~json
{
  "dates": ["2026-01-02", "2026-01-05", "2026-01-06"]
}
~~~

### GET /api/backtest/runs/{run_id}/candles?date={utc_date}

Returns one UTC day of the run’s one-minute snapshot. An empty array is valid for a requested date with no candles. A date outside `[context_start_utc_ms, end_utc_ms)` returns validation/not-found according to the existing API error convention. This source data includes warm-up candles; the frontend may display candles before the replay cursor as historical context, but MUST filter replay-period candles after the current cursor.

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

`open`, `high`, `low`, and `close` are component-wise arithmetic midpoints of the corresponding COMB BID/ASK OHLC values. Since BID and ASK minute extrema are aggregated independently, the midpoint high and low are estimates rather than exact tick-level midpoint extrema. `volume` is summed bid and ask quoted liquidity, not executed trade volume; the replay UI labels it accordingly.

## Save the shared replay position

### PUT /api/backtest/runs/{run_id}/replay-position

Request:

~~~json
{
  "source_candle_index": 1234,
  "time_ms": 1767308400000,
  "expected_revision": 8
}
~~~

The server validates that the run is ready and the index/time pair matches the immutable snapshot. A valid replay cursor MUST be at or after `snapshot.replay_start_source_index` and no later than the last candle in the selected replay period; warm-up indexes are not valid cursor positions. When expected_revision matches, it accepts any valid replay cursor, including an intentional step-back, and increments the revision. A stale revision returns 409. The client clamps a seek before the selected replay start to the first eligible replay candle, serializes/coalesces writes so an older in-flight request cannot overwrite a later selection, and flushes on pause, seek, and route exit.

When a run first becomes ready, the server persists `source_candle_index: replay_start_source_index`, the first eligible replay candle’s `time_ms`, and revision zero in the same run-document update that changes status to ready. The frontend uses this stored cursor and starts playback paused. All snapshot candles before this index are loaded as historical chart context but do not contribute to replay progress, forward/backward stepping, seeking, or completion.

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

## Status and error behavior

- Preparing and ready are the normal retained run statuses. `deleting` is a temporary, non-playable state retained only while confirmed cleanup is pending.
- Interrupted preparation stays preparing. A separate worker claims durable MongoDB jobs with expiring leases; after a worker restart or lease expiry, the job resumes from the last completed UTC-date checkpoint. Manual retry requeues the same job.
- Failed and no-data runs are reported and then deleted with their account.
- Confirmed user deletion removes the dedicated account and its linked trades, while a durable `deleting` run state fences writes and lets the worker finish idempotent cleanup after restart.
- Invalid input and out-of-range requests use the existing validation error shape.
- Unknown or non-owned run resources return not found.
- Drawing revision conflicts return 409 with the latest revision.
- All writes are owner-checked and idempotent where retry/repeated save semantics require it.






