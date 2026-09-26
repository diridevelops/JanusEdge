---
description: "Implementation backlog for the dockable Backtest chart workspace"
---

# Tasks: Backtest Candle Replay

**Input**: Design documents in `specs/001-backtest-workspace/` (`spec.md`, `plan.md`, `data-model.md`, `contracts/backtest-api.md`, `research.md`, and `quickstart.md`).

**Prerequisites**: `plan.md` and `spec.md` are available. The project constitution remains an unratified Spec Kit placeholder and defines no project gates.

**Scope**: This regenerated backlog carries forward implementation already recorded as complete in the previous task list. It does not repeat the Real/Backtest separation, run preparation, core replay transport, account integration, or initial drawing integration tasks. The old flat chart-tabs task is superseded by the dockable workspace work in User Story 3. These carry-forward notes reflect the prior task ledger, not a new code audit.

**Tests**: Include focused backend and frontend tests for the new versioned workspace contract, migration, and panel lifecycle. UI/browser scenarios remain deferred under the user's current instruction; no tests were run while generating this backlog.

**Organization**: One phase per feature user story, in priority order. User Stories 1, 2, and 4 have no new tasks in this plan delta because their work is recorded as complete in the prior task list.

**Format**: `- [ ] T### [P?] [US#?] Description with file path`

## Phase 1: Setup

**Purpose**: Add the missing dock-layout runtime dependency using the version boundary established in the plan.

- [ ] T001 Pin an exact `flexlayout-react` version compatible with CandleKit 0.1.0's optional `^0.9.1` peer and update the npm lockfile in `frontend/package.json` and `frontend/package-lock.json`.

---

## Phase 2: Foundational

**Purpose**: Add the persistence key required before the workspace API can safely read and write per-run layouts.

- [ ] T002 Add a unique compound MongoDB index for `(user_id, run_id)` workspace ownership in `backend/app/db.py`.

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

**Goal**: Replace the flat chart grid with a persistent dockable workspace while retaining the run's single replay cursor and cursor-bounded chart data.

**Independent Test**: A new run opens with one 1m chart. Add and reorder tabs, move one between groups, split by dropping it at a pane edge, resize panes, and close tabs while retaining one chart. Reload and confirm layout, active tabs, stable ids, intervals, and the shared replay position are restored. Migrate legacy flat tabs without losing their ids or intervals.

### Tests for User Story 3

- [ ] T003 [P] [US3] Add backend tests for workspace ownership, schema/type/interval validation, minimum-one-chart enforcement, legacy-tab reads, and revision conflict behavior in `backend/tests/test_backtests/test_backtest_chart_workspaces.py`.
- [ ] T004 [P] [US3] Add frontend tests for one-chart/1m initialization, legacy flat-tab conversion preserving ids and intervals, layout/panel identity round trips, and conflict handling that retains a local draft in `frontend/src/utils/backtestWorkspace.test.ts`.

### Implementation for User Story 3

- [ ] T005 [P] [US3] Define the versioned chart-workspace schema and owner/run-scoped repository operations, including atomic expected-revision compare-and-swap, in `backend/app/backtests/schemas.py` and `backend/app/backtests/repository.py`.
- [ ] T006 [US3] Implement authenticated GET/PUT chart-workspace service and routes in `backend/app/backtests/service.py` and `backend/app/backtests/routes.py`; GET returns a saved layout or ordered legacy chart tabs, and PUT validates layout/panel correspondence and returns 409 for stale revisions.
- [ ] T007 [P] [US3] Add workspace request/response types and a CandleKit `LayoutPersistence` adapter backed by the authenticated chart-workspace API in `frontend/src/types/backtest.types.ts` and `frontend/src/api/backtests.api.ts`.
- [ ] T008 [US3] Create `BacktestChartWorkspace` with `WorkspaceProvider`, `FlexLayoutAdapter`, and a registered JanusEdge chart panel; initialize one stable-id 1m chart or convert legacy records into visible sibling panes, then persist initialization before enabling edits in `frontend/src/components/backtest/BacktestChartWorkspace.tsx` and `frontend/src/utils/backtestWorkspace.ts`.
- [ ] T009 [US3] Configure workspace operations so Add Chart activates a tab in the focused group, tab drag reorders/moves, edge drops split panes, splitters resize, and closing the final chart is rejected in `frontend/src/components/backtest/BacktestChartWorkspace.tsx`.
- [ ] T010 [US3] Replace the flat chart grid with the persisted workspace while keeping all chart panels connected to the existing single run replay controller and UTC synchronization in `frontend/src/pages/BacktestReplayPage.tsx` and `frontend/src/hooks/useBacktestReplay.ts`.

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

