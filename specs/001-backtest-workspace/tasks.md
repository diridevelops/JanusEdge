---
description: "Implementation backlog for Backtest replay and simulated trading"
---

# Tasks: Backtest Candle Replay

**Input**: Design documents in `specs/001-backtest-workspace/` (`spec.md`, `plan.md`, `data-model.md`, `contracts/backtest-api.md`, `research.md`, and `quickstart.md`).

**Prerequisites**: `plan.md` and `spec.md` are available. The project constitution remains an unratified Spec Kit placeholder and defines no project gates.

**Scope**: This backlog carries forward the original replay/workspace work, deletion, warm-up, random selection, Blind mode, and simulated trading, then records the implemented shared cache, cache recovery, HistData source, portable Backtest backups, scale-in, linked trade chart cap, and keyboard transport updates. The old flat chart-tabs task is superseded by the dockable workspace work in User Story 3. Checked implementation items indicate source/test coverage exists; they do not assert that the full test suite or browser matrix was run in this documentation pass.

**Tests**: Focused backend tests for the versioned workspace contract, migration, panel lifecycle, run deletion, warm-up, random selection, Blind mode, simulation, shared candle cache, manual import, linked trade charts, and backup/restore are tracked below. The full quickstart UI/browser scenario task remains open until those end-to-end scenarios have been run.

**Organization**: Preserve the original story phases and completion history, then record later implementation deltas in Phase 17. User Stories 1, 2, and 4 have no new tasks for their original scope because their work is recorded as complete in the prior task list.

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

**Goal**: Continue to use each ready run's metadata-only manifest over user-owned cache data and its associated account.

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
- [ ] T014 After UI validation is resumed, execute the chart-workspace migration, docking, persistence, concurrency, warm-up-history and selected-replay-boundary, panel-move, replay-follow, return-to-latest, and User Story 9 scenarios—including exact range-touch limit fills, protection edits, per-position entry/SL/TP indicators, independent BE/X controls for multiple positions, display-only unrealized P&L, stop-moved tagging, and account results—in `specs/001-backtest-workspace/quickstart.md`.

---

## Phase 9: User Story 3 follow-mode enhancement (Priority: P1)

**Purpose**: Add follow behavior to the already-integrated replay chart workspace. Browser validation in T014 is not a prerequisite for implementing these tasks.

### Tests

- [X] T015 [US3] Add frontend tests for pane-local follow transitions (initial snap, playback/step/seek updates, pan backward and forward, detached-range preservation, independent viewport changes, latest catch-up, and no horizontal jump on an in-place higher-timeframe bar update) in `frontend/src/utils/backtestChartFollow.test.ts` and `frontend/src/components/backtest/CandleKitReplayChart.test.tsx`.

### Implementation

- [X] T016 [US3] Implement pane-local follow tracking from the time-scale position and latest cursor-bounded chart bar; snap new/remounted panes to latest, follow replay cursor changes only while snapped, and preserve each detached pane's range as replay advances in `frontend/src/hooks/useBacktestChartSync.ts` and `frontend/src/utils/backtestChartFollow.ts`. Coalesce replay-driven scroll updates and use non-animated positioning at 30x; do not scroll horizontally for in-place updates to an active higher-timeframe bar.
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

**Independent Test**: Cancel a deletion confirmation and verify nothing changes. Confirm deletion of a ready run containing linked trades and verify run/account/trade/dependent records are physically absent while shared candle-cache data remains. Repeat during active preparation and after interrupting cleanup; the run must never become ready and cleanup must resume without touching another run or Real data.

### Tests for User Story 6

- [X] T021 [P] [US6] Add backend deletion tests for owner isolation, preparing-run worker fencing, restart recovery, and idempotent cleanup. On completion, assert the run/deletion marker, account, linked trade documents, trade-owned dependent records/files, and preparation/replay/workspace/drawing records are absent while shared cache records are retained in `backend/tests/test_backtests/test_backtest_run_deletion.py`.
- [X] T022 [P] [US6] Add frontend tests for confirmation/cancel behavior, pending-deletion display, and list refresh/error handling in `frontend/src/components/backtest/BacktestRunList.test.tsx`; confirm these tests fail before implementation.

### Implementation for User Story 6

- [X] T023 [US6] Add the durable owner-scoped `deleting` run state and authenticated `DELETE /api/backtest/runs/{run_id}` contract; fence replay, workspace, drawing, and preparation writes once deletion begins in `backend/app/backtests/repository.py`, `backend/app/backtests/service.py`, and `backend/app/backtests/routes.py`.
- [X] T024 [P] [US6] Make the worker resume and idempotently purge deleting runs: remove preparation/recovery jobs, chart tabs/workspace, drawings, simulation records, and every linked trade plus its dependent data, then remove the dedicated account and finally the run/deletion marker. Retain shared Dukascopy and manual dataset objects. Interim query filtering may hide pending resources but must not substitute for the purge. Implement in `backend/app/backtests/worker.py`, `backend/app/backtests/repository.py`, `backend/app/trades/service.py`, `backend/app/repositories/trade_repo.py`, and `backend/app/workspace_mode/service.py`.
- [X] T025 [US6] Add the delete API/type handling and run-list confirmation flow; treat 202 as pending cleanup, show completion only after the run disappears following physical purge, keep cancel non-mutating, and prevent opening a deleting run in `frontend/src/api/backtests.api.ts`, `frontend/src/types/backtest.types.ts`, `frontend/src/components/backtest/BacktestRunList.tsx`, and `frontend/src/pages/BacktestRunListPage.tsx`.

