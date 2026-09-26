# Feature Specification: Backtest Candle Replay

**Feature Branch**: [001-backtest-workspace]

**Created**: 2026-09-23

**Status**: Draft

**Input**: User description: "Add a Backtest workspace in JanusEdge, separate from Real mode. Download one-minute historical candles for one instrument; let the chart display a selected timeframe whose active bar updates as each underlying one-minute candle is replayed. Create one Backtest account per run. Keep real trades and backtest activity separate; defer order entry and trade recording."

## Clarifications

### Session 2026-09-24

- Q: When selecting the start and end dates for a backtest, should those calendar dates be interpreted in UTC, your configured display timezone, or the instrument’s market timezone? → A: Configured display timezone.
- Q: When a user leaves a replay and later returns, should it reopen at that run’s last candle position, including after an app reload? → A: Save position per run across navigation and reloads.
- Q: What should the automatically created Backtest account show as its label in the Trades account selector? → A: Auto-label with instrument and date range; add a unique suffix if needed.
- Q: If a user seeks to another timestamp while playback is running, should playback continue from the new position or pause there? → A: Always pause after seeking.
- Q: Should a v1 Backtest run allow any date range for which Dukascopy has one-minute data, or should it enforce a maximum range? → A: Maximum one year per run.
- Q: How should the Backtest workspace organize the previous-run list and active replay? → A: Run list page, then a separate replay detail page.
- Q: Should the run list include runs that are still preparing or failed, and what should happen when the user selects one? → A: Show ready and preparing runs; immediately delete failed runs rather than retaining them.
- Q: If a request completes successfully but finds no candles in the selected date range, should that run be deleted like a failed run or kept as a “No data” entry? → A: Show no-data message, then remove run and account.
- Q: Should replay controls include a one-candle step-back button as well as the existing forward-step button? → A: Add step-back; hide later candles again.
- Q: What should happen when a user selects a run that is still preparing? → A: Keep it in the list with inline progress; do not open a detail.

### Session 2026-09-26

- Q: How should the selected chart timeframe advance from the one-minute replay feed? → A: Each replayed one-minute candle updates the active chart candle; a five-minute bar updates five times before closing, and playback speed is measured in one-minute candles per second.
- Q: Which chart intervals should users be able to choose when replaying the fixed one-minute data? → A: 1m, 5m, 15m, 30m, 1h, 4h, 1d, and custom whole-minute intervals.
- Q: What limit should custom whole-minute chart intervals have? → A: Cap custom intervals at 1,440 minutes (one day).
- Q: Should chart bars be grouped on the configured display timezone's clock or on UTC clock boundaries? → A: Use the same deterministic candle grouping as JanusEdge's existing chart: UTC-aligned intervals that include their start and exclude their end; display timezone affects timestamp presentation, not candle membership.
- Q: How should multiple chart tabs share one replay? → A: Tabs show the same run and instrument at their own timeframes and always share one replay position; replay synchronization cannot be disabled.
- Q: How should crosshair, pan, and zoom behave across the chart tabs? → A: Replay is always synchronized; crosshair, pan, and zoom synchronization each have an independent on/off control.
- Q: When a replay page first opens, which defaults should the crosshair, pan, and zoom synchronization controls use? → A: All three synchronization controls start enabled and can be turned off independently.

## User Scenarios & Testing

### User Story 1 - Keep Real and Backtest activity separate (Priority: P1)

As a trader, I want separate Real and Backtest workspaces so that existing trading records remain separate from historical market replay.

**Why this priority**: Users must be able to trust the data shown in the existing journal and the new replay workspace.

**Independent Test**: View the app in both modes and verify that the Real workspace has no Backtest runs or accounts, while the Backtest workspace shows its runs and no real trades.

**Acceptance Scenarios**:

1. **Given** the user is in Real mode, **When** they view trades, accounts, or trade-based reports, **Then** only real activity is shown and no Backtest runs or accounts are shown.
2. **Given** the user is in Backtest mode, **When** they view trade-facing sections, **Then** no Real trades are shown and sections without Backtest trade data display an appropriate empty state.
3. **Given** the user switches modes or reloads the app, **When** they return to a workspace, **Then** its current mode is clear and saved runs remain available in Backtest.
4. **Given** the user is in Backtest mode, **When** they look for trade import or manual trade creation, **Then** those actions are unavailable; those existing actions remain available in Real mode.

