---
description: "Implementation backlog for the dockable Backtest chart workspace"
---

# Tasks: Backtest Candle Replay

**Input**: Design documents in `specs/001-backtest-workspace/` (`spec.md`, `plan.md`, `data-model.md`, `contracts/backtest-api.md`, `research.md`, and `quickstart.md`).

**Prerequisites**: `plan.md` and `spec.md` are available. The project constitution remains an unratified Spec Kit placeholder and defines no project gates.

**Scope**: This backlog carries forward implementation already recorded as complete and includes the replay chart follow-mode, chart-workspace UI refinements, run deletion, the one-month warm-up-history delta, and random replay-period selection. It does not repeat the Real/Backtest separation, original run preparation, core replay transport, account integration, or initial drawing integration tasks. The old flat chart-tabs task is superseded by the dockable workspace work in User Story 3. These carry-forward notes reflect the prior task ledger, not a new code audit.

**Tests**: Focused backend and frontend tests for the versioned workspace contract, migration, panel lifecycle, run deletion, warm-up history, and random period selection are recorded below. The full quickstart UI/browser scenario task remains open until those end-to-end scenarios have been run.

**Organization**: Preserve existing story phases and task statuses, then add the follow-mode enhancement, chart UI refinement, run-deletion story, and warm-up-history delta after the carried-forward backlog. User Stories 1, 2, and 4 have no new tasks for their original scope because their work is recorded as complete in the prior task list.

**Format**: `- [ ] T### [P?] [US#?] Description with file path`

## Phase 1: Setup

**Purpose**: Add the missing dock-layout runtime dependency using the version boundary established in the plan.

- [X] T001 Pin an exact `flexlayout-react` version compatible with CandleKit 0.1.0's optional `^0.9.1` peer and update the npm lockfile in `frontend/package.json` and `frontend/package-lock.json`.

---

## Phase 2: Foundational

**Purpose**: Add the persistence key required before the workspace API can safely read and write per-run layouts.

- [X] T002 Add a unique compound MongoDB index for `(user_id, run_id)` workspace ownership in `backend/app/db.py`.

**Checkpoint**: The pinned layout dependency is installed and the workspace collection can enforce one document per owner/run.

---

## Phase 3: User Story 1 - Keep Real and Backtest activity separate (Priority: P1)

**Goal**: Preserve mode isolation established by the existing implementation.

**Independent Test**: Switch between Real and Backtest and reload; each mode shows only its own records and permitted actions.

No new tasks in this plan delta; the prior task list records this story's implementation as complete.

---

## Phase 4: User Story 2 - Prepare a one-instrument replay (Priority: P1)

**Goal**: Continue to use each ready run's immutable, user-owned one-minute snapshot and associated account.

**Independent Test**: Prepare a supported instrument/range and verify preparation status, account association, candle coverage, and recoverable job state.

No new tasks in this plan delta; the prior task list records this story's implementation as complete. The dock workspace consumes the existing ready-run contract.

---

## Phase 5: User Story 3 - Replay candles interactively (Priority: P1)

**Goal**: Replace the flat chart grid with a persistent dockable workspace while retaining the run's single replay cursor and cursor-bounded chart data. Keep each pane following its latest revealed candle until the user navigates away, then provide a return-to-latest action.

**Independent Test**: A new run opens with one 1m chart snapped to the latest candle. Add and reorder tabs, move one between groups, split by dropping it at a pane edge, resize panes, and close tabs while retaining one chart. Reload and confirm layout, active tabs, stable ids, intervals, and the shared replay position are restored. Migrate legacy flat tabs without losing their ids or intervals. Confirm follow mode moves the latest revealed candle with playback and manual cursor changes; pan away in either direction, confirm the viewport remains detached, then use the return button or existing time-axis double-click gesture to snap back.

### Tests for User Story 3

- [X] T003 [P] [US3] Add backend tests for workspace ownership, schema/type/interval validation, minimum-one-chart enforcement, legacy-tab reads, and revision conflict behavior in `backend/tests/test_backtests/test_backtest_chart_workspaces.py`.
- [X] T004 [P] [US3] Add frontend tests for one-chart/1m initialization, legacy flat-tab conversion preserving ids and intervals, layout/panel identity round trips, and conflict handling that retains a local draft in `frontend/src/utils/backtestWorkspace.test.ts`.