**Checkpoint**: A 202 response and interim hiding are treated only as pending cleanup. Confirm deletion completes only after the run/deletion marker, account, linked trades and dependent data are absent; shared cache and manual datasets remain. Cleanup survives restarts and no unrelated Backtest or Real data changes.

---

## Phase 12: User Story 2 - Prepare chart warm-up history (Priority: P1)

**Goal**: Include whatever one-minute history is available in the user-requested `warmup_days` before the selected replay start without changing the user-selected replay period or its one-year limit.

**Independent Test**: Prepare runs with complete, partial, and unavailable warm-up history. Confirm available pre-start candles are retained, selected-period data alone determines readiness and coverage, and a run with no selected-period candles remains no-data even if earlier candles exist.

### Tests for User Story 2

- [X] T026 [P] [US2] Add backend tests for the nonnegative `warmup_days` boundary, source-specific date/timezone conversion, best-effort warm-up availability, and selected-period-only no-data/readiness behavior in `backend/tests/test_backtests/test_backtest_service.py`.
### Implementation for User Story 2

- [X] T027 [US2] Calculate the warm-up boundary from the selected start date and `warmup_days` using the source-specific calendar, prepare and recover the extended UTC-date range, retain available context through manifest references, and keep readiness and reported replay coverage based only on the selected period in `backend/app/backtests/service.py`, `backend/app/backtests/preparation_jobs.py`, `backend/app/backtests/worker.py`, and `backend/app/backtests/snapshot_store.py`.

**Checkpoint**: The source manifest references available warm-up and selected-period candles; missing warm-up does not block a run with selected-period data, and warm-up-only data remains a no-data result.

---

## Phase 13: User Story 3 - Start replay after chart-context history (Priority: P1)

**Goal**: Show available warm-up candles before the initial replay cursor as historical chart context while keeping every replay action inside the user-selected period.

**Independent Test**: Open a ready run with prior-month history. Verify the earlier chart bars are visible, the saved cursor points at the first selected-period candle, stepping backward at that point cannot enter context, and seeking before the selected start clamps to that candle.

### Tests for User Story 3

- [X] T028 [P] [US3] Add replay API tests proving the initial cursor uses `replay_start_source_index`, warm-up indexes cannot be persisted as replay positions, and seeks before the replay start clamp to its first eligible candle in `backend/tests/test_backtests/test_backtest_replay_routes.py`.
- [X] T029 [P] [US3] Add frontend tests for showing pre-start candles as historical context at initial open, starting replay at the selected period, and clamping backward steps and pre-start seeks in `frontend/src/utils/backtestReplay.test.ts` and `frontend/src/components/backtest/CandleKitReplayChart.test.tsx`.

### Implementation for User Story 3

- [X] T030 [US3] Persist and return the first eligible replay-source index with the ready run, initialize the saved cursor there, and reject cursor writes outside the selected replay interval while allowing candle reads from the full manifest-referenced context in `backend/app/backtests/schemas.py`, `backend/app/backtests/repository.py`, `backend/app/backtests/service.py`, and `backend/app/backtests/routes.py`.
- [X] T031 [US3] Load pre-start candles as chart context while initializing the shared replay controller at the returned replay-start index; keep playback, step, seek, progress, and completion inside the selected replay period in `frontend/src/types/backtest.types.ts`, `frontend/src/api/backtests.api.ts`, `frontend/src/hooks/useBacktestReplay.ts`, and `frontend/src/components/backtest/CandleKitReplayChart.tsx`.

---

## Phase 14: User Story 7 - Select a random replay period (Priority: P1)

**Goal**: Let users request a 1, 3, 6, or 12 calendar-month replay period whose start date is chosen randomly from dates with available candles, using a restart-safe bounded worker search.

**Independent Test**: Use a fixed cutoff, controlled randomness, and fake candle-provider results to verify eligible date bounds, no-replacement sampling, the per-year probe limit, successful selection, exhaustion, provider errors, restart recovery, account creation timing, and deletion fencing. Confirm the form disables dates only in random mode and the manual request remains unchanged.

### Tests