### User Story 2 - Prepare a one-instrument replay (Priority: P1)

As a trader, I want to select one instrument and a historical date range, download its available one-minute candles, and prepare a replay.

**Why this priority**: Historical candle data is the required input for every replay.

**Independent Test**: Select one supported instrument and a date range with available data; verify the data preparation status, run account, and resulting replay coverage.

**Acceptance Scenarios**:

1. **Given** the user is in Backtest mode, **When** they request a run for one supported instrument and date range, **Then** the app shows preparation progress and creates one Backtest account for that run.
2. **Given** data preparation completes successfully with candles available, **When** the user opens the run, **Then** the run is ready and displays the covered date range.
3. **Given** the requested range contains ordinary no-data dates, **When** data preparation completes, **Then** those gaps are reported and no artificial candles are added.
4. **Given** the entire requested range has no candles, **When** data preparation completes, **Then** the user is shown a no-data message with the affected instrument, selected range, and a useful next action, and the run and its Backtest account are deleted.
5. **Given** data preparation fails, **When** the failure is reported, **Then** the user is shown the affected instrument, selected range, and a useful next action, and the failed run and its Backtest account are immediately deleted.
6. **Given** data preparation is interrupted and the user retries it, **When** the retry completes, **Then** it continues the same run without creating a duplicate Backtest account.
7. **Given** historical data is refreshed after a run is ready, **When** the user reopens that run, **Then** it still uses the candle data selected when the run was prepared.
8. **Given** data preparation is interrupted, **When** the user returns to that run, **Then** it remains in preparation and can be retried without creating a duplicate Backtest account.
9. **Given** the user is entering a date range longer than one year, **When** they select or enter the end date, **Then** the form prevents accepting that range, explains the one-year maximum, and does not allow the run to be submitted.
10. **Given** the user starts a new run from the Backtest run-list page, **When** the run-creation form opens, **Then** it asks for one supported instrument, a start date, and an end date; Dukascopy and one-minute candles are fixed for this version.

### User Story 3 - Replay candles interactively (Priority: P1)

As a trader, I want to play, pause, step through, and seek across completed candles so that I can inspect historical price action at my own pace.

**Why this priority**: Candle-by-candle replay is the core user experience in this version.

**Independent Test**: Start a ready run, step through several candles, use each playback control, and verify that the displayed candle and timestamp match the replay position.

**Acceptance Scenarios**:

1. **Given** the user is on the Backtest run-list page, **When** they select a ready run, **Then** its separate replay detail page opens.
2. **Given** a run is ready with available candles, **When** the user opens it for the first time, **Then** replay starts at the first available candle.
3. **Given** a ready run is at a candle, **When** the user steps forward once, **Then** the replay advances by exactly one next available candle.
4. **Given** the replay is at a candle with a previous available candle, **When** the user steps backward once, **Then** the replay moves back exactly one available candle and hides all later candles.
5. **Given** replay is at the first available candle, **When** the user steps backward, **Then** it remains at the first candle and reveals no earlier data.
6. **Given** a ready run is playing, **When** the user pauses it, **Then** candle advancement stops at the current replay position.
7. **Given** the user has left a replay, **When** they return to that run after navigating away or reloading the app, **Then** it resumes at that run's last saved position.
8. **Given** the user selects a playback speed, **When** playback continues, **Then** 1x advances one candle per second, 5x advances five candles per second, and 20x advances twenty candles per second.
9. **Given** the user seeks to a historical timestamp, **When** the seek completes, **Then** replay moves to the first available candle at or after that timestamp and is paused.
10. **Given** the replay is at a particular candle, **When** the chart is displayed, **Then** it does not reveal any later candle.
11. **Given** volume is available for a candle, **When** that candle is displayed, **Then** its volume is available for review.
12. **Given** a candle has a UTC timestamp, **When** it is displayed, **Then** the user sees the same instant in their configured timezone.
13. **Given** replay reaches the final available candle, **When** the user advances or continues playback, **Then** the run reports completion and does not advance beyond the selected data.
14. **Given** the selected chart timeframe is longer than one minute, **When** another one-minute source candle is replayed within the active chart interval, **Then** the active chart candle updates from the source candles seen so far and closes only after its interval is complete.
15. **Given** the same replay data and chart interval, **When** the user changes the configured display timezone, **Then** the source candles remain grouped into the same UTC-aligned chart bars and only their displayed timestamps change.
16. **Given** a ready run is open, **When** the user adds chart tabs, **Then** each tab shows the same run's instrument and can use a different chart timeframe.
17. **Given** a run has multiple chart tabs open, **When** the user plays, pauses, steps, seeks, or changes playback speed, **Then** every tab reflects the same one-minute replay position and replay synchronization cannot be disabled.
18. **Given** a chart tab is open, **When** the user inspects or navigates its chart, **Then** crosshair inspection, panning, and zooming are available.
19. **Given** multiple chart tabs are open, **When** the user enables crosshair, pan, or zoom synchronization, **Then** that behavior is shared across tabs; disabling one of these options leaves the other synchronization options and replay synchronization unchanged.
20. **Given** a replay detail page opens, **When** its chart tabs and synchronization controls appear, **Then** crosshair, pan, and zoom synchronization are enabled by default.