### Implementation for User Story 3

- [X] T005 [P] [US3] Define the versioned chart-workspace schema and owner/run-scoped repository operations, including atomic expected-revision compare-and-swap, in `backend/app/backtests/schemas.py` and `backend/app/backtests/repository.py`.
- [X] T006 [US3] Implement authenticated GET/PUT chart-workspace service and routes in `backend/app/backtests/service.py` and `backend/app/backtests/routes.py`; GET returns a saved layout or ordered legacy chart tabs, and PUT validates layout/panel correspondence and returns 409 for stale revisions.
- [X] T007 [P] [US3] Add workspace request/response types and a CandleKit `LayoutPersistence` adapter backed by the authenticated chart-workspace API in `frontend/src/types/backtest.types.ts` and `frontend/src/api/backtests.api.ts`.
- [X] T008 [US3] Create `BacktestChartWorkspace` with `WorkspaceProvider`, `FlexLayoutAdapter`, and a registered JanusEdge chart panel; initialize one stable-id 1m chart or convert legacy records into visible sibling panes, then persist initialization before enabling edits in `frontend/src/components/backtest/BacktestChartWorkspace.tsx` and `frontend/src/utils/backtestWorkspace.ts`.
- [X] T009 [US3] Configure workspace operations so the tab-row `+` action activates a tab in the focused group, tab drag reorders/moves, edge drops split panes, splitters resize, and closing the final chart is rejected in `frontend/src/components/backtest/BacktestChartWorkspace.tsx`.
- [X] T010 [US3] Replace the flat chart grid with the persisted workspace while keeping all chart panels connected to the existing single run replay controller and crosshair synchronization in `frontend/src/pages/BacktestReplayPage.tsx` and `frontend/src/hooks/useBacktestReplay.ts`.

**Checkpoint**: The saved dock tree survives navigation/reload and all chart panels continue to reflect the same no-look-ahead replay state.

---

## Phase 6: User Story 4 - Find a run through its Backtest account (Priority: P2)

**Goal**: Retain distinct Backtest account identification for each run.

**Independent Test**: Select among multiple Backtest accounts and verify each identifies only its associated run.

No new tasks in this plan delta; the prior task list records this story's implementation as complete.

---

## Phase 7: User Story 5 - Annotate replay charts (Priority: P2)

**Goal**: Keep drawing state correct when a chart tab moves and its panel unmounts/remounts.

**Independent Test**: Move a panel while a drawing save is pending; confirm the save completes, the same chart id/timeframe reloads the same drawings, and replay/sync listeners are registered only once.

### Tests for User Story 5

- [X] T011 [US5] Add a panel-move lifecycle regression test for pending drawing writes and replay/sync listener cleanup in `frontend/src/components/backtest/BacktestChartWorkspace.test.tsx`.

### Implementation for User Story 5

- [X] T012 [US5] Flush pending drawing persistence and unregister/re-register drawing, replay, and sync subscriptions safely across chart-panel unmount/remount in `frontend/src/components/backtest/BacktestChartTab.tsx`, `frontend/src/components/backtest/CandleKitReplayChart.tsx`, and `frontend/src/hooks/useBacktestChartSync.ts`.

**Checkpoint**: Moving a tab preserves its stable drawing scope and does not lose pending saves or duplicate chart subscriptions.

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: Validate the new layout against the existing application and documented acceptance scenarios.

- [X] T013 Run backend pytest, frontend Vitest, lint, and production build after workspace integration; resolve regressions and the previously recorded standard Vite build-loader access error using `backend/pyproject.toml`, `frontend/package.json`, and `frontend/vite.config.ts`.
- [ ] T014 After UI validation is resumed, execute the chart-workspace migration, docking, persistence, concurrency, warm-up-history and selected-replay-boundary, panel-move, replay-follow, and return-to-latest scenarios in `specs/001-backtest-workspace/quickstart.md`.

---

## Phase 9: User Story 3 follow-mode enhancement (Priority: P1)

**Purpose**: Add follow behavior to the already-integrated replay chart workspace. Browser validation in T014 is not a prerequisite for implementing these tasks.

### Tests

