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
- Q: What drawing behavior should v1 use for tool selection, persistence, deletion, and stepping backward? → A: Use the standard drawing tools; persist by user, run, and timeframe across reloads; save edits and deletions; preserve replay-aware drawing visibility if the pinned CandleKit artifact provides it, otherwise hide drawings by time anchor only, never drawing creation or edit time.
- Q: How should the one-year run limit be applied to selected calendar dates? → A: Start and end dates are inclusive in the configured display timezone; the end date is before the start date's one-year anniversary. For a February 29 start, the latest permitted end date is February 28 of the following year.
- Q: What should users see during preparation and after gaps or errors? → A: Show progress stages and a percentage when measurable; after no-data or failure cleanup, show a dismissible result with the instrument, range, and next action; report fully empty dates and summarize partial gaps; do not synthesize candles.
- Q: How should custom interval input and cross-chart synchronization work at edge cases? → A: Reject invalid intervals with an inline error and keep the last valid interval; retain each tab's interval for the run across reloads; synchronize crosshairs to the same UTC time using the nearest available candle at or before it, and preserve UTC pan/zoom bounds by rounding outward to target interval boundaries.
- Q: How many chart tabs should v1 support at once? → A: Do not enforce a fixed maximum number of chart tabs.
- Q: Should v1 add a chart-tab capacity or rendering-performance target beyond the specified playback speeds? → A: No additional capacity limit or performance target for now.
- Q: Where does the supported-instrument list come from? → A: Use the current catalog exposed by the pinned Dukascopy downloader dependency; the backend validates submitted instruments against that catalog.
- Q: How should preparation work survive an API backend restart? → A: Use a durable worker and persisted preparation jobs so interrupted work can resume without creating a duplicate run or account.
- Q: How often should the run list refresh preparation status? → A: Poll the run list every five seconds while at least one run is preparing.
- Q: What replay cursor should a newly ready run receive? → A: Persist the first available source candle as its cursor when the run becomes ready.
- Q: Which replay controls should the detail page use? → A: Use CandleKit ReplayControls; add a JanusEdge wrapper only for the speed selector if the component does not offer the required speeds.
- Q: Which Dukascopy quote series should the chart use? → A: Use the COMB BID/ASK series and display component-wise midpoint OHLC.

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

1. **Given** the user is in Backtest mode, **When** they request a run for one supported instrument and date range, **Then** the app creates one Backtest account and shows the current preparation stage with a percentage when measurable or indeterminate progress otherwise.
2. **Given** data preparation completes successfully with candles available, **When** the user opens the run, **Then** the run is ready and displays the covered date range.
3. **Given** the requested range contains dates with no candles or partial gaps, **When** data preparation completes, **Then** fully empty dates and summaries of partial gaps are reported and no artificial candles are added.
4. **Given** the entire requested range has no candles, **When** data preparation completes, **Then** the run and its Backtest account are deleted and a dismissible result remains on the run-list page with the instrument, selected range, and an action to edit the range.
5. **Given** data preparation fails, **When** the failure is reported, **Then** the failed run and its Backtest account are immediately deleted and a dismissible result remains on the run-list page with the instrument, selected range, and an action to start a new run.
6. **Given** data preparation is interrupted and the user retries it, **When** the retry completes, **Then** it continues the same run without creating a duplicate Backtest account.
7. **Given** historical data is refreshed after a run is ready, **When** the user reopens that run, **Then** it still uses the candle data selected when the run was prepared.
8. **Given** data preparation is interrupted, **When** the user returns to that run, **Then** it remains in preparation and can be retried without creating a duplicate Backtest account.
9. **Given** the user is entering a date range longer than one year, **When** they select or enter the end date, **Then** the form prevents accepting that range, explains the one-year maximum, and does not allow the run to be submitted.
10. **Given** the user starts a new run from the Backtest run-list page, **When** the run-creation form opens, **Then** it asks for one instrument from the current catalog exposed by the pinned Dukascopy downloader, a start date, and an end date; the backend validates the submitted instrument against that catalog, and Dukascopy and one-minute candles are fixed for this version.
11. **Given** the user selects February 29 as the start date, **When** they select February 28 of the following year as the end date, **Then** the range is accepted; March 1 or later is rejected.
12. **Given** preparation is in progress, **When** the API backend restarts, **Then** the durable job continues or is reclaimed by the worker from its latest completed UTC-date checkpoint without creating another run or account.

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
21. **Given** a chart tab has a valid interval selected, **When** the user enters a non-integer custom interval or a value outside 1 through 1,440 minutes, **Then** the form shows an inline error and keeps the tab's last valid interval.
22. **Given** a run has chart tabs with selected intervals, **When** the user navigates away or reloads and reopens that run, **Then** the tabs and their selected intervals are restored.
23. **Given** crosshair synchronization is enabled and the target timeframe has no candle at the source timestamp, **When** the crosshair is synchronized, **Then** the target uses the nearest available candle at or before that UTC timestamp, or shows no synchronized crosshair if no such candle exists.
24. **Given** pan or zoom synchronization is enabled across different timeframes, **When** the visible time range is synchronized, **Then** each target range uses the same UTC bounds rounded outward to its chart interval boundaries.