- [X] T032 [US7] Add backend tests for the random create contract, timezone-yesterday cutoff, calendar-duration and latest-start boundaries, random year/date sampling without replacement, ten-probe-per-year exhaustion, provider-error classification, worker restart recovery, DST-local day filtering, deletion fencing, one-account creation, and normal preparation continuation in `backend/tests/test_backtests/test_random_period_selection.py` and `backend/tests/test_backtests/test_backtest_routes.py`.
- [X] T033 [US7] Add frontend tests for duration choices, disabled date controls in random mode, unchanged manual request shape, pending selection status, and dismissible instrument/duration failure notices in `frontend/src/components/backtest/BacktestRunForm.test.tsx` and `frontend/src/components/backtest/BacktestRunList.test.tsx`.

### Implementation

- [X] T034 [US7] Add the random-selection request and pending run state; persist the fixed local-yesterday cutoff, eligible bounds, year/date attempts, and pending candidate; implement bounded COMB local-day probes, provider-error handling, selection recovery, post-hit date/account transition, and deletion fencing in `backend/app/backtests/schemas.py`, `backend/app/backtests/preparation_jobs.py`, `backend/app/backtests/repository.py`, `backend/app/backtests/service.py`, `backend/app/backtests/routes.py`, and `backend/app/backtests/worker.py`.
- [X] T035 [US7] Add the random/manual mode selector and duration controls, disable manual dates only in random mode, preserve manual request payloads, display unresolved selection state and nullable dates/account, poll while selecting, and render duration-aware failure/deletion messages in `frontend/src/components/backtest/BacktestRunForm.tsx`, `frontend/src/components/backtest/BacktestRunList.tsx`, `frontend/src/pages/BacktestRunListPage.tsx`, `frontend/src/types/backtest.types.ts`, `frontend/src/utils/backtestRunDeletion.ts`, and `frontend/src/utils/backtestRunRequest.ts`.
- [X] T036 [US7] Update the normative specification, architecture, data model, API contract, research decisions, implementation backlog, and quickstart scenarios for random period selection in `specs/001-backtest-workspace/spec.md`, `plan.md`, `data-model.md`, `contracts/backtest-api.md`, `research.md`, `tasks.md`, and `quickstart.md`.

**Checkpoint**: Manual runs retain their request and preparation behavior. Random runs remain date/account-free while searching, resume from persisted attempts, either resolve into normal warm-up/preparation or emit a dismissible duration-aware failure, and are fenced by deletion.

---

## Phase 15: User Story 8 - Create and replay a blind run (Priority: P1)

**Goal**: Let users replay a random period without rendered calendar dates or raw prices, using a stable normalized price reference while retaining canonical data for replay.

**Independent Test**: Verify the blind form contract, blind account label and date suppression, normalized chart values anchored to the first replay candle, timezone-aware weekday/time labels, invalid-reference failure, and unchanged non-blind request/display behavior. Trade recording remains unavailable.

### Specification

- [X] T037 [US8] Update the normative feature requirements, architecture, data model, API contract, research decisions, implementation backlog, and quickstart with Blind mode behavior and future Journal masking rules in `specs/001-backtest-workspace/spec.md`, `plan.md`, `data-model.md`, `contracts/backtest-api.md`, `research.md`, `tasks.md`, and `quickstart.md`.

### Tests

- [X] T038 [US8] Add backend tests for optional `blind_mode`, its random-selection requirement, legacy/default false behavior, blind account labels without dates, persistence of the normalized reference from the first replay-period candle, and zero/non-finite reference failure before readiness in `backend/tests/test_backtests/test_blind_mode.py` and `backend/tests/test_backtests/test_backtest_routes.py`.
- [X] T039 [US8] Add frontend tests for the unchecked checkbox, forced/locked random selection, unlock on uncheck, preserved request shapes, blind date suppression, normalized OHLC/price-coordinate rendering, and weekday/time formatting for the replay cursor, axes, and crosshair in `frontend/src/components/backtest/BacktestRunForm.test.tsx`, `frontend/src/components/backtest/BacktestRunList.test.tsx`, and focused backtest price/time utility tests.

### Implementation

- [X] T040 [US8] Persist the immutable run blind flag and normalized reference, require random selection for blind requests, set the reference from the first available replay-period candle before ready, fail clearly for zero/non-finite references, and generate date-free “blind” account labels with collision suffixes in `backend/app/backtests/schemas.py`, `backend/app/backtests/service.py`, `backend/app/backtests/repository.py`, `backend/app/backtests/worker.py`, and `backend/app/backtests/routes.py`.
- [X] T041 [US8] Add the Blind mode form behavior and render-only privacy transformation. Hide full dates and raw prices throughout blind run/list/notice/account/chart surfaces; format replay cursor timestamps, chart ticks, and tooltips as configured-timezone weekday/time; apply the fixed `100 × P / referencePrice` scale to replay and warm-up OHLC, labels, and drawings in `frontend/src/components/backtest/BacktestRunForm.tsx`, `frontend/src/components/backtest/BacktestRunList.tsx`, `frontend/src/pages/BacktestRunListPage.tsx`, `frontend/src/pages/BacktestReplayPage.tsx`, and the Backtest chart/time/price utilities. Do not add trade entry or recording.

