# API Reference

## Base Notes

- Base API namespace: `/api`
- Authentication mechanism: JWT bearer token in the `Authorization` header
- Public endpoints: `GET /api/auth/health`, `POST /api/auth/register`, `POST /api/auth/login`
- All other endpoints currently require authentication

Unless otherwise noted, IDs are MongoDB ObjectId strings serialized as plain strings.

## Authentication

| Method | Path | Auth | Purpose | Request | Response |
| --- | --- | --- | --- | --- | --- |
| GET | `/api/auth/health` | No | Basic health check | None | `{ "status": "ok" }` |
| POST | `/api/auth/register` | No | Create a new user | JSON with `username`, `password`, `timezone` | `{ token, user }` |
| POST | `/api/auth/login` | No | Log in | JSON with `username`, `password` | `{ token, user }` |
| GET | `/api/auth/me` | Yes | Get current profile | None | Direct serialized user object |
| POST | `/api/auth/logout` | Yes | Client-side logout acknowledgement | None | `{ "message": "Logged out." }` |
| POST | `/api/auth/change-password` | Yes | Change password | JSON with `current_password`, `new_password` | `{ "message": "Password changed successfully." }` |
| PUT | `/api/auth/timezone` | Yes | Update trading timezone | JSON with `timezone` | Direct serialized user object |
| PUT | `/api/auth/display-timezone` | Yes | Update display timezone | JSON with `display_timezone` | Direct serialized user object |
| PUT | `/api/auth/starting-equity` | Yes | Update starting equity used by simulations | JSON with `starting_equity` | Direct serialized user object |
| PUT | `/api/auth/symbol-mappings` | Yes | Replace user symbol mappings | JSON with `symbol_mappings` | Direct serialized user object |
| GET | `/api/auth/export` | Yes | Export a portable backup ZIP | None | ZIP download |
| POST | `/api/auth/restore` | Yes | Restore a portable backup ZIP into the current user | `multipart/form-data` with `file` | `{ message, summary }` |

### User response shape

Where the backend returns a serialized user object, the frontend currently expects fields like:

```json
{
  "id": "...",
  "username": "...",
  "timezone": "America/New_York",
  "display_timezone": "America/New_York",
  "starting_equity": 10000,
  "symbol_mappings": {},
  "created_at": "..."
}
```

## Imports

| Method | Path | Auth | Purpose | Request | Response |
| --- | --- | --- | --- | --- | --- |
| POST | `/api/imports/upload` | Yes | Upload and parse a CSV | `multipart/form-data` with `file` | `{ platform, executions, errors, warnings, row_count, file_hash, file_name, file_size, column_mapping }` |
| POST | `/api/imports/reconstruct` | Yes | Reconstruct trades from parsed executions | JSON with `executions` and optional `method` | `{ trades: [...] }` |
| POST | `/api/imports/finalize` | Yes | Persist a completed import | JSON with `file_hash`, `platform`, `file_name`, `file_size`, `reconstruction_method`, `trades`, `executions`, and `column_mapping` | `{ import_batch_id, file_name, platform, trades_imported, executions_imported }` |
| GET | `/api/imports/batches` | Yes | List import batches for the current user | None | `{ batches: [...] }` |
| GET | `/api/imports/batches/:batch_id` | Yes | Get one import batch with related trades and executions | Path parameter `batch_id` | `{ batch, trades, executions }` |
| DELETE | `/api/imports/batches/:batch_id` | Yes | Delete an import batch and related trade data | Path parameter `batch_id` | `{ "message": "Import batch deleted." }` |

### Upload response notes

- `executions` is a normalized preview array, not yet persisted.
- `errors` includes row-level parse or validation issues.
- the backend returns `row_count`; the frontend derives convenience fields such as `total_rows` and `parsed_rows`

### Reconstruct response notes

The trade preview array is inferred from the import wizard and includes fields such as:

- `index`
- `symbol`
- `raw_symbol`
- `side`
- `total_quantity`
- `avg_entry_price`
- `avg_exit_price`
- `gross_pnl`
- `net_pnl`
- `entry_time`
- `exit_time`
- `execution_count`
- `executions`

If you need an exact stable schema here, treat it as TODO because the preview response is shaped by serializer helpers rather than a separate public schema contract.

## Trades