### User Story 4 - Find a run through its Backtest account (Priority: P2)

As a trader, I want each replay run represented by an account in the Trades workspace so that I can identify and select a specific run.

**Why this priority**: It gives each run a familiar, unique place in JanusEdge while leaving later trade tracking possible.

**Independent Test**: Create two runs, view the Backtest account selector in Trades, and verify that each run has a distinct account and selecting one identifies only that run.

**Acceptance Scenarios**:

1. **Given** a Backtest run is created, **When** the user views Trades in Backtest mode, **Then** the run appears once as an account option labeled with its instrument and date range.
2. **Given** two runs use the same instrument and date range, **When** the user views the Trades account selector, **Then** their labels have unique suffixes that distinguish the runs.
3. **Given** a Real account and a Backtest account have the same displayed name, **When** the user switches modes, **Then** those accounts remain distinct.
4. **Given** the user selects a Backtest account in Trades, **When** no trade-recording feature is available yet, **Then** the run can be identified and the trade list shows its empty state.

### User Story 5 - Annotate replay charts (Priority: P2)

As a trader, I want to annotate a replay chart so that I can retain observations for a particular run and timeframe.

**Why this priority**: Drawings let users record chart observations while preserving the run's replay and timeframe context.

**Independent Test**: Create, edit, and remove drawings on a replay chart, leave and reload the run, and inspect the saved drawing state at different replay positions and timeframes.

**Acceptance Scenarios**:

1. **Given** a replay chart tab is open, **When** the user uses the standard drawing tools, **Then** they can create, select, reposition, edit, and remove supported drawings.
2. **Given** the user changes a drawing, **When** they leave and later reopen the same run and timeframe, **Then** the drawing state, including edits and removals, is restored for that user.
3. **Given** a run has tabs with different timeframes, **When** the user switches between them, **Then** each timeframe retains its own drawing state.
4. **Given** the pinned CandleKit artifact provides replay-aware drawing visibility, **When** the replay cursor moves backward or forward, **Then** that behavior is preserved.
5. **Given** the pinned CandleKit artifact provides no replay-aware drawing visibility, **When** the cursor is before any of a drawing's time anchors, **Then** the drawing is hidden until all anchors are at or before the cursor. This fallback leaves saved state unchanged and does not use drawing creation or edit time.

### Edge Cases

