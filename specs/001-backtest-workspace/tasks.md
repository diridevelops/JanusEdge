---
description: "Dependency-ordered implementation tasks for Backtest Candle Replay"
---

# Tasks: Backtest Candle Replay

**Input**: Design documents in `specs/001-backtest-workspace/` (`spec.md`, `plan.md`, `data-model.md`, `contracts/backtest-api.md`, `research.md`, and `quickstart.md`).

**Prerequisites**: The feature spec and implementation plan are available. The project constitution is still the Spec Kit placeholder and defines no ratified principles.

**Testing**: Include focused backend pytest coverage and focused frontend adapter tests because the plan calls for API, replay-adapter, synchronization, and browser validation. Add Vitest for deterministic frontend date, aggregation, synchronization, and drawing-visibility tests. Keep end-to-end user-flow validation in the quickstart. Write focused tests before their story implementation.

**Organization**: Tasks are grouped by the five user stories and ordered by their dependencies. The paths follow the existing Flask/React project and the feature plan.

## Phase 1: Setup

**Purpose**: Resolve library and data-provider compatibility before feature implementation.

- [ ] T001 Inspect the pinned `@getcandlekit/charts@0.1.1` artifact for the `ChartView`, `ReplayControls`, `DrawingToolbar`, `ReplayDataSource`, `SyncEngine`, and `DrawingEngine` APIs, including whether `ReplayControls` exposes 1x/5x/20x speeds; record verified exports in `specs/001-backtest-workspace/research.md`, and if a required core API is missing, identify a compatible CandleKit release before updating the dependency rather than substituting another chart library.
- [ ] T002 Pin CandleKit and one compatible `lightweight-charts` 5.x version, add Vitest and a frontend test script, and update the lockfile in `frontend/package.json` and `frontend/package-lock.json`.
- [ ] T003 Add the Dukascopy downloader as a pinned Git dependency, confirm its `fetch_instrument_codes` catalog and per-day download API, and reconcile its PyArrow 25+ requirement with the backend dependency set in `backend/pyproject.toml` and `backend/uv.lock`.
- [ ] T004 Adapt the existing Real trade chart to the Lightweight Charts 5.x API while preserving its markers, price lines, interval selector, and theme behavior in `frontend/src/components/charts/CandlestickChart.tsx`.

---

## Phase 2: Foundational

**Purpose**: Add shared persistence and API boundaries required by all Backtest stories.

- [ ] T005 [P] Add MongoDB indexes for user-scoped run lookups, unique run-to-account and run-to-preparation-job associations, queued/expired-lease job claims, immutable snapshot identity, per-run chart-tab identity, and per-user/run/interval drawing state in `backend/app/db.py`.
- [ ] T006 [P] Create and register the authenticated Backtest Flask blueprint in `backend/app/backtests/__init__.py` and `backend/app/__init__.py`.
- [ ] T007 [P] Define shared instrument-catalog, run, preparation-notice, candle, replay-position, chart-tab, and drawing API types and request helpers in `frontend/src/types/backtest.types.ts` and `frontend/src/api/backtests.api.ts`.

---

## Phase 3: User Story 1 - Keep Real and Backtest activity separate (Priority: P1)

**Goal**: Make the active workspace explicit and ensure trade-facing data and actions stay within that mode.

**Independent Test**: Switch between Real and Backtest and reload. Real sections contain only legacy/default-Real records and retain existing actions; Backtest sections contain no Real trades and hide import/manual trade creation.

### Tests for User Story 1

- [ ] T008 [P] [US1] Add pytest coverage for reading/updating a user's workspace mode, ownership, and the default Real mode in `backend/tests/test_workspace_mode/test_workspace_mode_routes.py`.
- [ ] T009 [P] [US1] Add pytest coverage for legacy accounts defaulting to Real, mode-filtered trade/account/report results, and blocked Backtest trade-import/manual-entry writes in `backend/tests/test_workspace_mode/test_workspace_mode_isolation.py`.

### Implementation for User Story 1