- [X] T015 [US3] Add frontend tests for pane-local follow transitions (initial snap, playback/step/seek updates, pan backward and forward, detached-range preservation, independent viewport changes, latest catch-up, and no horizontal jump on an in-place higher-timeframe bar update) in `frontend/src/utils/backtestChartFollow.test.ts` and `frontend/src/components/backtest/CandleKitReplayChart.test.tsx`.

### Implementation

- [X] T016 [US3] Implement pane-local follow tracking from the time-scale position and latest cursor-bounded chart bar; snap new/remounted panes to latest, follow replay cursor changes only while snapped, and preserve each detached pane's range as replay advances in `frontend/src/hooks/useBacktestChartSync.ts` and `frontend/src/utils/backtestChartFollow.ts`. Coalesce replay-driven scroll updates and use non-animated positioning at 20x; do not scroll horizontally for in-place updates to an active higher-timeframe bar.
- [X] T017 [US3] Add an accessible lower-right return-to-latest button that appears only when the pane is away from the latest revealed candle, restores follow when selected, and preserves the existing double-click time-axis snap behavior in `frontend/src/components/backtest/BacktestChartTab.tsx`, `frontend/src/components/backtest/CandleKitReplayChart.tsx`, and `frontend/src/styles/backtest-candlekit.css`.

**Checkpoint**: Playback and manual cursor changes move each following pane to the latest revealed candle. Panned panes remain detached until brought back to the real-time edge; the button is available only while detached.

---

## Phase 10: User Story 3 chart controls and workspace chrome (Priority: P1)

**Purpose**: Match the chart controls and workspace chrome to the clarified screenshot reference while preserving accessibility and interval validation.

### Implementation

- [X] T018 [US3] Replace the numeric interval field with a compact, chart-styled timeframe dropdown; open a popup from Custom and display the applied custom interval directly in the selector in `frontend/src/components/backtest/BacktestChartTab.tsx` and `frontend/src/styles/backtest-candlekit.css`.
- [X] T019 [US3] Remove the visible chart title/timeframe label, volume explanation, and separate interval header; keep the quoted-liquidity explanation available to assistive technology in `frontend/src/components/backtest/BacktestChartTab.tsx`.
- [X] T020 [US3] Remove the standalone workspace toolbar and drag instructions, place an accessible `+` chart-creation button in the tab row, and reserve tab space so it does not cover chart tabs in `frontend/src/components/backtest/BacktestChartWorkspace.tsx` and `frontend/src/styles/backtest-candlekit.css`.

**Checkpoint**: Each chart has a compact timeframe selector inside the upper-left plot area, custom minutes are validated, and the tab row contains `+` without the redundant workspace toolbar.

---

## Phase 11: User Story 6 - Delete a run and its activity (Priority: P1)

**Goal**: Let the owner permanently remove a preparing or ready run together with its dedicated Backtest account, linked trades, and run-owned replay data, while preserving unrelated and Real records.

**Independent Test**: Cancel a deletion confirmation and verify nothing changes. Confirm deletion of a ready run containing linked trades and verify that completion occurs only after its run/account/trade/dependent records are physically absent and its MinIO prefix is empty. Repeat during active preparation and after interrupting cleanup; the run must never become ready and cleanup must resume without touching another run or Real data.

### Tests for User Story 6

- [X] T021 [P] [US6] Add backend deletion tests for owner isolation, preparing-run worker fencing, restart recovery, and idempotent cleanup. On completion, assert the run/deletion marker, account, linked trade documents, trade-owned dependent records/files, and preparation/replay/workspace/drawing records are absent, and listing the run's MinIO prefix returns zero objects (including unreferenced objects) in `backend/tests/test_backtests/test_backtest_run_deletion.py`; confirm these tests fail before implementation.
- [X] T022 [P] [US6] Add frontend tests for confirmation/cancel behavior, pending-deletion display, and list refresh/error handling in `frontend/src/components/backtest/BacktestRunList.test.tsx`; confirm these tests fail before implementation.

### Implementation for User Story 6