- The requested range includes dates with no candles or partial gaps within populated dates; gaps are reported and the replay advances through available candles without synthesizing bars.
- The requested range contains no candles at all.
- The user requests a date range longer than one year.
- Data preparation fails; the failed run and its account are immediately deleted after the user is shown an error.
- Data preparation is interrupted; the run remains in preparation and a retry must not duplicate its account.
- The API backend or preparation worker restarts while a run is preparing; the durable job and completed UTC-date checkpoints remain available for recovery.
- The supported-instrument catalog cannot be fetched; the app reports a service error and does not create a run or account.
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
- **FR-002**: Real mode MUST preserve existing Real trade, account, import, manual-entry, and journal behavior and MUST exclude Backtest runs, accounts, and activity from all trade-facing sections and reports.
- **FR-003**: Backtest mode MUST provide the existing applicable sections and a candle replay workspace; trade-facing sections MUST exclude Real trade records.
- **FR-004**: A Backtest run MUST use one instrument from the current supported-instrument catalog exposed by the pinned Dukascopy downloader dependency. The backend MUST validate the submitted code against that catalog before creating a run or account. The run MUST cover an inclusive range of historical calendar dates no longer than one calendar year in the user's configured display timezone. The end date MUST be earlier than the start date's one-year anniversary; for a February 29 start, that anniversary is March 1 of the following year, so the latest permitted end date is February 28. The selected local-day boundaries MUST be converted to UTC when selecting candles.
- **FR-005**: The app MUST retrieve one-minute COMB BID/ASK candles for the selected instrument and range from Dukascopy and derive midpoint open, high, low, and close by taking the arithmetic mean of each corresponding BID/ASK field. The single candle `volume` value MUST be the sum of bid and ask quoted liquidity, and the UI MUST identify it as quoted liquidity rather than executed trade volume. Since the source provides independently aggregated side highs and lows rather than synchronized intraminute quotes, midpoint high and low are component-wise midpoint estimates, not exact tick-level midpoint extrema. Preparation MUST run through a durable worker backed by persisted jobs, independent of the HTTP request lifecycle. It MUST survive API backend restarts and recover interrupted jobs from the latest completed UTC-date checkpoint without duplicating the run or account. During preparation the app MUST show the current stage and a percentage when progress is measurable, or indeterminate progress otherwise; it MUST show a ready state when successful and a result message when no data is available or preparation fails.
- **FR-006**: A run MUST become ready only when data preparation completes successfully and at least one candle is available.
- **FR-007**: The app MUST report requested dates with no candles and summarize partial gaps between available one-minute source candles within populated dates. It MUST NOT synthesize candles for gaps and MUST replay available candles in chronological order.
- **FR-008**: Each run MUST retain the exact candle selection used for replay so later data refreshes do not change that run's history.
- **FR-009**: Each run MUST have exactly one automatically created Backtest account, distinct from Real accounts, including when displayed names match. Its label MUST include the instrument and selected date range; runs with the same instrument and range MUST have a short unique suffix to distinguish them.
- **FR-010**: The Backtest account selector in Trades MUST identify its associated run; a run with no recorded trades MUST display an appropriate empty state.
- **FR-011**: When a run becomes ready, the app MUST persist its replay cursor at source-candle index zero and the timestamp of the first available one-minute source candle as part of the ready-state update. Users MUST be able to play, pause, resume, step forward or backward by one available source candle, and seek to a historical timestamp. Stepping backward at the first source candle MUST leave replay at that candle. Each run MUST retain its replay position across navigation and app reloads.
- **FR-012**: Playback MUST support 1x, 5x, and 20x speeds, defined as one, five, and twenty one-minute source candles per second respectively, regardless of the selected chart timeframe.
- **FR-013**: Seeking MUST position replay at the first available candle at or after the requested timestamp and MUST pause playback. Seeking beyond available data MUST position the run at completion and leave playback paused.
- **FR-014**: The replay MUST display only source data through the current one-minute replay position and MUST NOT reveal later source candles. When stepping backward, later source candles MUST be hidden again.
- **FR-015**: Candle timestamps MUST retain their original UTC meaning and be displayed using the user's configured timezone.
- **FR-016**: Dukascopy bid and ask quoted liquidity MUST be summed and available for review as quoted liquidity; the UI MUST NOT present it as executed trade volume.
- **FR-017**: No-data results and preparation failures MUST be reported with the affected instrument and range in a dismissible result on the run-list page that remains available after the run, account, and preparation job are deleted. A no-data result MUST offer an action to edit the range; a preparation failure MUST offer an action to start a new run. Interrupted preparation MUST remain in preparation, MUST NOT be shown as ready, and MUST offer a retry action. A worker restart or expired lease MUST NOT be treated as a terminal preparation failure.
- **FR-018**: Retrying or recovering data preparation for an interrupted run MUST continue the same durable job, run, and account. It MUST resume from the latest completed UTC-date checkpoint; an incomplete UTC date MAY be fetched again. Recovery MUST NOT create a duplicate run or account.
- **FR-019**: Trade import, manual trade creation, simulated order entry, and trade recording MUST be unavailable in Backtest mode in this version.
- **FR-021**: Backtest mode MUST provide a run-list page and a separate replay detail page. Selecting a ready run MUST open its detail page, which identifies the run and presents one or more adjacent chart tabs, replay controls, and the current replay timestamp.
- **FR-022**: The run-list page MUST show ready and preparing runs with each run's generated account label and preparation status. Preparing runs MUST show the current stage and a percentage when measurable, or indeterminate progress otherwise; the page MUST refresh the run list every five seconds while at least one run is preparing and stop polling when none are preparing. Selecting a preparing run MUST leave the user on the run-list page. When preparation fails or returns no candles, the app MUST show the result described in FR-017 and then immediately delete the run, its associated Backtest account, and its preparation job; failed and no-data runs MUST NOT be retained in the list.
- **FR-023**: The run-list page MUST provide a New Run action that opens a form requiring one instrument from the current catalog exposed by the pinned Dukascopy downloader, a start date, and an end date. The backend MUST validate that instrument against the same catalog before creating the run or account. The form MUST prevent selecting or accepting dates beyond the one-year boundary defined in FR-004 and MUST prevent submission of an over-limit range. Dukascopy and the one-minute source interval are fixed for this version; the account label is generated automatically. Each chart tab MUST offer 1m, 5m, 15m, 30m, 1h, 4h, 1d, and custom whole-minute intervals from 1 through 1,440 minutes. A non-integer or out-of-range custom interval MUST show an inline error and leave the tab's last valid interval selected.
- **FR-024**: Chart bars MUST be aggregated from the one-minute source candles using the same fixed, UTC-aligned interval boundaries as JanusEdge's existing chart, independent of the configured display timezone. Each interval MUST include its start boundary and exclude its end boundary. Each bar MUST use the first source candle's open, the highest source high, the lowest source low, the last source candle's close, and the sum of source volume when available; its timestamp MUST identify the start of the interval. Each replayed source candle MUST update the active bar, which MUST remain in progress until its interval ends. Missing source candles MUST NOT be synthesized.
- **FR-025**: A replay detail page MUST let users open multiple adjacent chart tabs for the same run and instrument, with a separately selected timeframe for each tab and no fixed v1 maximum tab count. The tab set and each tab's selected timeframe MUST be retained for the run across navigation and reloads. All tabs MUST share the run's one-minute replay position and playback state for play, pause, step, seek, and speed changes. Replay synchronization MUST always be enabled and MUST NOT be user-disableable.
- **FR-026**: Every chart tab MUST support crosshair inspection, panning, and zooming.
- **FR-027**: The replay detail page MUST provide separate on/off controls to synchronize crosshair position, horizontal panning, and horizontal zoom across chart tabs. All three controls MUST default to enabled. When enabled, crosshair synchronization MUST use the nearest available target candle at or before the source UTC timestamp; if none exists, the target tab MUST show no synchronized crosshair. Pan and zoom synchronization MUST preserve the same UTC range, rounding each target range outward to its chart interval boundaries. Each option MUST operate independently; changing one MUST NOT alter another or the always-on replay synchronization.
- **FR-028**: Each replay chart tab MUST provide the standard drawing tools for creating, selecting, repositioning, editing, and removing supported drawings.
- **FR-029**: Drawing state MUST be scoped to the authenticated user, run, and chart timeframe. Changes and removals MUST be saved and restored when the user navigates away from or reloads that run and timeframe.
- **FR-030**: Drawing visibility during replay MUST preserve any replay-aware visibility behavior provided by the pinned CandleKit artifact. If it provides no such behavior, a drawing MUST be hidden whenever any time anchor is later than the current replay cursor and MUST become visible again when the cursor reaches or passes all anchors. This fallback MUST NOT use drawing creation or edit time and MUST NOT change the saved drawing state.