| Method | Path | Auth | Purpose | Request | Response |
| --- | --- | --- | --- | --- | --- |
| GET | `/api/trades` | Yes | List trades with filters and pagination | Query params: `account`, `symbol`, `side`, `tag`, `date_from`, `date_to`, `page`, `per_page`, `sort_by`, `sort_dir` | `{ trades, total, page, per_page, pages }` |
| GET | `/api/trades/:trade_id` | Yes | Get one trade with executions | Path parameter `trade_id` | `{ trade, executions }` |
| POST | `/api/trades` | Yes | Create a manual trade | JSON with `symbol`, `side`, `total_quantity`, `entry_price`, `exit_price`, `entry_time`, `exit_time`, optional `fee`, `initial_risk`, `account`, `tags`, `notes` | `{ trade }` |
| PUT | `/api/trades/:trade_id` | Yes | Update journaling and risk fields on a trade | JSON may include `fee`, `fee_source`, `initial_risk`, `strategy`, `pre_trade_notes`, `post_trade_notes`, `tag_ids`, `wish_stop_price`, `target_price` | `{ trade }` |
| DELETE | `/api/trades/:trade_id` | Yes | Delete a trade and related data | Path parameter `trade_id` | `{ "message": "Trade deleted." }` |
| POST | `/api/trades/:trade_id/restore` | Yes | Restore a trade with `status: deleted` | Path parameter `trade_id` | `{ trade }` |
| GET | `/api/trades/search` | Yes | Full-text trade search | Query param `q` | `{ trades: [...] }` |
| GET | `/api/trades/symbols` | Yes | List distinct symbols from closed trades | None | `{ symbols: [...] }` |

### Trade list notes

- `sort_by=r_multiple` is handled specially in the backend.
- `account` can be either an account ObjectId or an account name.
- `tag` can be either a tag ObjectId or a tag name.
- each returned trade currently includes a computed `market_data_cached` boolean.

### Delete and restore note

The restore route exists, but the current delete implementation permanently removes the trade document, related executions, and related media. In normal current usage, `POST /restore` is effectively a legacy or TODO endpoint.

## Accounts

| Method | Path | Auth | Purpose | Request | Response |
| --- | --- | --- | --- | --- | --- |
| GET | `/api/accounts` | Yes | List all trade accounts for the current user | None | `{ accounts: [...] }` |
| PUT | `/api/accounts/:account_id` | Yes | Update a trade account | JSON with any of `display_name`, `notes`, `status` | `{ account }` |

## Executions

| Method | Path | Auth | Purpose | Request | Response |
| --- | --- | --- | --- | --- | --- |
| GET | `/api/executions` | Yes | List executions with pagination | Query params: `trade_id`, `symbol`, `date_from`, `date_to`, `page`, `per_page` | `{ executions, total, page, per_page }` |
| GET | `/api/executions/:execution_id` | Yes | Get one execution | Path parameter `execution_id` | `{ execution }` |

Note: the route docstring mentions an `account` query parameter, but the current implementation does not apply any account filter in code. Treat account filtering here as TODO.

## Tags

| Method | Path | Auth | Purpose | Request | Response |
| --- | --- | --- | --- | --- | --- |
| GET | `/api/tags` | Yes | List tags | None | `{ tags: [...] }` |
| POST | `/api/tags` | Yes | Create a tag | JSON with `name` and optional `category`, `color` | `{ tag }` |
| PUT | `/api/tags/:tag_id` | Yes | Update a tag | JSON with any of `name`, `category`, `color` | `{ tag }` |
| DELETE | `/api/tags/:tag_id` | Yes | Delete a tag | Path parameter `tag_id` | `{ "message": "Tag deleted." }` |

## Market Data

| Method | Path | Auth | Purpose | Request | Response |
| --- | --- | --- | --- | --- | --- |
| GET | `/api/market-data/ohlc` | Yes | Return OHLC data for charting | Query params: `symbol` required, optional `interval`, `start`, `end`, `raw_symbol`, `force_refresh` | `{ ohlc_data: [...] }` |

The frontend currently expects each OHLC point to look like:

```json
{
  "time": 1739145600,
  "open": 0.0,
  "high": 0.0,
  "low": 0.0,
  "close": 0.0,
  "volume": 0
}
```

## Analytics

All analytics endpoints accept the common filter params `account`, `symbol`, `side`, `tag`, `date_from`, `date_to`. Some also accept `timezone`.

| Method | Path | Auth | Purpose | Request | Response |
| --- | --- | --- | --- | --- | --- |
| GET | `/api/analytics/summary` | Yes | Summary metrics for closed trades | Common query filters | Summary object |
| GET | `/api/analytics/trade-pnls` | Yes | Per-trade net PnL values | Common query filters | Array of objects containing net PnL values |
| GET | `/api/analytics/equity-curve` | Yes | Equity-curve chart data | Common query filters | Array of equity points |
| GET | `/api/analytics/drawdown` | Yes | Drawdown series | Common query filters | Array of drawdown points |
| GET | `/api/analytics/calendar` | Yes | Daily calendar heatmap data | Common query filters | Array of `{ date, net_pnl, gross_pnl, trade_count }` |
| GET | `/api/analytics/distribution` | Yes | Histogram data | Common query filters plus optional `bucket_size` | Array of `{ bucket, count }` |
| GET | `/api/analytics/time-of-day` | Yes | Hour-of-day performance | Common query filters | Array of `{ hour, trade_count, net_pnl, avg_pnl, win_rate }` |
| GET | `/api/analytics/by-tag` | Yes | Grouped metrics by tag | Common query filters | Array of per-tag metrics |
| GET | `/api/analytics/appt-by-day-of-week` | Yes | APPT by weekday | Common query filters plus optional `timezone` | Array of `{ day_of_week, appt, trade_count, net_pnl }` |
| GET | `/api/analytics/appt-by-timeframe` | Yes | APPT by 15-minute entry bucket | Common query filters plus optional `timezone` | Array of `{ timespan_start, appt, trade_count, net_pnl }` |
| GET | `/api/analytics/evolution` | Yes | Running and rolling metrics | Common query filters plus `window`, `min_side_count` | Array of evolution points |
| POST | `/api/analytics/monte-carlo` | Yes | Run Monte Carlo simulations | JSON body with simulator params; common query filters still apply | `{ chart_data, metrics, metadata }` |