- [X] T023 [US6] Add the durable owner-scoped `deleting` run state and authenticated `DELETE /api/backtest/runs/{run_id}` contract; fence replay, workspace, drawing, and preparation writes once deletion begins in `backend/app/backtests/repository.py`, `backend/app/backtests/service.py`, and `backend/app/backtests/routes.py`.
- [X] T024 [P] [US6] Make the worker resume and idempotently purge deleting runs: physically remove every object under the run's MinIO prefix and verify it is empty, remove the preparation job, chart tabs/workspace, drawings, and every linked trade plus its dependent data, then remove the dedicated account and finally the run/deletion marker. Interim query filtering may hide pending resources but must not substitute for the purge. Implement in `backend/app/backtests/worker.py`, `backend/app/backtests/repository.py`, `backend/app/trades/service.py`, `backend/app/repositories/trade_repo.py`, and `backend/app/workspace_mode/service.py`.
- [X] T025 [US6] Add the delete API/type handling and run-list confirmation flow; treat 202 as pending cleanup, show completion only after the run disappears following physical purge, keep cancel non-mutating, and prevent opening a deleting run in `frontend/src/api/backtests.api.ts`, `frontend/src/types/backtest.types.ts`, `frontend/src/components/backtest/BacktestRunList.tsx`, and `frontend/src/pages/BacktestRunListPage.tsx`.

**Checkpoint**: A 202 response and interim hiding are treated only as pending cleanup. Confirm deletion completes only after the run/deletion marker, account, linked trades and dependent data are absent and the run's MinIO prefix is empty; cleanup survives restarts and no unrelated Backtest or Real data changes.

---

## Phase 12: User Story 2 - Prepare chart warm-up history (Priority: P1)

**Goal**: Include whatever one-minute history is available in the calendar month before the selected replay start without changing the user-selected replay period or its one-year limit.

**Independent Test**: Prepare runs with complete, partial, and unavailable warm-up history. Confirm available pre-start candles are retained, selected-period data alone determines readiness and coverage, and a run with no selected-period candles remains no-data even if earlier candles exist.

### Tests for User Story 2

- [X] T026 [P] [US2] Add backend tests for preceding-calendar-month calculation (including end-of-month and daylight-saving boundaries), best-effort warm-up availability, and selected-period-only no-data/readiness behavior in `backend/tests/test_backtests/test_backtest_service.py`.
### Implementation for User Story 2

- [X] T027 [US2] Calculate the warm-up boundary from the selected local start date, prepare and recover the extended UTC-date range, retain available context through selected replay data in the immutable snapshot, and keep readiness and reported replay coverage based only on the selected period in `backend/app/backtests/service.py`, `backend/app/backtests/preparation_jobs.py`, `backend/app/backtests/worker.py`, and `backend/app/backtests/snapshot_store.py`.

**Checkpoint**: The immutable snapshot retains available warm-up and selected-period candles; missing warm-up does not block a run with selected-period data, and warm-up-only data remains a no-data result.

---

## Phase 13: User Story 3 - Start replay after chart-context history (Priority: P1)

**Goal**: Show available warm-up candles before the initial replay cursor as historical chart context while keeping every replay action inside the user-selected period.

**Independent Test**: Open a ready run with prior-month history. Verify the earlier chart bars are visible, the saved cursor points at the first selected-period candle, stepping backward at that point cannot enter context, and seeking before the selected start clamps to that candle.

### Tests for User Story 3

- [X] T028 [P] [US3] Add replay API tests proving the initial cursor uses `replay_start_source_index`, warm-up indexes cannot be persisted as replay positions, and seeks before the replay start clamp to its first eligible candle in `backend/tests/test_backtests/test_backtest_replay_routes.py`.
- [X] T029 [P] [US3] Add frontend tests for showing pre-start candles as historical context at initial open, starting replay at the selected period, and clamping backward steps and pre-start seeks in `frontend/src/utils/backtestReplay.test.ts` and `frontend/src/components/backtest/CandleKitReplayChart.test.tsx`.

### Implementation for User Story 3

- [X] T030 [US3] Persist and return the first eligible replay-source index with the ready run, initialize the saved cursor there, and reject cursor writes outside the selected replay interval while allowing candle reads from the full immutable context snapshot in `backend/app/backtests/schemas.py`, `backend/app/backtests/repository.py`, `backend/app/backtests/service.py`, and `backend/app/backtests/routes.py`.
- [X] T031 [US3] Load pre-start candles as chart context while initializing the shared replay controller at the returned replay-start index; keep playback, step, seek, progress, and completion inside the selected replay period in `frontend/src/types/backtest.types.ts`, `frontend/src/api/backtests.api.ts`, `frontend/src/hooks/useBacktestReplay.ts`, and `frontend/src/components/backtest/CandleKitReplayChart.tsx`.