### User Story 4 - Find a run through its Backtest account (Priority: P2)

As a trader, I want each replay run represented by an account in the Trades workspace so that I can identify and select a specific run.

**Why this priority**: It gives each run a familiar, unique place in JanusEdge while leaving later trade tracking possible.

**Independent Test**: Create two runs, view the Backtest account selector in Trades, and verify that each run has a distinct account and selecting one identifies only that run.

**Acceptance Scenarios**:

1. **Given** a Backtest run is created, **When** the user views Trades in Backtest mode, **Then** the run appears once as an account option labeled with its instrument and date range.
2. **Given** two runs use the same instrument and date range, **When** the user views the Trades account selector, **Then** their labels have unique suffixes that distinguish the runs.
3. **Given** a Real account and a Backtest account have the same displayed name, **When** the user switches modes, **Then** those accounts remain distinct.
4. **Given** the user selects a Backtest account in Trades, **When** no trade-recording feature is available yet, **Then** the run can be identified and the trade list shows its empty state.

### Edge Cases

- The requested range includes dates with no candles, such as market closures; the replay advances through available candles without synthesizing bars.
- The requested range contains no candles at all.
- The user requests a date range longer than one year.
- Data preparation fails; the failed run and its account are immediately deleted after the user is shown an error.
- Data preparation is interrupted; the run remains in preparation and a retry must not duplicate its account.
- A seek timestamp falls in a gap or after the last available candle.
- The user steps backward at the first available candle; replay remains at the first candle.
- Seeking while playback is running pauses the replay at the selected position.
- Playback reaches the last candle.
- A Real account and Backtest account share the same displayed name.
- Two Backtest runs use the same instrument and date range and need distinct account labels.
- The user changes workspace while data is downloading or replay is paused.
- Data is refreshed after a run is ready; the run must retain its original selection.

## Requirements

### Functional Requirements