- [ ] T010 [US1] Implement user-scoped workspace-mode persistence and authenticated read/update routes in `backend/app/workspace_mode/repository.py`, `backend/app/workspace_mode/service.py`, `backend/app/workspace_mode/routes.py`, and `backend/app/workspace_mode/__init__.py`; register the blueprint in `backend/app/__init__.py`.
- [ ] T011 [US1] Scope account, trade, execution, analytics, calendar, and What-if reads to the active mode, treating documents without a mode as Real, in `backend/app/repositories/account_repo.py`, `backend/app/repositories/trade_repo.py`, `backend/app/trades/service.py`, `backend/app/executions/routes.py`, `backend/app/analytics/routes.py`, `backend/app/analytics/service.py`, and `backend/app/whatif/routes.py`.
- [ ] T012 [US1] Reject trade import and manual trade creation while Backtest mode is active while preserving their Real-mode behavior in `backend/app/imports/routes.py` and `backend/app/trades/routes.py`.
- [ ] T013 [US1] Add the workspace-mode API/types and a provider that loads and persists the user's selected mode across navigation and reloads in `frontend/src/api/workspace.api.ts`, `frontend/src/types/workspace.types.ts`, and `frontend/src/contexts/WorkspaceModeContext.tsx`.
- [ ] T014 [US1] Mount the workspace provider, add a visible mode switcher, route Backtest navigation to the run list, and hide or guard trade import/manual-entry actions in `frontend/src/App.tsx`, `frontend/src/components/layout/AppLayout.tsx`, `frontend/src/components/layout/Sidebar.tsx`, `frontend/src/pages/ImportPage.tsx`, and `frontend/src/pages/ManualTradePage.tsx`.

**Checkpoint**: Both modes load independently; returning to Real preserves existing behavior and no Backtest account or activity appears in Real trade-facing sections.

---

## Phase 4: User Story 2 - Prepare a one-instrument replay (Priority: P1)

**Goal**: Create one run and one associated Backtest account, download the selected one-minute candles, and report preparation outcomes without changing a ready run's snapshot.

**Independent Test**: From Backtest mode, submit a supported instrument and valid date range; verify stage/progress, one account, coverage and gaps, retry behavior, and dismissible no-data/failure results.

### Tests for User Story 2

- [ ] T015 [P] [US2] Add pytest coverage for catalog-backed instrument validation, display-timezone date conversion, the inclusive one-calendar-year limit, February 29 handling, and exactly one account per run in `backend/tests/test_backtests/test_backtest_service.py`.
- [ ] T016 [P] [US2] Add pytest coverage for progress, partial and fully empty dates, no-data/failure cleanup, durable job lease recovery and UTC-date checkpoints, retry idempotency, and immutable ready snapshots in `backend/tests/test_backtests/test_dukascopy_provider.py` and `backend/tests/test_backtests/test_backtest_routes.py`.
- [ ] T017 [P] [US2] Add Vitest coverage for the client-side inclusive year boundary, February 29 rule, and invalid-range rejection in `frontend/src/utils/backtestDates.test.ts`.

### Implementation for User Story 2

- [ ] T018 [US2] Define Backtest run, account, coverage, progress, preparation-notice, and durable preparation-job schemas, including lease ownership/expiry and completed UTC-date checkpoints, plus owner-scoped repository operations in `backend/app/backtests/schemas.py` and `backend/app/backtests/repository.py`.
- [ ] T019 [US2] Validate the instrument against the pinned downloader's current `fetch_instrument_codes` catalog, IANA display timezone, inclusive local dates, UTC day boundaries, and one-calendar-year rule, then create one preparing run, one uniquely labeled account, and one durable preparation job idempotently in `backend/app/backtests/service.py`, `backend/app/backtests/preparation_jobs.py`, `backend/app/models/trade_account.py`, and `backend/app/repositories/account_repo.py`.
- [ ] T020 [US2] Implement the separate MongoDB-backed preparation worker with atomic expiring leases and lease renewal, recovery of expired jobs, per-UTC-date downloader calls, one-minute OHLCV normalization, measurable/indeterminate progress, empty-date and partial-gap summaries without synthesized candles, durable MinIO date staging and MongoDB date checkpoints, and persisted run progress across API or worker restarts in `backend/app/backtests/preparation_jobs.py`, `backend/app/backtests/worker.py`, `backend/app/backtests/dukascopy_provider.py`, `backend/app/backtests/service.py`, and the `backtest-worker` service in `docker-compose.yml`.
- [ ] T021 [US2] Assemble completed UTC-date staging into a run-owned immutable MinIO Parquet snapshot with checksum, candle coverage, empty-date, and partial-gap metadata; after confirming at least one candle, update the run to ready and persist cursor index zero plus the first candle timestamp in the same MongoDB run-document write in `backend/app/backtests/snapshot_store.py` and `backend/app/backtests/service.py`.
- [ ] T022 [US2] Persist a user-scoped notice and immediately remove the run/account/job and staging data after no-data or terminal provider failure; requeue the same job and preserve completed-date checkpoints for manual retry, while worker interruption remains recoverable through its lease, in `backend/app/backtests/repository.py`, `backend/app/backtests/preparation_jobs.py`, and `backend/app/backtests/service.py`.
- [ ] T023 [US2] Implement authenticated instrument-catalog, create, list, detail, retry, notice-list, and notice-dismissal endpoints with owner filtering and the response shapes in `specs/001-backtest-workspace/contracts/backtest-api.md` in `backend/app/backtests/routes.py` and `backend/app/backtests/schemas.py`.
- [ ] T024 [US2] Build the new-run form using the instrument catalog endpoint, with start/end dates, display-timezone boundary checks, inline one-year validation, and submission blocking for invalid ranges in `frontend/src/components/backtest/BacktestRunForm.tsx` and `frontend/src/utils/backtestDates.ts`.
- [ ] T025 [US2] Build the run-list page with ready/preparing states, stage and percentage-or-indeterminate progress, five-second polling while any run prepares (stopping when none do), inline preparation notices, retry/dismiss/edit-range actions, and ready-only navigation in `frontend/src/pages/BacktestRunListPage.tsx` and `frontend/src/components/backtest/BacktestRunList.tsx`.