**Checkpoint**: Blind runs always use the existing random-selection lifecycle; canonical data remains unchanged and rendered surfaces reveal no full dates or raw prices. Trade capture is implemented separately in User Story 9, using the Blind display rules established here.

---

## Phase 16: User Story 9 - Practice simulated trades during replay (Priority: P1)

**Goal**: Let a trader place and manage market and limit orders during replay, size exposure from the run's risk settings, manage each position's OCO protection from independent chart controls, and review fully closed trades and results without sending orders to a broker.

**Independent Test**: Create a run with default and overridden balance/risk settings. In a ready replay, place auto-sized and manual market/limit entries with both protections; verify market next-open fills, future range-touch-only limit fills at the exact submitted price (a gap without range touch remains pending), OCO and FIFO behavior, costs and conversion, per-position entry/stop/target chart indicators, independent drag/BE/X controls with multiple open positions, manual close, immutable initial risk, idempotent `stop-moved` tagging under General, Journal publication only after full close, account balance/analytics, reset, deletion, and Blind-mode privacy.

### Tests for User Story 9

- [x] T042 [P] [US9] Add backend tests for required finite instrument-precision stop/target values on the correct sides, 0.001-lot minimum/increments, next-open market fills, no use of the market fill candle's range, limit fills only when an eligible future high-low range reaches the submitted price, exact limit fill prices with gap-only non-fills, delayed bracket activation, OCO stop precedence and adverse stop gaps, FIFO/reversal accounting, costs/FX, per-position as-of unrealized USD P&L before hypothetical exit costs without balance impact, manual close at the current candle close, protection edits, immutable initial risk, tag idempotency, committed balance, retry recovery, reset, and deletion in `backend/tests/test_backtests/test_backtest_simulation.py`.
- [x] T043 [P] [US9] Add frontend tests for USD 10,000/1% run defaults, enabled auto-size and manual-size mode, a collapsible right-side entry panel, 1R initial target, preview movement and long/short orientation, and fixed market preview entry. Test filled-position entry/stop/target indicators, immutable entry lines, independent stop/target dragging, BE-to-entry validation, X close behavior, quantity and as-of unrealized USD P&L before hypothetical exit costs without balance changes, overlapping levels and multiple positions whose controls remain independent, cost settings, and blind price/date masking in `frontend/src/components/backtest/BacktestRunForm.test.tsx`, `frontend/src/components/backtest/BacktestEntryPanel.test.tsx`, `frontend/src/components/backtest/BacktestBracketPreview.test.tsx`, `frontend/src/components/backtest/BacktestPositionOverlay.test.tsx`, `frontend/src/components/backtest/BacktestOrdersAndPositions.test.tsx`, and `frontend/src/components/backtest/BacktestCostSettings.test.tsx`.

### Implementation for User Story 9

