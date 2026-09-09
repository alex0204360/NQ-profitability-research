# Changelog

## 2026-09-09 — Phase 0

- Created the separate V2 research protocol from V1's negative screening result.
- Preregistered net-payoff actions, conservative fills, costs, two rounds, gates,
  one terminal holdout, and data-agnostic matcher boundaries before writing code.
- Recorded independent protocol review by `v2_protocol_review`.

## 2026-09-09 — Failing specifications

- Added package scaffold and pre-evaluation timestamp/booking clarifications.
- Committed failing causal-feature, conservative-execution, learned-policy, and replay tests before implementations.

- Committed failing paired profit-inference and standard-OHLCV matcher contracts.

## 2026-09-09 — Profit research engine

- Implemented 1,080 ATR-scaled TP/SL/window actions, conservative payoff labels and nonoverlapping replay.
- Added four learned policies, paired block inference, hash-bound standard-OHLCV matching and sealed terminal orchestration.
- Resolved independent review findings on incomplete benchmarks, serving identity, input hashes and candidate failure isolation before any market outcome evaluation.

## 2026-09-09 — Audited inputs and trade labels

- Reused 706,008 training bars and frozen calendar with recorded file identities.
- Generated 1,080 cost-adjusted action labels on 125,518 common eligible fit observations.
- Preserved inherited data-quality exclusions and metadata uncertainty. Holdout prices/outcomes were not decoded; only an opaque file digest was recorded.
- Added opt-in full-round integration verification of costs, chronology, occupancy and the 45-minute cap.

## 2026-09-09 — Tournament Round 1

- Tested regime8 and prototype8 across all four chronological validation folds.
- Both policies abstained at all 113,688 validation opportunities: no fitted action had a positive cost-adjusted ranking score. Both were rejected for insufficient executed trades and no established net expectancy.
- No bootstrap or heldout evaluation ran; the no-trade outcome is a recorded research result.
- Full-round integration verification passed, including the untouched-holdout guard.