---

## Phase 14: User Story 7 - Select a random replay period (Priority: P1)

**Goal**: Let users request a 1, 3, 6, or 12 calendar-month replay period whose start date is chosen randomly from dates with available candles, using a restart-safe bounded worker search.

**Independent Test**: Use a fixed cutoff, controlled randomness, and fake candle-provider results to verify eligible date bounds, no-replacement sampling, the per-year probe limit, successful selection, exhaustion, provider errors, restart recovery, account creation timing, and deletion fencing. Confirm the form disables dates only in random mode and the manual request remains unchanged.

### Tests

- [X] T035 [US7] Add backend tests for the random create contract, timezone-yesterday cutoff, calendar-duration and latest-start boundaries, random year/date sampling without replacement, ten-probe-per-year exhaustion, provider-error classification, worker restart recovery, DST-local day filtering, deletion fencing, one-account creation, and normal preparation continuation in `backend/tests/test_backtests/test_random_period_selection.py` and `backend/tests/test_backtests/test_backtest_routes.py`.
- [X] T036 [US7] Add frontend tests for duration choices, disabled date controls in random mode, unchanged manual request shape, pending selection status, and dismissible instrument/duration failure notices in `frontend/src/components/backtest/BacktestRunForm.test.tsx` and `frontend/src/components/backtest/BacktestRunList.test.tsx`.

### Implementation

- [X] T037 [US7] Add the random-selection request and pending run state; persist the fixed local-yesterday cutoff, eligible bounds, year/date attempts, and pending candidate; implement bounded COMB local-day probes, provider-error handling, selection recovery, post-hit date/account transition, and deletion fencing in `backend/app/backtests/schemas.py`, `backend/app/backtests/preparation_jobs.py`, `backend/app/backtests/repository.py`, `backend/app/backtests/service.py`, `backend/app/backtests/routes.py`, and `backend/app/backtests/worker.py`.
- [X] T038 [US7] Add the random/manual mode selector and duration controls, disable manual dates only in random mode, preserve manual request payloads, display unresolved selection state and nullable dates/account, poll while selecting, and render duration-aware failure/deletion messages in `frontend/src/components/backtest/BacktestRunForm.tsx`, `frontend/src/components/backtest/BacktestRunList.tsx`, `frontend/src/pages/BacktestRunListPage.tsx`, `frontend/src/types/backtest.types.ts`, `frontend/src/utils/backtestRunDeletion.ts`, and `frontend/src/utils/backtestRunRequest.ts`.
- [X] T039 [US7] Update the normative specification, architecture, data model, API contract, research decisions, implementation backlog, and quickstart scenarios for random period selection in `specs/001-backtest-workspace/spec.md`, `plan.md`, `data-model.md`, `contracts/backtest-api.md`, `research.md`, `tasks.md`, and `quickstart.md`.

**Checkpoint**: Manual runs retain their request and preparation behavior. Random runs remain date/account-free while searching, resume from persisted attempts, either resolve into normal warm-up/preparation or emit a dismissible duration-aware failure, and are fenced by deletion.

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependency; completes the exact layout peer pin.
- **Foundational (Phase 2)**: Depends on Setup and blocks workspace API persistence.
- **User Stories 1 and 2 (Phases 3 and 4)**: Previously delivered; US3 relies on the ready-run behavior from US2.
- **User Story 3 (Phase 5)**: Depends on Setup and Foundational; the replay/run API and dock workspace it extends are recorded as delivered in US2/US3 work from the previous backlog. Add follow tests in T015 before implementing T016-T017; follow logic depends on the shared replay controller and existing chart panel lifecycle.
- **User Story 4 (Phase 6)**: Previously delivered; independent of the dock-layout change.
- **User Story 5 (Phase 7)**: Depends on US3's docked chart panel and move behavior.
- **Polish (Phase 8)**: T013 depends on implementation completion; T014 remains open until the remaining UI validation scenarios are completed.
- **US3 follow-mode enhancement (Phase 9)**: Depends on the existing chart workspace and shared replay controller from Phase 5. Add tests in T015 before implementing T016-T017; T017 depends on follow-state and snap APIs from T016. T014 is not a prerequisite and remains deferred until UI validation resumes.
- **US3 chart UI refinement (Phase 10)**: Depends on the existing chart workspace from Phase 5. T018-T020 are implemented as a refinement of that workspace; full UI validation remains tracked separately by T014.
- **US6 deletion (Phase 11)**: Depends on the existing run/account lifecycle from US2 and account association from US4. T021-T022 can be authored in parallel; T023 establishes the deletion fence and endpoint, after which T024 and T025 can proceed in parallel on backend cleanup/query filtering and frontend controls.
- **Warm-up preparation (Phase 12)**: T026 validates date-window and selected-period readiness behavior before T027 implements it.
- **Warm-up replay (Phase 13)**: T028 and T029 tests can be authored in parallel. T030 depends on the replay-start index produced by T027 and validated by T028. T031 depends on the backend response/cursor contract in T030 and the frontend behavior tests in T029.
- **US7 random period selection (Phase 14)**: T035 and T036 establish backend and frontend contracts before T037-T038. T037 persists worker selection and resolves the run before account creation; T038 consumes the pending and resolved states. T039 captures the shipped behavior in the design and validation artifacts.