- [x] T044 [P] [US9] Add immutable `starting_balance_usd` and `risk_percent` to run creation and Backtest account data with defaults of USD 10,000 and 1%; reject non-finite/non-positive values and Risk% greater than 100, then expose the values to replay forms and account views in `backend/app/backtests/schemas.py`, `backend/app/backtests/service.py`, `backend/app/backtests/repository.py`, `backend/app/models/trade_account.py`, and `backend/app/backtests/routes.py`.
- [x] T045 [P] [US9] Define simulation request and response schemas in `backend/app/backtests/simulation_schemas.py` for operation kinds `submit_order`, `cancel_order`, `close_position`, `modify_protection`, `update_costs`, `advance`, `rewind`, and `reset`, with operation states `pending`, `cleanup_pending`, `committed`, and `rejected`; support only market/limit entries with order states `pending`, `filled`, and `cancelled`, require both entry protection prices, enforce finite instrument-precision prices and lots in 0.001 increments with a 0.001 minimum, and allow prices to be negative where the Blind normalization rules require it.
- [x] T046 [US9] Persist run-scoped operations, orders, fills, open positions, and versioned cost profiles in `backend/app/backtests/simulation_repository.py` and add required indexes in `backend/app/db.py`; enforce unique `(user_id, run_id, client_operation_id)` and `(run_id, sequence)` operation keys, unique run/generation/position publication, committed-sequence visibility, and dedicated collections instead of unbounded arrays on BacktestRun.
- [x] T047 [US9] Implement the run-level simulation operation gate and recovery flow in `backend/app/backtests/simulation_service.py`, `backend/app/backtests/repository.py`, and `backend/app/backtests/worker.py`; use compare-and-swap revisions and monotonic committed sequences, return the stored result for identical operation retries, return 409 when a key is reused with a different request, resume pending effects idempotently after restart, and reject mutations outside ready-run/owner scope or while deletion/reset fencing applies.
- [x] T048 [P] [US9] Add direct/inverse/configured quote-to-USD one-minute conversion references to the shared user cache and run manifest, then resolve the latest completed rate no later than each fill event in `backend/app/backtests/dukascopy_provider.py`, `backend/app/backtests/preparation_jobs.py`, `backend/app/backtests/snapshot_store.py`, `backend/app/backtests/worker.py`, and `backend/app/backtests/fx_conversion.py`; use rate 1 for USD quote currency and fail when no historical or valid source-specific fallback rate exists.
- [x] T049 [P] [US9] Implement versioned per-run cost-profile validation and accounting in `backend/app/backtests/simulation_schemas.py`, `backend/app/backtests/simulation_repository.py`, and `backend/app/backtests/simulation_service.py`; require nonnegative `total_spread_pips`, `slippage_pips`, and `commission_usd_per_lot_per_side`, apply side-specific spread, adverse slippage and per-side commission once, apply profile changes only to future fills, keep configured limit-fill costs separate from the recorded limit price, report gross P&L after spread/slippage and net P&L after commission, and identify unset/zero profiles as excluded costs.
- [x] T050 [US9] Implement order acceptance, sizing, and causal entry fills in `backend/app/backtests/simulation_engine.py` and `backend/app/backtests/simulation_service.py`; every entry requires both finite, instrument-precision stop-loss and take-profit prices on the correct sides; auto-size from current balance × Risk% / 100 and selected stop distance, round down to 0.001 lots, and reject if minimum size exceeds budget. Market entries accepted after candle N fill at the next available candle open without using N or the fill candle's range. Limit entries fill only when an eligible future candle's high-low range reaches the submitted price; a gap alone does not fill, and each filled limit entry records exactly its submitted price.
- [x] T051 [US9] Implement bracket activation, scale-in, and position allocation in `backend/app/backtests/simulation_engine.py`; activate stop-loss and take-profit only after the entry-fill candle is fully processed, preserve their OCO link, fill a touched take-profit at its exact limit price only on eligible range touch, apply adverse opening prices to gapped protective stops, choose the stop when both OCO levels are touched in one candle, attach same-direction fills to the oldest open position while retaining its bracket, and reduce opposite-side fills FIFO before opening any separately protected excess position.
- [x] T052 [US9] Implement `POST /api/backtest/runs/{run_id}/simulation/positions/{position_id}/close` in `backend/app/backtests/simulation_service.py` and `backend/app/backtests/routes.py`; close the full remaining position at the currently revealed candle close without advancing replay, apply close-event costs/FX, cancel both OCO children in the same committed operation, and make retries idempotent.
- [x] T053 [US9] Implement `PUT /api/backtest/runs/{run_id}/simulation/positions/{position_id}/protection` in `backend/app/backtests/simulation_service.py` and `backend/app/backtests/routes.py`; accept stop, target, or both for an open position, validate finite instrument-precision prices against the current revealed close, preserve the OCO link and unmodified child, activate changes no earlier than the next unrevealed candle, and keep original initial-risk and R-analysis fields immutable.
- [x] T054 [US9] On an actual stop-price change, idempotently reuse the user's `stop-moved` tag or create it under the system `General` category, save its id on the open position, and copy it to the closed Journal Trade; do not add the tag for target-only changes. Use `backend/app/backtests/simulation_service.py`, `backend/app/repositories/tag_repo.py`, `backend/app/repositories/tag_category_repo.py`, `backend/app/tags/categories.py`, `backend/app/models/tag_category.py`, and `backend/app/models/trade.py`.
- [x] T055 [US9] Publish exactly one conventional closed `Trade` only after a position is fully closed, using a unique run/generation/position identity, and extend Backtest `Execution` allocations with event-level currency conversion/cost data in `backend/app/backtests/simulation_service.py`, `backend/app/models/trade.py`, `backend/app/repositories/trade_repo.py`, and `backend/app/trades/service.py`; include the run account, original initial risk, aggregate native/USD P&L, partial exits and tags, expose only committed current-generation trades to Journal/analytics, and derive current balance from initial balance plus committed realized cash effects with each cost counted once and unrealized P&L excluded.
- [x] T056 [US9] Wire authenticated, owner-scoped simulation state/order/cancel/close/protection/cost/advance/reset routes to their schemas and services in `backend/app/backtests/routes.py`, following `specs/001-backtest-workspace/contracts/backtest-api.md`; enforce expected revisions, unique operation ids, ready/complete conflicts, exact range-touch limit fill semantics, and protection responses with immutable initial risk and tag state.
- [x] T057 [P] [US9] Add TypeScript simulation entities, operation request/response types, and API functions for run sizing and simulation state, order submit/cancel, close, protection modification, cost changes, advance, and reset in `frontend/src/types/backtest.types.ts`, `frontend/src/api/backtests.api.ts`, and `frontend/src/hooks/useBacktestSimulation.ts`.
- [x] T058 [US9] Add initial-balance and Risk% inputs to `frontend/src/components/backtest/BacktestRunForm.tsx` with defaults USD 10,000 and 1%, finite positive validation, Risk% maximum 100, inclusion in the run-creation request, and persisted values in the run detail/account summary in `frontend/src/pages/BacktestReplayPage.tsx` and `frontend/src/components/backtest/BacktestRunList.tsx`.
- [x] T059 [P] [US9] Implement the collapsible right-side Market/Limit and long/short entry panel plus transient chart bracket preview in `frontend/src/components/backtest/BacktestEntryPanel.tsx`, `frontend/src/components/backtest/BacktestBracketPreview.tsx`, and `frontend/src/components/backtest/CandleKitReplayChart.tsx`; initialize entry at the current revealed close, derive default stop pips from current USD risk divided by one standard lot's USD pip value, set the initial target to 1R, move limit brackets as a group, allow independent stop/target dragging, keep market entry fixed to the current close, reverse short geometry, and show cost-aware projected risk and quantity. Enable auto-size by default using the current risk budget and selected stop distance, round down to 0.001 lots, block sizing below the 0.001 minimum when it would exceed budget, and require manual lots when auto-size is disabled.
- [x] T060 [P] [US9] Implement per-position chart indicators and working-order/open-position views in `frontend/src/components/backtest/BacktestPositionOverlay.tsx` and `frontend/src/components/backtest/BacktestOrdersAndPositions.tsx`; render each open position by stable position id with a fixed entry line/price, remaining quantity, display-only unrealized USD P&L marked at the latest revealed close before hypothetical exit costs, and independent movable stop/target lines/prices. Scope all controls to that position and give icon buttons accessible action/position names; make BE request its entry price through the existing protection operation (disabled if crossed by the current revealed close), and make X invoke that position's full close at the current revealed close. Allow cancel only for pending entries; show immutable original initial risk/R and `stop-moved` state without presenting open positions as closed Journal trades.
- [x] T061 [P] [US9] Implement the per-run spread/slippage/commission editor and cost disclosure in `frontend/src/components/backtest/BacktestCostSettings.tsx`; display nonnegative spread, slippage, and USD commission-per-lot-per-side settings, show when unset/zero costs are excluded, and explain that changes apply only to future fills.
- [x] T062 [US9] Integrate the simulation hook, entry panel, chart preview, per-position indicators, orders/positions, and cost settings into `frontend/src/pages/BacktestReplayPage.tsx` and `frontend/src/components/backtest/CandleKitReplayChart.tsx`; render each open position independently on every run chart pane from committed simulation state, keep both preview and filled-position indicators separate from persisted user drawings, enforce submission/operation pending states, render blind prices only in the run's normalized scale and hide complete dates/raw prices, and preserve accessible price labels and theme styling.
- [x] T063 [US9] Extend run reset and deletion cleanup for the new generation-scoped simulation operations, orders, fills, positions, linked executions, closed Backtest trades, and tag associations without affecting another run or Real activity; reset MUST preserve the latest run-level cost profile and immutable balance/risk settings, while deletion removes all run cost data. Clear run-owned tag references without deleting a reused user-owned tag or the General category in `backend/app/backtests/simulation_repository.py`, `backend/app/backtests/repository.py`, `backend/app/backtests/service.py`, `backend/app/backtests/worker.py`, `backend/app/trades/service.py`, and `backend/app/repositories/trade_repo.py`.

