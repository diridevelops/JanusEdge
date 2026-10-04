# Usage Guide

This guide explains how to use Janus Edge as a trader or journal user.

## Index

- [What Janus Edge Helps You Do](#what-janus-edge-helps-you-do)
- [Before You Start](#before-you-start)
- [Main Navigation](#main-navigation)
- [Recommended First Workflow](#recommended-first-workflow)
- [Login And Registration](#login-and-registration)
- [Dashboard](#dashboard)
- [Trades](#trades)
- [Import Trades](#import-trades)
- [Import Market Data](#import-market-data)
- [Backtest Runs](#backtest-runs)
- [Add A Manual Trade](#add-a-manual-trade)
- [Trade Detail Page](#trade-detail-page)
- [Calendar](#calendar)
- [Analytics](#analytics)
- [What-If](#what-if)
- [Settings](#settings)
- [Common Tasks](#common-tasks)
- [Practical Tips](#practical-tips)
- [When Something Looks Wrong](#when-something-looks-wrong)

## What Janus Edge Helps You Do

Janus Edge is built to help you:

- import trades from supported CSV exports
- add trades manually when needed
- review charts, executions, notes, tags, and attachments for each trade
- track performance over time
- study daily and monthly patterns
- test what-if ideas around stop placement and trade outcomes
- replay historical candles and manage simulated orders and positions
- back up your data and restore it later

## Before You Start

You need an account before you can use the app.

On the sign-up screen, enter:

- a username
- a password
- your trading timezone

Your trading timezone matters because some imported files do not include full timezone information.

After you sign in, the main app sections become available.

## Main Navigation

After signing in, the main sidebar gives you these sections:

- Dashboard
- Trades
- Calendar
- Analytics
- What-if
- Settings

Two important actions are not in the sidebar:

- Import Trades: open it from the Trades page
- New Manual Trade: open it from the Trades page

The header's **Real / Backtest** switch changes the workspace. Backtest mode
shows Backtest Runs and simulated trades; Real mode keeps your journal and
manually entered or imported trades separate.

## Recommended First Workflow

If you are new to the app, this is the simplest order to follow:

1. Create your account and sign in.
2. Open Settings and confirm your trading timezone and display timezone.
3. If you need custom lookup behavior, configure point-value symbol mappings separately from explicit market-data mappings.
4. Open Trades and use Import to bring in your CSV files.
5. Review imported trades and open individual trade details.
6. Add notes, tags, fees, risk values, and media.
7. Use Dashboard, Calendar, Analytics, and What-if to study your performance.
8. Export a backup after you have useful data in the app.

## Login And Registration

### Register

Use the Register page to create a new account.

You will enter:

- username
- password
- password confirmation
- trading timezone

If the passwords do not match, or the password is too short, the app will stop you before creating the account.

### Sign In

Use the Login page to access your account with your username and password.

If your session expires, the app sends you back to the login page.

## Dashboard

The Dashboard is your main summary page.

It shows:

- total trades
- net P&L
- win rate (winners ÷ classified winners and losers; breakevens excluded)
- APPT
- expectancy in R
- equity curve
- drawdown
- daily APPT
- daily win rate
- performance by tag

You can filter the dashboard by:

- account
- symbol
- side
- tag
- date range

The page has three tabs:

### Overview

Use this tab for your high-level performance picture.

It includes:

- equity curve
- drawdown
- APPT by day
- win rate by day
- performance by tag table

### Time & Date

Use this tab to see when you tend to trade best or worst.

It groups results by:

- day of week
- time of day

### Evolution

Use this tab to study how your edge changes as more trades are added.

It helps answer questions like:

- Is my edge stable?
- Is performance improving or fading?
- Are recent trades behaving differently from older ones?

## Trades

The Trades page is the main list of all saved trades.

It lets you:

- browse all trades
- filter trades
- sort columns
- move through pages of results
- open a trade detail page
- start an import
- add a manual trade

### Filters On The Trades Page

You can filter by:

- account
- symbol
- side
- tag
- date range

Use Clear Filters to return to the full list.

### Sorting And Table Columns

You can sort the list by clicking table headers.

Useful columns include:

- date
- symbol
- side
- quantity
- entry
- exit
- net P&L
- R-multiple
- duration
- tags
- market-data status

If a trade shows market data as available, stored candles overlap that trade's time window.

## Import Trades

Open the Trades page and click Import.

The import process is a guided wizard with four steps.

### Step 1: Upload CSV Files

You can drag and drop or click to select one or more CSV files.

The current implementation supports:

- NinjaTrader CSV exports
- Quantower CSV exports

### Step 2: Preview Parsed Executions

After upload, the app shows a preview of the parsed executions.

Review:

- detected platform
- file name
- number of rows parsed
- individual executions
- warnings
- parsing errors

If there are row-level problems, they appear in a validation panel so you can decide whether to continue.

### Step 3: Assign Fees And Initial Risk

The app reconstructs trades from executions and then asks you to fill in:

- fee or commission for each trade
- initial risk for each trade

You can enter values:

- one trade at a time
- in bulk for all trades

This is especially useful if your source CSV does not include the values you want to track.

### Step 4: Summary

After finalizing the import, Janus Edge shows a summary of:

- how many trades were created
- winners, losers, and break-even trades
- gross P&L
- total fees
- net P&L

From there you can either:

- import another file
- go to the trade list

## Import Market Data

Open the dedicated market-data import page to upload NinjaTrader tick-data `.txt` exports used by charts, running P&L, and What-if analysis.

Important current behavior:

- the importer does not read the instrument symbol from the file contents
- it derives the raw symbol from the filename stem
- it derives the normalized symbol from the first token of that filename stem

Example:

- `MES 06-26.txt` becomes raw symbol `MES 06-26`
- the normalized symbol guess becomes `MES`

If your file is named differently, fill the override fields before starting the import:

- `Raw Symbol Override`: the full platform/export symbol used for market-data lookup, for example `MES 06-26`
- `Normalized Symbol Override`: the base symbol only, for example `MES`
- imported market data is stored by the normalized instrument symbol, so re-importing the same symbol and trading day replaces the existing stored day instead of creating a second raw-symbol variant

If imported market data does not appear later on trade charts or on the What-if page, the most common cause is that the filename-derived raw symbol did not match the symbol family you expected.

## Backtest Runs

Backtest Runs provides an interactive one-minute historical replay. Switch the
header to **Backtest**, open **Backtest Runs**, and select **New run**. Choose
**Dukascopy** to prepare data from the supported instrument catalog or **Manual
import** to use HistData CSVs. The instrument picker searches without regard to
case or separators, so `EURUSD` matches `EUR-USD`; it preserves the canonical
selected symbol.

### Dukascopy runs

Choose an instrument and either a date range or a random period. The date range
uses the configured display timezone and must be shorter than one calendar
year. Random periods are 1, 3, 6, or 12 months. Preparation runs in the
background; the run list shows progress and opens the replay when the run is
ready. The shared per-user candle cache reuses downloaded UTC dates across
runs, including known empty dates, and fetches only cache misses.

### Manual import runs

Choose **Manual import**, then select an instrument configured in Settings.
The form keeps the same balance, risk, blind-mode, execution-cost, warm-up, and
period fields as Dukascopy mode. It accepts one or more headerless HistData
one-minute CSV files with semicolon-separated columns in this order:

```text
DateTime Stamp;Bar OPEN Bid Quote;Bar HIGH Bid Quote;Bar LOW Bid Quote;Bar CLOSE Bid Quote;Volume
```

The timestamp is interpreted as fixed UTC−5 with no daylight-saving change.
Bid OHLC values are used directly as replay prices, and the supplied volume is
retained. After file selection, the form shows the file date range and the
combined cached/uploaded coverage. You can also create a run from an existing
manual import without uploading the files again. Date choices include only
dates containing candles. Random selection uses imported dates; if the chosen
duration exceeds the available history, it uses the full imported range.
Warm-up uses earlier candles from the same imported dataset.

Manual imports are merged by timestamp. If an upload conflicts with cached
candles, Janus Edge shows the affected dates and asks before replacing those
timestamps. Confirming creates a new dataset revision; runs already created
from an earlier revision keep their original data. The generated Backtest
account label has a `-manual` suffix. For non-USD quote currencies, a fallback
USD-per-quote-unit rate is available for use when eligible historical
conversion data cannot be found.

### Replay controls and simulated positions

The replay advances through one-minute candles. Playback speeds are 1×, 2×, 5×,
15×, and 30×. Use the transport buttons or the keyboard: Left Arrow steps back,
Right Arrow steps forward, and Space toggles play/pause. Arrow-key steps use
the selected speed's step size (one candle at 1×); the step controls remain
available at the latest candle and clamp to the available replay bounds.
Shortcuts are ignored while editing text or using a control that accepts
keyboard input. Replay timestamps use the configured display timezone and a
format such as `Mon Sep 21 2026, 13:45`. Blind mode hides identifying dates and
renders prices relative to the starting reference.

The chart workspace can contain multiple charts with saved intervals, tabs,
layouts, and drawings; every chart shares the run's replay cursor. Supported
chart intervals are 1m, 5m, 15m, and 1h. A chart only uses candles revealed by
the replay. A linked Backtest trade's detail chart reads the run's source data
and ends at the furthest candle reached, even if you rewind the replay.

When an entry fills in the same direction on the same instrument as an open
position, it scales into the oldest matching position. The displayed entry is
the lot-weighted average and its existing stop and target remain in place.
Opposite-side fills continue to scale positions out FIFO. Closed trade details
show the average entry and every execution.

### Missing replay data

Opening a run does not automatically download missing data. If a Dukascopy
cache entry is missing or unreadable, the replay lists the affected
instrument/date pairs. Choose **Download missing data** to restore only those
entries. The refreshed candle history may differ; the replay shows a
dismissible warning while preserving saved orders, fills, positions, and
balance. A missing manual-import revision must be restored by uploading the
original HistData CSV files for that run.

## Add A Manual Trade

Open the Trades page and click New Trade.

Use this when you want to log a trade without importing a CSV file.

You can enter:

- symbol
- long or short side
- quantity for futures, or lot size for a configured forex pair (minimum `0.001` lots)
- entry price
- exit price
- entry time
- exit time
- fee
- initial risk
- account name
- notes

After saving, the app opens the new trade detail page automatically.

For an instrument in the Settings sizing table, the form accepts its canonical
symbol or a slash/dash alias and saves the canonical symbol while retaining
the entered text as `raw_symbol`. The row supplies contract size, lot limits,
tick size, and price precision. The trade stores signed native quote-currency
P&L while `gross_pnl` and `net_pnl` remain USD values for dashboards and
analytics. If the quote currency is not USD, the form looks up a completed
one-minute conversion candle at or before the exit time and pre-fills the
USD-per-quote-unit rate when available. You can edit the rate; if no historical
rate is available, enter one manually to submit. USD quotes use a rate of 1.
Legacy Forex and futures entry remain supported when no Settings sizing row
matches.

## Trade Detail Page

Open any trade from the Trades list to see its detail page.

This is where you do most of your journaling and review work.

### Trade Summary

At the top of the page you can review:

- quantity
- average entry and exit prices
- gross P&L
- fees
- net P&L
- initial risk
- R-multiple
- duration

Forex trades additionally show lot size, pair-precision prices, signed pips,
native quote-currency P&L, and the quote-to-USD rate.

### Price Chart

The chart shows the trade day with your executions plotted on top of market data.

Use it to:

- review context around entry and exit
- switch chart interval inside the chart component
- refresh market data if needed

Important limitation:

- intraday market data is only available for roughly the last two months

If a chart does not load for a symbol, check whether the trade symbol matches an imported dataset directly or whether you need an explicit market-data mapping.

### Running P&L

The trade detail page also includes a Running P&L chart.

It shows:

- time on the x-axis from trade entry to trade exit
- gross P&L in dollars on the y-axis
- live mark-to-market movement based on stored raw ticks
- realized plus unrealized P&L for trades that scale in or out

If the instrument trades in points instead of dollars, the chart converts movement using your configured symbol mapping dollar-value-per-point setting. For forex, it uses the stored contract size and quote-to-USD rate, including fractional lots.

Important limitation:

- the Running P&L chart requires stored raw tick data for that trade window and does not fall back to 1-minute candles

### Media

The Media section lets you attach files to a trade.

You can:

- drag and drop files
- click to upload files
- open attachments in a viewer
- delete attachments

Supported media includes common images and videos.

### Fees & Risk

This panel lets you edit:

- fees
- initial risk

Use it when imported values were missing, inaccurate, or changed later.

### Stop Analysis

This panel lets you record:

- a wishful stop
- a target price

This data is used by the What-if stop-management tools.

In practical terms:

- wishful stop = where you wish your stop had been
- target price = the price you were aiming for

These values help the app analyze whether a wider stop could have kept you in the trade.

For losing trades, the panel also includes a `Detect` button next to the wishful stop field. It reads the stored `1m` OHLC data for the trade day, finds the first completed adverse excursion after entry, and fills the wishful stop with one inferred tick beyond that adverse extreme.

Detection behavior:

- `Long`: waits for a bar low below entry, tracks the lowest low, and stops when a later bar high reaches back to entry or higher
- `Short`: waits for a bar high above entry, tracks the highest high, and stops when a later bar low reaches back to entry or lower
- the check is limited to stored `1m` OHLC bars on the trade entry day
- the detected value is only suggested in the form until you click `Save`
- if OHLC data is missing, there are no bars after entry, price never moves to the adverse side, or price never gets back to entry, the app shows an error instead of filling the field

### Executions

This section shows every execution that belongs to the trade, including:

- timestamp
- side
- quantity
- price
- commission

### Tags

Use tags to label trades with ideas that matter to you.

You can:

- add an existing tag
- remove a tag
- create a new tag directly from the trade page

Examples include setup names, mistakes, or market conditions.

### Trade Notes

Each trade supports two note areas:

- Pre-Trade Plan
- Post-Trade Review

Use them to record what you planned, what happened, and what you learned.

### Delete Trade

The Delete button permanently removes the trade.

Use it carefully.

## Calendar

The Calendar page shows a month view of your trading results.

It includes:

- a daily performance heatmap
- monthly summary cards
- optional filters for account, symbol, side, and tag

You can move between months to review older periods.

Helpful shortcut:

- click any day in the calendar to open the Trades page filtered to that exact date

## Analytics

The Analytics page is for deeper performance study.

It shows more detailed metric cards than the main dashboard.

Use it to review:

- results metrics
- risk-normalized metrics
- drawdown-related figures
- profitability and consistency measures

Many metrics include small info icons that explain what the number means.

Use the same filter bar to focus on a specific:

- account
- symbol
- side
- tag
- date range

## What-If

The What-if page has two tabs:

- Simulator
- Stop management
  The symbol filter is optional here. If you leave it blank, the page shows one combined stop-management analysis across all trades matching the other filters.

Both tabs work with the filter bar at the top.

### Simulator Tab

The Simulator tab runs Monte Carlo style simulations.

Use it to explore how your results might behave over many future trades.

You can control:

- simulation mode
- starting equity
- number of trades
- risk per trade

There are two modes:

- Sampling: reuses your filtered historical trades
- Parametric: uses the inputs you provide, such as win rate and win/loss ratio

Use this section when you want to ask questions like:

- What could my equity curve look like from here?
- How much drawdown might I face?
- What happens if my risk per trade changes?

### Stop Management Tab

This tab is designed for symbol-specific stop analysis.

Important requirement:

- you must select a symbol in the filters before this tab becomes useful

It includes three parts.

#### Wicked-Out Trades

This list shows trades that were stopped out but may have moved back in your favor later.

It helps you review:

- wishful stop
- target price
- overshoot in R
- whether raw tick data is available

#### Overshoot In R

This section summarizes how far price moved past your stop before reversing.

It shows statistics such as:

- mean
- median
- P75
- P90
- P95
- IQR

Use this to estimate whether your stops are often too tight.

#### What-If Calculator

This tool simulates the effect of widening your stop.

Use it to estimate how results might change if stopped-out trades had more room.

Current calculator behavior:

- with `Replay all trades to the default target` turned off, winners keep their realized P&L, losing trades with a saved target price use that explicit target, and losing trades without a target derive one from the run-scoped `Default Target (R)` input
- with that checkbox turned on, all eligible trades are replayed to the run-scoped default target and saved trade targets are ignored for that run
- `Stop Widening (R)` accepts values from `0` to `10`; setting it to `0` preserves the original stop distance and lets you simulate only the target rule
- `Default Target (R)` is measured from the widened stop, not from the trade's original risk
- the `Converted` section includes any replay that flips a trade from winner to loser or from loser to winner
- if a trade has neither a usable derived target nor usable risk, it is skipped

It has two calculation modes:

- `OHLC (1m)`: replays stored 1-minute candles generated from imported tick data
- `Tick`: replays stored raw ticks directly

OHLC mode is the default and is faster, but it is less precise because each candle only preserves open, high, low, and close.
When a trade's recorded exit falls in a later candle, OHLC replay suppresses stop fills from the entry candle while still allowing an entry-candle target fill.

Tick mode is more precise because it replays the stored ticks in order.

If usable data is missing for the selected mode, the trade is skipped and shown as `Skipped: no data`.

## Settings

The Settings page controls your account preferences and backup tools.

It includes the following sections.

### Profile

Shows your current:

- username
- trading timezone
- display timezone

### Trading Timezone

This is used to interpret timestamps from platforms that do not include timezone information clearly.

If imported times look wrong, check this first.

### Display Timezone

This controls how times appear inside the app, including:

- trade timestamps
- chart times
- other displayed dates and times

### Simulation Starting Equity

This sets the default starting balance used to prefill Monte Carlo simulations.

### Outcome Classification

Gross-flat trades are always classified as breakeven. You can optionally enable
R-based classification and set a breakeven threshold, which defaults to
`0.05R`. When enabled, a trade whose absolute fee-inclusive R multiple is at
or below that threshold is classified as breakeven. Disabling the option leaves
only gross-flat trades classified as breakeven.

### Symbol Mappings

The Symbol Mappings page includes Futures point values, legacy Forex mappings,
and the CFD Instrument Sizing table. Futures retain top-level base-symbol point
values. Legacy Forex pairs use canonical `AAA/BBB` keys and define base
currency, quote currency, pip size, price precision, and contract size. New
legacy Forex contract sizes default to 100,000 base-currency units.

Each Futures row defines:

- normalized base symbol
- dollar value per point

The CFD Instrument Sizing table defines canonical instrument, base unit, quote
currency, tick/price precision, contract size, minimum lots, and lot increment.
Use **Find an instrument** to search the pair, base, or quote field; case and
separators such as dots, dashes, slashes, and spaces are ignored. Search does
not correct misspellings or reorder characters.

Futures point-value and legacy Forex mappings do not change which imported
market-data dataset the backend reads. Use Market-Data Mappings for an explicit
cross-symbol data lookup.

### Market-Data Mappings

Use Market-Data Mappings only when you want one symbol family to read another symbol family's imported datasets.

Each row defines:

- source symbol prefix
- target symbol prefix

Example use case:

- your trades use `MES`
- your imported market-data datasets are stored under `ES`
- you add an explicit mapping from `MES` to `ES`

The default market-data mapping configuration is empty, which means market-data lookup uses the symbol exactly as stored on the trade.

### Backup

This section lets you export and restore your data.

#### Export Backup

Use Export Backup to download a ZIP file containing your Janus Edge data.

This is useful for:

- personal backups
- moving data between environments
- keeping a recovery copy before major imports or edits

The backup also includes stored market-data datasets currently present in the app, not only datasets referenced by exported trades.

Backups use format 1.1 and also include ready and completed Backtest runs with
their committed orders, positions, fills, linked trades/accounts, and saved
chart state. Replay and conversion candle bytes are excluded. When a run is
restored into another Janus Edge instance, destination cache entries are reused
when available; missing Dukascopy dates use the explicit download-recovery
action, and missing manual data requires re-uploading the original CSV files.
Restoring the same archive again reuses imported Backtest runs. Existing 1.0
archives remain supported.

#### Restore Backup

Use Restore Backup to merge a previous ZIP backup into your current account.

Important behavior:

- restore merges into the current account
- existing accounts, tags, and import batches are reused when possible
- duplicate trades are skipped
- after restore, the app shows a summary of what was created, reused, updated, or skipped

This is not a full account replacement. It is a merge.

### Change Password

Use this section to change your password.

You must enter:

- current password
- new password
- confirmation of the new password

### Account

Use the Account section at the bottom of Settings to manage the login account.

To rename the account, enter a 3–50 character username and the current
password. The new username must be unique and existing sessions remain active.

To delete the account, enter the current password and type the current
username exactly. Deletion is permanent and removes the login, trades,
executions, settings, tags, import records, audit records, and media. Shared
imported market-data datasets are retained because they can be used by other
accounts. The current endpoint does not remove Backtest run/cache/revision
records or their candle objects, so those may remain after account deletion.
Export a backup before deleting if the data may be needed later.

## Common Tasks

### Import A New Batch Of Trades

1. Open Trades.
2. Click Import.
3. Upload one or more CSV files.
4. Review the preview and any errors.
5. Reconstruct trades.
6. Fill in fees and initial risk.
7. Finalize the import.
8. Open the imported trades and review details.

### Journal A Trade Properly

1. Open a trade detail page.
2. Review the chart and executions.
3. Add or correct fees and initial risk.
4. Add tags.
5. Fill in Pre-Trade Plan and Post-Trade Review.
6. Upload screenshots or videos if helpful.
7. Add wishful stop and target price if you want to use stop-management analysis later. On losing trades, you can use `Detect` to fill the wishful stop from the stored OHLC data before saving.

### Check A Bad Trading Day Quickly

1. Open Calendar.
2. Move to the month you want.
3. Click the losing day.
4. Review the filtered trade list.
5. Open each trade detail page for notes, chart context, and execution review.

### Study One Setup Or One Symbol

1. Open Dashboard, Analytics, or What-if.
2. Filter by symbol, tag, account, side, or date.
3. Review the filtered charts and metrics.
4. Use What-if for simulation or stop analysis when needed.

## Practical Tips

- Set your timezone correctly before importing large amounts of data.
- If charts are missing for a symbol, check explicit market-data mappings before changing point-value settings.
- Add initial risk if you want meaningful R-multiples and risk-based analysis.
- Use tags consistently so Dashboard and Analytics reports stay useful.
- Use the Calendar page to jump directly into a specific day.
- Export backups regularly, especially before large imports or cleanup work.
- Treat Delete as permanent.

## When Something Looks Wrong

Try these checks first:

- wrong timestamps: review Trading Timezone and Display Timezone in Settings
- missing chart data: refresh the chart, then review explicit market-data mappings and dataset availability
- empty stop-management view: make sure you selected a symbol and saved wishful-stop data on trades
- unexpected import issues: inspect the preview, warnings, and row-level parsing errors before finalizing
- restore confusion: remember that restore merges into the current account instead of replacing it

For setup and environment issues, see [Getting Started](./getting-started.md), [Configuration](./configuration.md), and [Troubleshooting](./troubleshooting.md).