**Checkpoint**: A ready run owns a non-empty immutable candle selection and one account; a failed or empty selection leaves only its dismissible result notice.

---

## Phase 5: User Story 3 - Replay candles interactively (Priority: P1)

**Goal**: Replay the immutable one-minute sequence through one shared cursor and show only data revealed through that cursor on persisted multi-timeframe tabs.

**Independent Test**: Open a ready run, step/play/pause/seek/back up, reload it, and verify the UTC timestamp, available-candle position, active higher-timeframe bar, and all tabs agree without exposing later candles.

### Tests for User Story 3

- [ ] T026 [P] [US3] Add pytest coverage for owner-scoped available-date/day-candle reads and revision-checked cursor writes, including intentional step-back and stale-write rejection, in `backend/tests/test_backtests/test_backtest_replay_routes.py`.
- [ ] T027 [P] [US3] Add Vitest coverage for UTC-aligned start-inclusive/end-exclusive OHLCV aggregation, active-bar updates, gaps, and cursor-bounded no-lookahead behavior in `frontend/src/utils/backtestCandles.test.ts`.
- [ ] T028 [P] [US3] Add Vitest coverage for crosshair nearest-prior mapping and outward UTC range rounding across different intervals in `frontend/src/utils/backtestChartSync.test.ts`.

### Implementation for User Story 3

- [ ] T029 [US3] Implement authenticated available-UTC-date and one-day candle reads from the run's immutable snapshot in `backend/app/backtests/routes.py`, `backend/app/backtests/service.py`, and `backend/app/backtests/snapshot_store.py`.
- [ ] T030 [US3] Persist the shared source-candle index and timestamp with monotonic revisions, validate each index/time pair against the immutable sequence, accept intentional step-back, and reject stale writes in `backend/app/backtests/repository.py`, `backend/app/backtests/service.py`, and `backend/app/backtests/routes.py`.
- [ ] T031 [US3] Implement one CandleKit `ReplayController` per run and its `ReplayDataSource` adapter, restore the saved cursor paused on reload, and serialize/coalesce cursor writes in `frontend/src/hooks/useBacktestReplay.ts` and `frontend/src/api/backtests.api.ts`.
- [ ] T032 [US3] Aggregate only revealed one-minute candles into each UTC-aligned interval using first open, maximum high, minimum low, latest close, and available-volume sum; update bars incrementally on forward replay and rebuild cursor-bounded bars on seek/back-step in `frontend/src/utils/backtestCandles.ts`, `frontend/src/hooks/useBacktestReplay.ts`, and `frontend/src/components/backtest/CandleKitReplayChart.tsx`.
- [ ] T033 [US3] Integrate CandleKit `ReplayControls` for play, pause, resume, forward/back one-candle steps, timestamp seek, and completion state, binding them to the shared `ReplayController`; add a JanusEdge wrapper only for the 1x/5x/20x speed selector if CandleKit does not expose those choices in `frontend/src/components/backtest/BacktestReplayControls.tsx` and `frontend/src/pages/BacktestReplayPage.tsx`.
- [ ] T034 [US3] Implement the nonempty, unbounded `PUT /api/backtest/runs/{run_id}/chart-tabs` contract with stable tab ids/order and 1–1,440 whole-minute validation, then restore each tab's interval and retain the last valid selection after inline errors in `backend/app/backtests/routes.py`, `backend/app/backtests/service.py`, `frontend/src/components/backtest/BacktestChartTab.tsx`, `frontend/src/pages/BacktestReplayPage.tsx`, and `frontend/src/api/backtests.api.ts`.
- [ ] T035 [US3] Route crosshair, pan, and zoom through CandleKit `SyncEngine` with independent default-enabled switches; map positions through UTC, snap crosshairs to the nearest available prior candle, round visible ranges outward, and keep replay synchronization always on in `frontend/src/hooks/useBacktestChartSync.ts` and `frontend/src/components/backtest/BacktestSyncControls.tsx`.
- [ ] T036 [US3] Build the separate replay detail page with run identity, configured-timezone timestamps, volume display, chart tabs, replay controls, and synchronization controls, and register its route in `frontend/src/pages/BacktestReplayPage.tsx` and `frontend/src/App.tsx`.