**Checkpoint**: A ready run supports protected market/limit practice with exact range-touch limit fills, separate configured costs, durable idempotent operations, independent per-position chart indicators and controls for post-fill protection/BE/exit, immutable original risk, correctly tagged closed Journal trades, accurate run-account results, and reset/deletion isolation.

---

## Phase 17: Shared Sources, Recovery, and Portable Backtests

**Purpose**: Record implemented source-reuse, manual-import, restore, linked-trade chart, and replay transport changes that supersede run-owned candle snapshot assumptions above.

### Shared candle cache and downloader integration

- [X] T064 [P] [US10] Store normalized Dukascopy COMB days and known-empty dates in a per-user/version/instrument/interval/side/date shared cache, coordinate concurrent misses with renewable leases, keep cache objects outside run deletion, and consume the downloader's aligned in-memory COMB API while preserving JanusEdge midpoint and volume transforms in `backend/app/backtests/candle_cache.py`, `backend/app/backtests/snapshot_store.py`, `backend/app/backtests/dukascopy_provider.py`, and `backend/tests/test_backtests/test_backtest_candle_cache.py`.

### Missing-data recovery

- [X] T065 [US10] Persist metadata-only run manifests that reference shared Dukascopy cache days or pinned manual revisions, expose availability/progress, queue only missing references after explicit user action, and preserve committed simulation state while remapping cursor/index state after recovery in `backend/app/backtests/service.py`, `backend/app/backtests/repository.py`, `backend/app/backtests/routes.py`, `backend/app/backtests/worker.py`, and `backend/tests/test_backtests/test_backtest_replay_routes.py`.

### HistData manual import

