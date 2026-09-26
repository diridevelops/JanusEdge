# Backtest API Contract

This contract describes the authenticated Flask API used by the React Backtest pages and CandleKit adapters. Route names are feature-local planning decisions; implementation should follow JanusEdge’s existing API prefix and error conventions.

## Authentication and ownership

All endpoints require the existing JWT bearer authentication. The backend derives user_id from the JWT and applies owner filtering to every run, candle, account, replay-position, and drawing operation. Request bodies never accept a user_id. Access to another user’s resource returns the same not-found behavior as an unknown id.

Timestamps are UTC epoch milliseconds. Candle bars are returned in chronological order with one-minute source interval.

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

The backend validates the supported instrument, date range, timezone, and inclusive one-calendar-year limit. For a February 29 start, February 28 of the following year is the latest permitted end date. It converts the selected local date boundaries to the equivalent UTC selection, then creates the run and exactly one associated Backtest account before starting preparation.

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

Return 202 while preparation continues. Invalid input uses the app’s validation-error format. If preparation later returns no data or fails, report the outcome with the instrument/range and remove the run/account as specified by the feature requirements.

## List and inspect runs

### GET /api/backtest/runs

Returns the authenticated user’s preparing and ready runs, newest first. Each list entry includes id, instrument, selected date range, generated account label, status, and preparation progress (`stage` plus a percentage when measurable, otherwise null). Failed/no-data records are not retained.

### GET /api/backtest/runs/{run_id}

Returns the owned run detail, account label, available candle coverage, empty dates and partial-gap summary, saved cursor, persisted chart-tab configurations, and status. A preparing run remains on the list page and has no chart detail data. A ready run has at least one chart tab; a newly ready run receives a default 1m tab if the user has not selected another interval.

## Preparation result notices

### GET /api/backtest/notices

Returns the authenticated user's undismissed no-data and failure notices, newest first. A notice includes its instrument, selected date range, outcome, and next action. Notices remain after the failed/no-data run and account are deleted.

### DELETE /api/backtest/notices/{notice_id}

Dismisses the owned notice. This does not restore or retain the deleted run or account.

## Persist chart-tab configuration

### PUT /api/backtest/runs/{run_id}/chart-tabs

Replaces the owned run's persisted chart-tab configuration. The list has no fixed v1 maximum and MUST contain at least one tab. Each entry contains a stable tab id, display position, and selected interval in whole minutes from 1 through 1,440. Invalid intervals return the existing validation error shape; a rejected update leaves the last valid tab settings unchanged.

~~~json
{
  "tabs": [
    {"id": "tab-1", "position": 0, "interval_minutes": 1},
    {"id": "tab-2", "position": 1, "interval_minutes": 60}
  ]
}
~~~

The endpoint returns the saved tab list, which is included in the run detail response and restored after navigation or reload.

## Retry an interrupted run

### POST /api/backtest/runs/{run_id}/retry

Restarts preparation for the existing owned preparing run and returns 202 with that same run id and account id. This operation is idempotent with respect to run/account creation. It does not permit retrying a ready run.

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

## Persist drawing state

### GET /api/backtest/runs/{run_id}/drawings?interval_minutes={n}

Returns the owned drawing payload for the given interval, or null when no saved set exists.

Example response:

~~~json
{
  "interval_minutes": 5,
  "candlekit_version": "0.1.1",
  "schema_version": 1,
  "revision": 3,
  "serialized_state": null
}
~~~

### PUT /api/backtest/runs/{run_id}/drawings?interval_minutes={n}

Request:

~~~json
{
  "candlekit_version": "0.1.1",
  "schema_version": 1,
  "expected_revision": 3,
  "serialized_state": "{}"
}
~~~

The server validates interval limits, ownership, payload size, and JSON shape, then upserts the opaque exported string by user/run/interval. Return the persisted payload and incremented revision. A revision conflict returns 409 so another open tab cannot silently overwrite a newer drawing set. An empty drawing set is a valid saved state. Preserve replay-aware drawing visibility if provided by the pinned CandleKit artifact; otherwise the frontend filters drawings with any time anchor later than the replay cursor and shows them again when all anchors are at or before it. This fallback does not use drawing creation or edit time and does not alter the persisted payload.

## Status and error behavior

- Preparing and ready are the only retained run statuses.
- Interrupted preparation stays preparing and can be retried.
- Failed and no-data runs are reported and then deleted with their account.
- Invalid input and out-of-range requests use the existing validation error shape.
- Unknown or non-owned run resources return not found.
- Drawing revision conflicts return 409 with the latest revision.
- All writes are owner-checked and idempotent where retry/repeated save semantics require it.