**Checkpoint**: All tabs share one saved replay position; higher-timeframe candles use only source bars already replayed, and seeking or stepping backward hides later data.

---

## Phase 6: User Story 4 - Find a run through its Backtest account (Priority: P2)

**Goal**: Let users identify and select a run from the Backtest account selector while keeping trade recording unavailable.

**Independent Test**: Create two same-instrument, same-range runs; verify their account labels distinguish them, selecting either identifies only that run, and its trade list shows an empty state.

### Tests for User Story 4

- [ ] T037 [P] [US4] Add pytest coverage for one account per run, unique same-range labels, account-mode separation, and Backtest account selection with no trade records in `backend/tests/test_backtests/test_backtest_accounts.py`.

### Implementation for User Story 4

- [ ] T038 [US4] Return the associated run id and generated display label with Backtest account records while preserving Real account response behavior in `backend/app/accounts/routes.py`, `backend/app/repositories/account_repo.py`, `frontend/src/api/accounts.api.ts`, and `frontend/src/types/account.types.ts`.
- [ ] T039 [US4] Show only active-mode accounts in the Trades selector, identify a selected Backtest run by its instrument/date-range label, and render the specified no-trades empty state in `frontend/src/components/filters/FilterBar.tsx` and `frontend/src/pages/TradeListPage.tsx`.

**Checkpoint**: Selecting a Backtest account identifies its run without showing Real trades or enabling trade recording.

---

## Phase 7: User Story 5 - Annotate replay charts (Priority: P2)

**Goal**: Provide standard CandleKit drawing tools with authenticated per-user/run/timeframe persistence and replay-aware visibility.

**Independent Test**: Create, edit, reposition, and delete drawings; reload the run and verify per-timeframe state, user isolation, and visibility after moving the replay cursor backward and forward.

### Tests for User Story 5

- [ ] T040 [P] [US5] Add pytest coverage for owner/run/interval-scoped drawing reads and writes, payload validation, empty saved state, and revision conflicts in `backend/tests/test_backtests/test_backtest_drawings.py`.
- [ ] T041 [P] [US5] Add Vitest coverage for anchor-only visibility fallback, including hiding any future anchor, restoring at the cursor, and leaving the serialized drawing state unchanged in `frontend/src/utils/backtestDrawings.test.ts`.

### Implementation for User Story 5

- [ ] T042 [US5] Implement owner-scoped drawing get/upsert operations keyed by user, run, and interval with CandleKit/schema versions, payload checks, and revision conflict handling in `backend/app/backtests/repository.py`, `backend/app/backtests/service.py`, `backend/app/backtests/schemas.py`, and `backend/app/backtests/routes.py`.
- [ ] T043 [US5] Add typed drawing load/save API calls carrying expected revisions in `frontend/src/api/backtests.api.ts` and `frontend/src/types/backtest.types.ts`.
- [ ] T044 [US5] Integrate CandleKit `DrawingController`, `DrawingEngine`, and `DrawingToolbar` for the standard create/select/reposition/edit/remove tools, and keep edits disabled until saved state is loaded in `frontend/src/components/backtest/CandleKitReplayChart.tsx` and `frontend/src/components/backtest/BacktestChartTab.tsx`.
- [ ] T045 [US5] Debounce drawing saves, flush pending writes on pause/seek/route exit, persist edits and deletions, handle revision conflicts without overwriting newer state, and preserve pinned-artifact replay-aware visibility or apply the time-anchor-only fallback without filtering creation/edit time in `frontend/src/components/backtest/CandleKitReplayChart.tsx`, `frontend/src/hooks/useBacktestReplay.ts`, and `frontend/src/utils/backtestDrawings.ts`.
- [ ] T046 [US5] Apply ThemeContext colors to CandleKit canvas and overlays, import its stylesheet once, and scope JanusEdge light/dark CSS overrides to the Backtest chart subtree in `frontend/src/components/backtest/CandleKitReplayChart.tsx`, `frontend/src/styles/backtest-candlekit.css`, and `frontend/src/main.tsx`.