### User Story Dependencies

- **US1 (P1)**: Previously delivered; no new tasks.
- **US2 (P1)**: Previously delivered; supplies ready runs for US3.
- **US3 (P1)**: Starts after T001-T002 and the existing ready-run/replay foundation.
- **US3 follow-mode delta (P1)**: Extends the delivered replay chart panes; T015 precedes T016, and T017 uses the state/action interfaces implemented by T016.
- **US4 (P2)**: Previously delivered; no new tasks.
- **US5 (P2)**: Starts after US3 panel moves are implemented.
- **US6 (P1)**: Extends the existing US2 run and US4 account relationship; independent of chart layout and drawing behavior. It does not add trade creation or order entry.
- **US2 warm-up delta (Phase 12)**: Extends the delivered run preparation; T026 precedes T027.
- **US3 warm-up delta (Phase 13)**: Extends the delivered replay controller; T028-T029 precede T030-T031, with the frontend implementation consuming the persisted cursor boundary from the backend contract.

### Parallel Opportunities

- T003 and T004 can be authored in parallel because they target separate backend and frontend test files.
- After those tests are in place, T005 and T007 can proceed in parallel on separate backend and frontend files against the already documented contract.
- Within US5, complete T011 before T012; backend tests and frontend tests from US3 can run independently.
- T026, T028, and T029 target separate backend or frontend test files and can be authored in parallel; implementation must wait for its corresponding tests.
- T035 and T036 target separate backend and frontend test files and can be authored independently; implementation must wait for both contract test sets.

## Parallel Example: User Story 3

```text
Task: T003 backend chart-workspace contract and migration tests in backend/tests/test_backtests/test_backtest_chart_workspaces.py
Task: T004 frontend workspace bootstrap and legacy conversion tests in frontend/src/utils/backtestWorkspace.test.ts
```

## Implementation Strategy

### MVP for This Plan Delta

1. Complete Setup and Foundational.
2. Complete User Story 3 so a run has one default chart and its dockable layout persists.
3. Complete User Story 5 lifecycle handling before release so moving a panel cannot lose drawings or leak subscriptions.
4. Complete the US3 follow-mode tasks so each pane can track or inspect replay history independently.
5. Run headless automated checks after implementation. Keep T014 open until the remaining quickstart UI scenarios are completed.
6. Complete User Story 6 before enabling any future Backtest trade-recording flow, so a run's dedicated account cannot outlive its run.
7. Implement the warm-up history extension after tests define its calendar-date boundary, partial-availability behavior, and separation from replay-eligible candles.
8. Implement random selection as a persisted worker phase before normal preparation; keep the manual request path unchanged and create the account only after a candle-bearing start date is found.

## Notes

- This list contains implementation and validation work; T039 is the explicit documentation update for the random-period feature.
- All generated task IDs are sequential. `[P]` is used only where the tasks can work on separate files without waiting for unfinished implementation.
- The previous task T034 for flat `/chart-tabs` persistence is superseded by T003-T010; do not implement a second flat layout source of truth.
- T014 covers the full quickstart UI/browser validation matrix and remains unchecked because that complete matrix was not run as part of the current source and documentation update.