- [X] T066 [P] [US11] Parse fixed-UTC-5 headerless HistData M1 bid OHLCV, preview date ranges without mutation, require confirmation before conflicting timestamp replacement, version merged datasets, pin run revisions, constrain available/random dates, apply manual quote-to-USD fallback only where needed, and support equivalent-data re-upload recovery in `backend/app/backtests/manual_import.py`, `backend/app/backtests/routes.py`, `frontend/src/components/backtest/BacktestRunForm.tsx`, `frontend/src/api/backtests.api.ts`, and `backend/tests/test_backtests/test_backtest_manual_import.py`.

### Settings archive integration

- [X] T067 [P] [US12] Extend Settings backup format 1.1 to export ready/complete committed Backtest run/simulation/account/trade/execution/workspace/drawing state without candle bytes or worker state, restore with stable source identity and destination cache binding, retain format 1.0 support, and report created/reused counts in `backend/app/auth/backup_service.py`, `backend/app/auth/routes.py`, `backend/tests/test_auth/test_backup_routes.py`, and the Settings backup UI.

### Linked trade charts

- [X] T068 [US10] Serve linked Backtest trade-chart candles from the run's pinned source, clip the exclusive end to furthest reached candle plus one minute with legacy current-cursor fallback, aggregate 1m/5m/15m/1h UTC buckets after clipping, and preserve non-Backtest data sources in `backend/app/backtests/service.py`, `backend/app/backtests/routes.py`, `frontend/src/pages/TradeDetailPage.tsx`, and `backend/tests/test_backtests/test_backtest_replay_routes.py`.

### Scale-in execution aggregation

- [X] T069 [US9] Attach same-direction fills at execution time to the oldest open position on the instrument, preserve every fill as an execution, update weighted entry/size/risk/costs and protection quantities without replacing the existing bracket, and create a separate bracketed position only when no matching position remains open in `backend/app/backtests/simulation_effects.py` and `backend/tests/test_backtests/test_backtest_simulation.py`.

### Replay transport and display follow-ups

- [X] T070 [US3] Bind ArrowLeft/ArrowRight to the same speed-sized back/forward step as the visible transport and Space to play/pause while ignoring repeats, modifiers, and editable controls; keep manual step-forward available whenever replay navigation is permitted in `frontend/src/components/backtest/BacktestReplayControls.tsx`.
- [X] T071 [US9] Align Backtest trade-detail precision and marker direction with Settings metadata, format replay date/time as weekday/month/day/year plus time, and present compact lot-weighted position labels with legible BE/close controls and vertical stop/target drag cursors in the trade-detail and replay chart components.

### Artifact convergence

- [X] T072 Update `spec.md`, `plan.md`, `data-model.md`, `contracts/backtest-api.md`, `research.md`, `quickstart.md`, and this task ledger to describe the current cache-manifest model, source-specific recovery, manual import, portable backups, scale-in behavior, high-water-capped trade charts, keyboard controls, separator-insensitive search, mapped manual trades, and remaining browser-validation scope.
- [X] T073 Document the authenticated manual-trade conversion lookup and creation contracts, including Settings alias resolution, sizing/precision snapshots, route metadata, completed-bar eligibility, and the seven-day manual-lookup window.
- [X] T074 Reconcile source-specific date/time and warm-up behavior across spec artifacts: Dukascopy uses the configured timezone, HistData manual import uses fixed UTC−5 without DST, and both honor `warmup_days` with a default of zero.
- [X] T075 Reconcile the replay speed choices and step size with the implemented 1x/2x/5x/15x/30x transport and document the no-emoji segmented controls.

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
- **US7 random period selection (Phase 14)**: T032 and T033 establish backend and frontend contracts before T034-T035. T034 persists worker selection and resolves the run before account creation; T035 consumes the pending and resolved states. T036 captures the shipped behavior in the design and validation artifacts.
- **US8 Blind mode (Phase 15)**: T038 and T039 establish backend and frontend contracts independently. T040 persists and validates run-level privacy/normalization metadata. T041 consumes that metadata to force random selection and apply the display transformation; it depends on the response and reference contract from T040. T037 records the agreed requirements and is complete before implementation begins.
- **US9 simulated trading (Phase 16)**: Depends on the delivered ready-run/replay and Backtest-account behavior from US2-US4, deletion cleanup from US6, and Blind display contract from US8. T042-T043 can be authored in parallel before implementation. T044-T045 establish run and simulation schemas; T046-T047 add durable collections and the operation gate. T048 and T049 prepare currency conversion and cost handling before T050-T051 implement causal fills, protection, OCO, and FIFO. T052-T056 add position actions, General tag propagation, closed-Trade publication, and API routes. T057 then supplies the frontend contract; T058-T062 build run settings, preview, position actions, costs, and page integration, with T059-T061 independent on separate component files. T063 extends reset/deletion cleanup after simulation records exist. T014 remains the end-to-end quickstart validation task.

### User Story Dependencies