- [ ] T011 [US5] Add a panel-move lifecycle regression test for pending drawing writes and replay/sync listener cleanup in `frontend/src/components/backtest/BacktestChartWorkspace.test.tsx`.

### Implementation for User Story 5

- [ ] T012 [US5] Flush pending drawing persistence and unregister/re-register drawing, replay, and sync subscriptions safely across chart-panel unmount/remount in `frontend/src/components/backtest/BacktestChartTab.tsx`, `frontend/src/components/backtest/CandleKitReplayChart.tsx`, and `frontend/src/hooks/useBacktestChartSync.ts`.

**Checkpoint**: Moving a tab preserves its stable drawing scope and does not lose pending saves or duplicate chart subscriptions.

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: Validate the new layout against the existing application and documented acceptance scenarios.

- [ ] T013 Run backend pytest, frontend Vitest, lint, and production build after workspace integration; resolve regressions and the previously recorded standard Vite build-loader access error using `backend/pyproject.toml`, `frontend/package.json`, and `frontend/vite.config.ts`.
- [ ] T014 After UI validation is resumed, execute the chart-workspace migration, docking, persistence, concurrency, and panel-move scenarios in `specs/001-backtest-workspace/quickstart.md`.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependency; completes the exact layout peer pin.
- **Foundational (Phase 2)**: Depends on Setup and blocks workspace API persistence.
- **User Stories 1 and 2 (Phases 3 and 4)**: Previously delivered; US3 relies on the ready-run behavior from US2.
- **User Story 3 (Phase 5)**: Depends on Setup and Foundational; the replay/run API it extends is recorded as delivered in US2/US3 work from the previous backlog.
- **User Story 4 (Phase 6)**: Previously delivered; independent of the dock-layout change.
- **User Story 5 (Phase 7)**: Depends on US3's docked chart panel and move behavior.
- **Polish (Phase 8)**: T013 depends on implementation completion; T014 remains deferred until UI validation resumes.

### User Story Dependencies

- **US1 (P1)**: Previously delivered; no new tasks.
- **US2 (P1)**: Previously delivered; supplies ready runs for US3.
- **US3 (P1)**: Starts after T001-T002 and the existing ready-run/replay foundation.
- **US4 (P2)**: Previously delivered; no new tasks.
- **US5 (P2)**: Starts after US3 panel moves are implemented.

### Parallel Opportunities

- T003 and T004 can be authored in parallel because they target separate backend and frontend test files.
- After those tests are in place, T005 and T007 can proceed in parallel on separate backend and frontend files against the already documented contract.
- Within US5, complete T011 before T012; backend tests and frontend tests from US3 can run independently.

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
4. Run headless automated checks after implementation. Keep T014 open until the user resumes UI validation.

## Notes

- This list contains implementation and validation work, not tasks to edit planning documents.
- All generated task IDs are sequential. `[P]` is used only where the tasks can work on separate files without waiting for unfinished implementation.
- The previous task T034 for flat `/chart-tabs` persistence is superseded by T003-T010; do not implement a second flat layout source of truth.
- T014 is intentionally deferred by the user's current “do not test the UI for now” instruction and must remain unchecked until UI validation is authorized.