### Summary response fields

The frontend currently depends on summary fields including:

- `total_trades`
- `winners`
- `losers`
- `breakeven`
- `win_rate`
- `total_gross_pnl`
- `total_net_pnl`
- `total_fees`
- `avg_winner`
- `avg_loser`
- `largest_win`
- `largest_loss`
- `profit_factor`
- `expectancy`
- `expectancy_r`
- `wl_ratio_r`
- `avg_holding_time_seconds`
- `avg_executions`
- `appt`
- `pl_ratio`
- `median_r`
- `profit_factor_r`
- `avg_initial_risk`

### Monte Carlo request body

The endpoint accepts camelCase or snake_case names for the main simulator fields. The frontend currently sends:

```json
{
  "mode": "bootstrap | parametric",
  "startingEquity": 10000,
  "winRate": 50,
  "winLossRatio": 2,
  "riskFixed": 200,
  "riskPct": 1,
  "minRisk": 50,
  "riskMode": "fixed | percent",
  "seed": 42,
  "numTrades": 500
}
```

## Media

| Method | Path | Auth | Purpose | Request | Response |
| --- | --- | --- | --- | --- | --- |
| POST | `/api/trades/:trade_id/media` | Yes | Upload a trade attachment | `multipart/form-data` with `file` | `{ media }` |
| GET | `/api/trades/:trade_id/media` | Yes | List media for a trade | Path parameter `trade_id` | `{ media: [...] }` |
| GET | `/api/media/:media_id/url` | Yes | Get a presigned download URL | Path parameter `media_id` | `{ url }` |
| DELETE | `/api/media/:media_id` | Yes | Delete a media attachment | Path parameter `media_id` | `{ "message": "Media deleted." }` |

Current server-side constraints:

- max file size `500 MB`
- max `20` attachments per trade
- allowed content types: JPEG, PNG, GIF, WebP, MP4, WebM, QuickTime

## What-If

What-if endpoints use the same filter set as trades and analytics: `account`, `symbol`, `side`, `tag`, `date_from`, `date_to`.

| Method | Path | Auth | Purpose | Request | Response |
| --- | --- | --- | --- | --- | --- |
| GET | `/api/whatif/stop-analysis` | Yes | Return R-normalized stop-overshoot statistics | Query filters; symbol is effectively required by the backend logic | Stop-analysis object |
| GET | `/api/whatif/wicked-out-trades` | Yes | List wicked-out trades and whether OHLC data exists | Query filters | `{ trades: [...] }` |
| POST | `/api/whatif/simulate` | Yes | Run wider-stop simulation | JSON body with `r_widening`; query filters still apply | Simulation response |

### Stop-analysis response

The frontend currently expects fields like:

```json
{
  "count": 0,
  "mean": 0.0,
  "median": 0.0,
  "p75": 0.0,
  "p90": 0.0,
  "p95": 0.0,
  "iqr": 0.0,
  "confidence_intervals": {
    "mean": { "lower": 0.0, "upper": 0.0 }
  },
  "details": []
}
```

### Simulation request and response

Request body:

```json
{
  "r_widening": 1.0
}
```

Response shape inferred from frontend types:

```json
{
  "original": {
    "total_pnl": 0.0,
    "avg_pnl": 0.0,
    "win_rate": 0.0,
    "total_winners": 0,
    "total_losers": 0,
    "profit_factor": 0.0,
    "expectancy_r": 0.0
  },
  "what_if": {
    "total_pnl": 0.0,
    "avg_pnl": 0.0,
    "win_rate": 0.0,
    "total_winners": 0,
    "total_losers": 0,
    "profit_factor": 0.0,
    "expectancy_r": 0.0
  },
  "trades_total": 0,
  "trades_converted": 0,
  "trades_simulated": 0,
  "trades_skipped": 0,
  "details": []
}
```

## Error Handling

The backend uses shared error handling and custom exceptions. In practice, many validation failures return a JSON body containing at least a human-readable message. Exact error payload shape is not fully standardized in a single public schema file, so if you are integrating a new client, treat error-body shape as partially inferred and validate against live responses.