- **US1 (P1)**: Previously delivered; no new tasks.
- **US2 (P1)**: Previously delivered; supplies ready runs for US3.
- **US3 (P1)**: Starts after T001-T002 and the existing ready-run/replay foundation.
- **US3 follow-mode delta (P1)**: Extends the delivered replay chart panes; T015 precedes T016, and T017 uses the state/action interfaces implemented by T016.
- **US4 (P2)**: Previously delivered; no new tasks.
- **US5 (P2)**: Starts after US3 panel moves are implemented.
- **US6 (P1)**: Extends the existing US2 run and US4 account relationship; independent of chart layout and drawing behavior. It does not add trade creation or order entry.
- **US7 (P1)**: Extends the delivered run-preparation lifecycle with persisted bounded candidate selection.
- **US8 (P1)**: Extends the existing random-selection run flow and replay chart; it does not add trade creation, order entry, or Journal persistence.
- **US9 (P1)**: Depends on the delivered replay, account, deletion, and Blind-display foundations listed above; no new feature story blocks it.
- **US2 warm-up delta (Phase 12)**: Extends the delivered run preparation; T026 precedes T027.
- **US3 warm-up delta (Phase 13)**: Extends the delivered replay controller; T028-T029 precede T030-T031, with the frontend implementation consuming the persisted cursor boundary from the backend contract.

### Parallel Opportunities

- T003 and T004 can be authored in parallel because they target separate backend and frontend test files.
- After those tests are in place, T005 and T007 can proceed in parallel on separate backend and frontend files against the already documented contract.
- Within US5, complete T011 before T012; backend tests and frontend tests from US3 can run independently.
- T026, T028, and T029 target separate backend or frontend test files and can be authored in parallel; implementation must wait for its corresponding tests.
- T032 and T033 target separate backend and frontend test files and can be authored independently; implementation must wait for both contract test sets.
- T038 and T039 target separate backend and frontend test files and can be authored independently; each implementation task waits for its corresponding blind-mode tests.
- T042 and T043 target separate backend/frontend tests and can be authored in parallel. T044 and T045 touch independent run and simulation schema files. T048 conversion-data work can proceed in parallel with T049 cost-profile work after the persistence contract is stable. After T057 defines the frontend API types, T059, T060, and T061 can be implemented in parallel in separate component files; T062 integrates them after completion.

## Parallel Example: User Story 3

```text
Task: T003 backend chart-workspace contract and migration tests in backend/tests/test_backtests/test_backtest_chart_workspaces.py
Task: T004 frontend workspace bootstrap and legacy conversion tests in frontend/src/utils/backtestWorkspace.test.ts
```

## Parallel Example: User Story 9

```text
Task: T042 backend simulation contract tests in backend/tests/test_backtests/test_backtest_simulation.py
Task: T043 frontend simulation interaction tests in frontend/src/components/backtest/BacktestEntryPanel.test.tsx and frontend/src/components/backtest/BacktestOrdersAndPositions.test.tsx

Task: T059 bracket preview and entry panel in frontend/src/components/backtest/BacktestEntryPanel.tsx and frontend/src/components/backtest/BacktestBracketPreview.tsx
Task: T060 per-position overlays and orders/positions controls in frontend/src/components/backtest/BacktestPositionOverlay.tsx and frontend/src/components/backtest/BacktestOrdersAndPositions.tsx
Task: T061 execution cost controls in frontend/src/components/backtest/BacktestCostSettings.tsx
```

## Implementation Strategy

### MVP for This Plan Delta

1. Complete Setup and Foundational.
2. Complete User Story 3 so a run has one default chart and its dockable layout persists.
3. Complete User Story 5 lifecycle handling before release so moving a panel cannot lose drawings or leak subscriptions.
4. Complete the US3 follow-mode tasks so each pane can track or inspect replay history independently.
5. Run headless automated checks after implementation. Keep T014 open until the remaining quickstart UI scenarios are completed.
6. Keep User Story 6 deletion cleanup in place before enabling User Story 9 trade recording, so simulation records and the dedicated account cannot outlive their run.
7. Implement the warm-up history extension after tests define its calendar-date boundary, partial-availability behavior, and separation from replay-eligible candles.
8. Implement random selection as a persisted worker phase before normal preparation; keep the manual request path unchanged and create the account only after a candle-bearing start date is found.
9. Implement Blind mode on top of the random path after backend and frontend tests define request compatibility, date masking, reference-price failure behavior, and normalized chart presentation. Keep API redaction and trade entry out of scope.
10. Implement User Story 9 on the delivered run/replay/account foundations: establish durable simulation operations and backend execution first, then build the entry, position, cost, and Blind-aware UI; use this story as the MVP for the remaining unimplemented scope.

## Notes

- This list contains implementation and validation work; T036 and T037 are the explicit documentation updates for random-period selection and Blind mode respectively.
- All generated task IDs are sequential. `[P]` is used only where the tasks can work on separate files without waiting for unfinished implementation.
- The previous flat `/chart-tabs` persistence task is superseded by T003-T010; do not implement a second flat layout source of truth.
- T014 covers the full quickstart UI/browser validation matrix and remains unchecked because that complete matrix was not run as part of the current source and documentation update.