- **FR-001**: The app MUST provide separate Real and Backtest workspaces for each user.
- **FR-002**: Real mode MUST preserve existing Real trade, account, import, manual-entry, and journal behavior and MUST exclude Backtest runs and accounts from trade-facing sections.
- **FR-003**: Backtest mode MUST provide the existing applicable sections and a candle replay workspace; trade-facing sections MUST exclude Real trade records.
- **FR-004**: A Backtest run MUST use one supported instrument and a user-selected historical date range no longer than one year. Selected calendar dates MUST use the user's configured display timezone, with their day boundaries converted to UTC when selecting candles.
- **FR-005**: The app MUST retrieve one-minute OHLC candles for the selected instrument and range from Dukascopy and show data preparation progress, a ready state when successful, or a clear message when no data is available or preparation fails.
- **FR-006**: A run MUST become ready only when data preparation completes successfully and at least one candle is available.
- **FR-007**: The app MUST report dates with no candles, MUST NOT synthesize candles for gaps, and MUST replay available candles in chronological order.
- **FR-008**: Each run MUST retain the exact candle selection used for replay so later data refreshes do not change that run's history.
- **FR-009**: Each run MUST have exactly one automatically created Backtest account, distinct from Real accounts, including when displayed names match. Its label MUST include the instrument and selected date range; runs with the same instrument and range MUST have a short unique suffix to distinguish them.
- **FR-010**: The Backtest account selector in Trades MUST identify its associated run; a run with no recorded trades MUST display an appropriate empty state.
- **FR-011**: A newly ready run MUST open at its first available one-minute source candle. Users MUST be able to play, pause, resume, step forward or backward by one available source candle, and seek to a historical timestamp. Stepping backward at the first source candle MUST leave replay at that candle. Each run MUST retain its replay position across navigation and app reloads.
- **FR-012**: Playback MUST support 1x, 5x, and 20x speeds, defined as one, five, and twenty one-minute source candles per second respectively, regardless of the selected chart timeframe.
- **FR-013**: Seeking MUST position replay at the first available candle at or after the requested timestamp and MUST pause playback. Seeking beyond available data MUST position the run at completion and leave playback paused.
- **FR-014**: The replay MUST display only source data through the current one-minute replay position and MUST NOT reveal later source candles. When stepping backward, later source candles MUST be hidden again.
- **FR-015**: Candle timestamps MUST retain their original UTC meaning and be displayed using the user's configured timezone.
- **FR-016**: Candle volume MUST be available for review when the data source provides it.
- **FR-017**: No-data results and preparation failures MUST be reported with the affected instrument and range and a relevant next action, then the run and its Backtest account MUST be deleted. Interrupted preparation MUST remain in preparation, MUST NOT be shown as ready, and MUST offer a retry action.
- **FR-018**: Retrying data preparation for an interrupted run MUST continue that run and MUST NOT create a duplicate run account.
- **FR-019**: Trade import, manual trade creation, simulated order entry, and trade recording MUST be unavailable in Backtest mode in this version.
- **FR-020**: Real mode MUST continue to show only real trade activity; Backtest activity MUST NOT enter Real trade-facing reports.
- **FR-021**: Backtest mode MUST provide a run-list page and a separate replay detail page. Selecting a ready run MUST open its detail page, which identifies the run and presents one or more adjacent chart tabs, replay controls, and the current replay timestamp.
- **FR-022**: The run-list page MUST show ready and preparing runs with each run's generated account label and preparation status. Preparing runs MUST show progress inline, and selecting one MUST leave the user on the run-list page. When preparation fails or returns no candles, the app MUST report the outcome and then immediately delete the run and its associated Backtest account; failed and no-data runs MUST NOT be retained in the list.
- **FR-023**: The run-list page MUST provide a New Run action that opens a form requiring one supported instrument, a start date, and an end date. The form MUST prevent selecting or accepting a date range longer than one year and MUST prevent submission of an over-limit range. Dukascopy and the one-minute source interval are fixed for this version; the account label is generated automatically. Each chart tab MUST offer 1m, 5m, 15m, 30m, 1h, 4h, and 1d chart intervals and MUST let users enter a custom whole-minute interval from 1 through 1,440 minutes.
- **FR-024**: Chart bars MUST be aggregated from the one-minute source candles using the same fixed, UTC-aligned interval boundaries as JanusEdge's existing chart, independent of the configured display timezone. Each interval MUST include its start boundary and exclude its end boundary. Each bar MUST use the first source candle's open, the highest source high, the lowest source low, the last source candle's close, and the sum of source volume when available; its timestamp MUST identify the start of the interval. Each replayed source candle MUST update the active bar, which MUST remain in progress until its interval ends. Missing source candles MUST NOT be synthesized.
- **FR-025**: A replay detail page MUST let users open multiple adjacent chart tabs for the same run and instrument, with a separately selected timeframe for each tab. All tabs MUST share the run's one-minute replay position and playback state for play, pause, step, seek, and speed changes. Replay synchronization MUST always be enabled and MUST NOT be user-disableable.
- **FR-026**: Every chart tab MUST support crosshair inspection, panning, and zooming.
- **FR-027**: The replay detail page MUST provide separate on/off controls to synchronize crosshair position, horizontal panning, and horizontal zoom across chart tabs. All three controls MUST default to enabled. When enabled, crosshair synchronization MUST align tabs to the same replay timestamp, and pan or zoom synchronization MUST keep their visible time range aligned even when their chart timeframes differ. Each option MUST operate independently; changing one MUST NOT alter another or the always-on replay synchronization.

