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

The backend validates the submitted instrument against the current catalog from the pinned downloader, along with the date range, timezone, and inclusive one-calendar-year limit. For a February 29 start, February 28 of the following year is the latest permitted end date. It converts the selected local date boundaries to the equivalent UTC selection, then creates the run, exactly one associated Backtest account, and one durable MongoDB preparation job. Preparation is handled by a separate worker process; the HTTP request does not run the download.

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

Returns the authenticated user’s preparing, ready, and deleting runs, newest first. Each list entry includes id, instrument, selected date range, generated account label, status, and preparation progress (`stage` plus a percentage when measurable, otherwise null). A deleting run is shown as pending cleanup and cannot be opened. The frontend polls this endpoint every five seconds while at least one run is preparing or deleting and stops when none are. Progress is read from MongoDB state updated by the worker. Failed/no-data records are not retained.

### GET /api/backtest/runs/{run_id}

Returns the owned run detail, account label, available candle coverage, empty dates and partial-gap summary, saved cursor, and status. A preparing or deleting run remains on the list page and has no playable chart detail. Its persisted cursor is initialized to source index zero and the timestamp of its first available candle when the run becomes ready. Chart workspace state is loaded through the dedicated chart-workspace routes below.

### DELETE /api/backtest/runs/{run_id}

Permanently deletes an owned preparing or ready run. The frontend must require explicit confirmation before calling this endpoint and explain that the run's dedicated Backtest account and all trades linked to it will also be removed. The request has no user or account identifier; the server derives ownership and the one-to-one account association from the run record.

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

Returns the authenticated user's undismissed no-data and failure notices, newest first. A notice includes its instrument, selected date range, outcome, and next action. Notices remain after the failed/no-data run and account are deleted.

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

Returns the sorted UTC dates that contain one or more candles in the immutable snapshot. This supports CandleKit’s day-oriented listDatesBefore/listDatesAfter behavior. Dates with no data are omitted and are not replaced by synthetic candles.

Example response:

~~~json
{
  "dates": ["2026-01-02", "2026-01-05", "2026-01-06"]
}
~~~

### GET /api/backtest/runs/{run_id}/candles?date={utc_date}

Returns one UTC day of the run’s one-minute snapshot. An empty array is valid for a requested date with no candles. A date outside the run’s data selection returns validation/not-found according to the existing API error convention.

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

The server validates that the run is ready and the index/time pair matches the immutable snapshot. When expected_revision matches, it accepts any valid selected cursor, including an intentional step-back, and increments the revision. A stale revision returns 409. The client serializes/coalesces writes so an older in-flight request cannot overwrite a later selection, and flushes on pause, seek, and route exit.

When a run first becomes ready, the server persists `source_candle_index: 0`, the first available candle’s `time_ms`, and revision zero in the same run-document update that changes status to ready. The frontend uses this stored cursor and starts playback paused.

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






