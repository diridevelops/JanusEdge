# Specification Quality Checklist: Backtest Candle Replay

**Purpose**: Validate specification completeness and quality before proceeding to planning
**Created**: 2026-09-23
**Feature**: [spec.md](../spec.md)

## Content Quality

- [x] No implementation details (languages, frameworks, APIs)
- [x] Focused on user value and business needs
- [x] Written for non-technical stakeholders
- [x] All mandatory sections completed

## Requirement Completeness

- [x] No [NEEDS CLARIFICATION] markers remain
- [x] Requirements are testable and unambiguous
- [x] Success criteria are measurable
- [x] Success criteria are technology-agnostic
- [x] All acceptance scenarios are defined
- [x] Edge cases are identified
- [x] Scope is clearly bounded
- [x] Dependencies and assumptions are identified
- [x] Run deletion confirmation, cascade scope, cancellation, and interrupted-cleanup cases are defined
- [x] Warm-up history is separated from replay eligibility, including partial/unavailable context and context-only no-data behavior
- [x] Filled-position chart indicators and independent stop/target/BE/X controls cover multi-position isolation

## Feature Readiness

- [x] All functional requirements have clear acceptance criteria
- [x] User scenarios cover the primary flows
- [x] Feature meets the measurable outcomes defined in Success Criteria
- [x] No implementation details leak into the specification

## Notes

- Each run uses one instrument and completed one-minute candles from either Dukascopy or a versioned HistData manual import; source-specific date and conversion behavior is defined in the feature requirements.
- Playback rates are explicitly defined as one, two, five, fifteen, or thirty one-minute candles per second; manual stepping uses the selected speed-sized batch.
- Each run creates one Backtest account; v1 includes simulated orders and trade recording during replay.
- Run deletion is permanent, confirmed, available during preparation or after readiness, and physically removes only that run's dedicated account, linked trades and dependents, run state, and manifest references. Shared candle cache and manual dataset revisions remain.
- A `deleting` run is only a temporary non-playable cleanup marker; interim hiding or a 202 response is not completion. Completion requires no run/account/trade/deletion-marker records; there is no per-run candle prefix to purge.
- Each run requests the user-selected `warmup_days` of available pre-start chart history (default 0), but the selected dates alone define replay start/end, readiness, and playback bounds; missing warm-up data is allowed. Dukascopy uses the configured timezone; HistData Manual import uses fixed UTC−5 without DST.
- Real and Backtest data remain separate; imported and manually created trades are Real-mode activity, while simulated orders and trades belong to their run's Backtest account.
- Future candle high-low range touches fill limit entries and take-profit limits at exactly their submitted prices; opening gaps without range touch do not fill, and configured costs remain separate.
- Open positions allow stop-loss and take-profit edits that take effect only on future unrevealed candles; original initial risk/R basis remains fixed, and an actual stop change adds the idempotent `stop-moved` Journal tag under General if needed.
- Every open position has its own run-wide chart indicators and independent controls; the filled entry is fixed, stop/target edits use the existing rules, BE targets that position's entry, and X closes only that position. Quantity and mark-to-market P&L are shown, with P&L display-only and before hypothetical exit costs.
- Same-direction fills at execution time scale into the oldest open position on the instrument and preserve every fill as an execution; opposite-side reductions remain FIFO.
- Backtest and Settings instrument searches ignore case and dot, dash, slash, and space separators while preserving character order; Settings search covers pair/base/quote and resets pagination on query changes.
- Manual trades resolve Settings aliases to a canonical instrument, preserve the raw symbol, apply configured sizing/precision, and use exit-time quote-currency conversion with an editable fallback only when historical data is unavailable.
- Manual conversion lookup uses only completed candles at or before the event and searches the event UTC date plus the preceding seven dates; Backtest simulation conversion remains governed by the run's pinned source data.
- Settings backup format 1.1 includes ready/complete Backtest state and excludes candle bytes. Missing source data is recovered only after the user's explicit choice.
- Linked Backtest trade-detail charts stop at the run's furthest replay candle, even after rewind; manual replay, chart precision, buy/sell colors, date formatting, and replay keyboard shortcuts follow the feature requirements.