### Key Entities

- **Workspace Mode**: The user's current Real or Backtest context, which determines which activity is shown.
- **Backtest Run**: One replay for one instrument and historical date range, selectable from the Backtest run-list page and opened in its own replay detail page, including its data coverage and replay position.
- **Backtest Preparation Job**: The durable worker job associated with a run, including its lease and completed UTC-date checkpoints.
- **Backtest Account**: The automatically created account-like grouping for exactly one run, visible in the Trades account selector and labeled with the instrument and date range, with a unique suffix when needed.
- **Candle Data Selection**: The one-minute OHLC candles and optional volume selected and retained for one run.
- **Replay Chart Tab**: A chart view for a Backtest run's instrument with its own selected timeframe and the run's shared replay position.
- **Replay Drawing State**: The supported chart annotations belonging to one authenticated user, Backtest run, and chart timeframe.

## Success Criteria

### Measurable Outcomes

- **SC-001**: Across trade-facing sections, 100% of activity shown in Real mode belongs to Real records and no Backtest run or account appears there.
- **SC-002**: Every Backtest run has exactly one associated Backtest account, and its label lets users distinguish and select only that run, including when runs share an instrument and date range.
- **SC-003**: Every forward or backward replay step moves by one available one-minute source candle when possible, and no later source candle is visible.
- **SC-004**: For every ready run, users can step forward and backward, play, pause, select a supported playback speed, and seek within the available candle data; a newly ready run's saved cursor points to its first available source candle, seeking leaves the replay paused, and returning to a run after navigation or reload restores its last saved position.
- **SC-005**: No-data and failed requests are removed with their Backtest accounts and preparation jobs and leave a dismissible result on the run-list page with the prescribed next action; interrupted runs remain in preparation with a retry action, and none are presented as ready. Worker or API backend restarts recover the same job and account from its latest completed UTC-date checkpoint.
- **SC-006**: Replaying a ready run after a later data refresh continues to use the candle selection originally associated with that run.
- **SC-007**: The run form prevents users from accepting or submitting dates beyond the inclusive one-calendar-year boundary defined in FR-004; every accepted run covers no more than that range, and no account is created for an invalid range.
- **SC-008**: Every preparing run shows its current stage and a percentage when measurable, or indeterminate progress otherwise; the run list refreshes that status every five seconds while preparation is active and stops when no runs are preparing; selecting a preparing run does not open a detail page.
- **SC-009**: Every new run request is entered with one supported instrument and a date range within the inclusive one-calendar-year boundary in FR-004; the data source and one-minute source interval are fixed, and the replay detail offers the specified standard chart intervals and custom whole-minute intervals from 1 through 1,440 minutes. Invalid custom values are rejected without changing the last valid interval, and each run's chart tabs and intervals are restored after navigation or reload.
- **SC-010**: At each replayed one-minute source candle, the active higher-timeframe chart bar reflects only source candles seen so far and uses the same UTC-aligned interval boundaries as JanusEdge's existing chart; at 5x speed, five source candles are replayed per second regardless of the displayed timeframe.
- **SC-011**: Each ready run can have any number of adjacent chart tabs for its instrument, each using its own timeframe; no fixed v1 tab maximum is enforced, and all tabs always reflect the same replay position and playback state, with no option to disable replay synchronization.
- **SC-012**: Crosshair, horizontal pan, and horizontal zoom synchronization start enabled and can each be turned off independently; when enabled, crosshair targets the nearest available candle at or before the same UTC timestamp, while pan and zoom preserve the same UTC bounds rounded outward to target interval boundaries, without changing replay synchronization.
- **SC-013**: Every replay chart tab provides the standard drawing actions to create, select, reposition, edit, and remove supported drawings; a user's drawing state is independent for each run and timeframe and is restored after navigation or reload.
- **SC-014**: Drawing visibility follows replay-aware behavior provided by the pinned CandleKit artifact; if none is provided, no drawing with a time anchor later than the replay cursor is visible, drawings reappear when all anchors are at or before the cursor, and cursor movement does not alter saved state. The fallback does not filter drawings by creation or edit time.
- **SC-015**: The run form lists instrument codes from the current catalog exposed by the pinned Dukascopy downloader, and the backend rejects codes not present in that catalog before creating a run or account.
- **SC-016**: Restarting the API backend or preparation worker during a run does not lose the job, duplicate its run/account, or repeat completed UTC-date work; after lease recovery, preparation resumes from the latest persisted checkpoint.

