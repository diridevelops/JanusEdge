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

- Version one is limited to downloading and replaying completed one-minute candles for one instrument and date range.
- Playback rates are explicitly defined as one, five, or twenty candles per second.
- Each run creates one Backtest account; v1 includes simulated orders and trade recording during replay.
- Run deletion is permanent, confirmed, available during preparation or after readiness, and physically removes only that run's dedicated account, linked trades and dependents, run data, and every object under its MinIO prefix.
- A `deleting` run is only a temporary non-playable cleanup marker; interim hiding or a 202 response is not completion. Completion requires an empty run MinIO prefix and no run/account/trade/deletion-marker records.
- Each run requests one calendar month of available pre-start chart history, but the selected dates alone define replay start/end, readiness, and playback bounds; missing warm-up data is allowed.
- Real and Backtest data remain separate; imported and manually created trades are Real-mode activity, while simulated orders and trades belong to their run's Backtest account.
- Future candle high-low range touches fill limit entries and take-profit limits at exactly their submitted prices; opening gaps without range touch do not fill, and configured costs remain separate.
- Open positions allow stop-loss and take-profit edits that take effect only on future unrevealed candles; original initial risk/R basis remains fixed, and an actual stop change adds the idempotent `stop-moved` Journal tag under General if needed.
- Every open position has its own run-wide chart indicators and independent controls; the filled entry is fixed, stop/target edits use the existing rules, BE targets that position's entry, and X closes only that position. Quantity and mark-to-market P&L are shown, with P&L display-only and before hypothetical exit costs.