### Key Entities

- **Workspace Mode**: The user's current Real or Backtest context, which determines which activity is shown.
- **Backtest Run**: One replay for one instrument and historical date range, selectable from the Backtest run-list page and opened in its own replay detail page, including its data coverage and replay position.
- **Backtest Account**: The automatically created account-like grouping for exactly one run, visible in the Trades account selector and labeled with the instrument and date range, with a unique suffix when needed.
- **Candle Data Selection**: The one-minute OHLC candles and optional volume selected and retained for one run.
- **Replay Chart Tab**: A chart view for a Backtest run's instrument with its own selected timeframe and the run's shared replay position.

## Success Criteria

### Measurable Outcomes

- **SC-001**: Across trade-facing sections, 100% of activity shown in Real mode belongs to Real records and no Backtest run or account appears there.
- **SC-002**: Every Backtest run has exactly one associated Backtest account, and its label lets users distinguish and select only that run, including when runs share an instrument and date range.
- **SC-003**: Every forward or backward replay step moves by one available one-minute source candle when possible, and no later source candle is visible.
- **SC-004**: For every ready run, users can step forward and backward, play, pause, select a supported playback speed, and seek within the available candle data; seeking leaves the replay paused, and returning to a run after navigation or reload restores its last saved position.
- **SC-005**: No-data and failed requests are reported and removed with their Backtest accounts; interrupted runs remain in preparation with a retry action, and none are presented as ready.
- **SC-006**: Replaying a ready run after a later data refresh continues to use the candle selection originally associated with that run.
- **SC-007**: The run form prevents users from accepting or submitting a range longer than one year; every accepted run covers no more than one year, and no account is created for an invalid range.
- **SC-008**: Every preparing run shows progress in the run-list row, and selecting it does not open a detail page.
- **SC-009**: Every new run request is entered with one supported instrument and a date range no longer than one year; the data source and one-minute source interval are fixed, and the replay detail offers the specified standard chart intervals and custom whole-minute intervals from 1 through 1,440 minutes.
- **SC-010**: At each replayed one-minute source candle, the active higher-timeframe chart bar reflects only source candles seen so far and uses the same UTC-aligned interval boundaries as JanusEdge's existing chart; at 5x speed, five source candles are replayed per second regardless of the displayed timeframe.
- **SC-011**: Each ready run can have multiple adjacent chart tabs for its instrument, each using its own timeframe; all tabs always reflect the same replay position and playback state, with no option to disable replay synchronization.
- **SC-012**: Crosshair, horizontal pan, and horizontal zoom synchronization start enabled and can each be turned off independently; when enabled, the corresponding time position or visible time range remains aligned across chart tabs without changing replay synchronization.

## Assumptions

- Replay advances through completed one-minute source candles. A higher-timeframe chart bar may remain in progress and update as each source candle is revealed; tick replay and developing one-minute source candles are out of scope.
- Each run contains one instrument and one-minute OHLC candles; volume is shown only when available.
- Selected calendar dates use the user's configured display timezone, with day boundaries converted to UTC; candle timestamps retain their UTC meaning and are displayed in that timezone.
- The configured display timezone changes how candle timestamps are presented but does not change which one-minute source candles belong to a higher-timeframe chart bar.
- Market closures and other no-candle dates are gaps, not failed data requests; no artificial candles are generated.
- Seeking into a gap selects the first available candle at or after the requested time; seeking beyond the data ends the run.
- Each run automatically receives one Backtest account, even though trade recording is deferred.

## Out of Scope for This Version

- Simulated market, limit, or stop orders; order cancellation or modification; fills; positions; stop-loss or target management.
- Recording simulated trades, trade P&L, fees, commissions, or slippage.
- Tick replay, developing one-minute source candles, synthetic intrabar paths within a source candle, or resolving same-candle order ambiguity.
- Multiple instruments in one run.
- Automated strategy execution or optimization.