## Assumptions

- Replay advances through completed one-minute source candles. A higher-timeframe chart bar may remain in progress and update as each source candle is revealed; tick replay and developing one-minute source candles are out of scope.
- Each run contains one instrument and one-minute OHLC candles; volume is shown only when available.
- Selected calendar dates use the user's configured display timezone, with day boundaries converted to UTC; candle timestamps retain their UTC meaning and are displayed in that timezone.
- COMB midpoint OHLC is derived component-wise from the corresponding one-minute BID and ASK OHLC values. Its high and low are estimates from independently aggregated side extrema; the selected minute data cannot reconstruct exact tick-level midpoint extrema. Combined candle volume is summed bid/ask quoted liquidity, not trade volume.
- The configured display timezone changes how candle timestamps are presented but does not change which one-minute source candles belong to a higher-timeframe chart bar.
- Market closures and other no-candle dates are gaps, not failed data requests; no artificial candles are generated.
- Seeking into a gap selects the first available candle at or after the requested time; seeking beyond the data ends the run.
- Each run automatically receives one Backtest account, even though trade recording is deferred.
- V1 drawing support uses the standard drawing tool set and stores independent state per authenticated user, run, and chart timeframe.

## Out of Scope for This Version

- Simulated market, limit, or stop orders; order cancellation or modification; fills; positions; stop-loss or target management.
- Recording simulated trades, trade P&L, fees, commissions, or slippage.
- Tick replay, developing one-minute source candles, synthetic intrabar paths within a source candle, or resolving same-candle order ambiguity.
- Multiple instruments in one run.
- Automated strategy execution or optimization.
