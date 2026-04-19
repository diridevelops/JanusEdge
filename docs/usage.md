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
- win rate
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

## Add A Manual Trade

Open the Trades page and click New Trade.

Use this when you want to log a trade without importing a CSV file.

You can enter:

- symbol
- long or short side
- quantity
- entry price
- exit price
- entry time
- exit time
- fee
- initial risk
- account name
- notes

After saving, the app opens the new trade detail page automatically.

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

If the instrument trades in points instead of dollars, the chart converts movement using your configured symbol mapping dollar-value-per-point setting.

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
- `Default Target (R)` is measured from the widened stop, not from the trade's original risk
- if a trade has neither a usable derived target nor usable risk, it is skipped

It has two calculation modes:

- `OHLC (1m)`: replays stored 1-minute candles generated from imported tick data
- `Tick`: replays stored raw ticks directly

OHLC mode is the default and is faster, but it is less precise because each candle only preserves open, high, low, and close.

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

### Symbol Mappings

Use Symbol Mappings to control point-value resolution only.

Each row defines:

- normalized base symbol
- dollar value per point

These mappings do not change which market-data dataset the backend reads.

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