**Checkpoint**: Drawing state survives reloads for the same user/run/timeframe; rewind visibility follows CandleKit behavior or the specified anchor-only fallback without mutating saved state.

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: Verify package notices, the whole application, and the documented acceptance flows.

- [ ] T047 Review CandleKit MIT and Lightweight Charts attribution requirements and add any required notices to `README.md` and the existing license/notice files.
- [ ] T048 Run the full backend pytest suite and frontend Vitest (`npm test`), lint, and production build commands from `backend/pyproject.toml` and `frontend/package.json`; resolve failures before release.
- [ ] T049 Run the authenticated browser scenarios in `specs/001-backtest-workspace/quickstart.md`, including catalog validation, Real/Backtest isolation, five-second progress polling, worker/API restart recovery, preparation outcomes, first-cursor persistence, CandleKit replay controls, replay timing and seek behavior, interval synchronization, drawing persistence, theme, and the existing Real chart.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)** must complete before implementation: CandleKit exports and dependency compatibility gate the chart integration and downloader use.
- **Foundational (Phase 2)** depends on Setup and provides the database, Flask, and frontend API boundaries required by all stories.
- **User Story 1 (Phase 3)** depends on Foundational and establishes persisted mode selection and isolation.
- **User Story 2 (Phase 4)** depends on User Story 1's Backtest mode and completes the run/account/snapshot lifecycle.
- **User Story 3 (Phase 5)** depends on ready immutable snapshots from User Story 2.
- **User Story 4 (Phase 6)** depends on mode-scoped accounts from User Story 1 and the generated run account from User Story 2; it can proceed alongside User Story 3 after User Story 2.
- **User Story 5 (Phase 7)** depends on the CandleKit replay chart from User Story 3.
- **Polish (Phase 8)** depends on all five stories.

### User Story Dependencies

- **US1 (P1)**: Starts after Foundational; independent of the run preparation implementation.
- **US2 (P1)**: Starts after US1 so run creation and navigation are available only in Backtest mode.
- **US3 (P1)**: Starts after US2 produces a ready immutable candle snapshot.
- **US4 (P2)**: Starts after US1 and US2; can run in parallel with US3.
- **US5 (P2)**: Starts after US3 provides the replay chart and shared cursor.

### Parallel Opportunities

- T005–T007 are independent after Setup and can run in parallel.
- T008–T009 are independent test files and can run in parallel before US1 implementation.
- T015–T017 are independent backend/frontend test files and can run in parallel before US2 implementation.
- T026–T028 are independent replay, aggregation, and sync test files and can run in parallel before US3 implementation.
- After US2, US3 and US4 can proceed in parallel; T037 can be written alongside US3, and US5 follows US3.
- T040–T041 can run in parallel before US5 implementation.

## Parallel Example: User Story 2

```text
Task: T015 date, timezone, and account lifecycle tests in backend/tests/test_backtests/test_backtest_service.py
Task: T016 provider and preparation-outcome tests in backend/tests/test_backtests/test_dukascopy_provider.py and backend/tests/test_backtests/test_backtest_routes.py
Task: T017 date-form validation tests in frontend/src/utils/backtestDates.test.ts
```

## Implementation Strategy

### Incremental Delivery

1. Complete Setup and Foundational, then deliver US1 to prove workspace isolation.
2. Deliver US2 to create immutable, user-owned runs with one account and reliable preparation outcomes.
3. Deliver US3 for the first usable end-to-end replay MVP.
4. Deliver US4 account discovery and US5 drawings; these can proceed independently after their listed dependencies.
5. Complete the quickstart scenarios and cross-cutting checks before release.

US1 is the first independently testable safety slice. A usable replay MVP requires US1–US3 together.

## Notes

- Every implementation task names the primary file(s) to create or change; user-story labels map directly to `spec.md`.
- `[P]` marks independent tasks on separate files with no unfinished dependencies.
- No application implementation is part of this task-generation result; these are future implementation tasks.
