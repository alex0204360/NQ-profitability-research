# Private MNQ oracle source dataset — October 12, 2026

This branch contains the user's Yahoo Finance MNQ=F continuous-futures 1-minute chart export and derived ChartChico 6.9 hindsight teacher labels. Do not publish this raw feed or the user's private indicator to the public NQ-trading-sept repository; evaluate market-data redistribution rights before external publication.

Files in data/mnq_oracle_2026:
- MNQ_Yahoo_1m_20260913_20261012_part01.csv through part06.csv. CSV chunks are numbered chronologically, with headers repeated on each part, 5,000 bars per file except last part (3,312), for 28,312 total source rows.
- mnq_oracle_teacher_labels.csv. 875 closed TradingView trades, with 89.6% apparent win rate calculated using future-leaking HTF data, NOT a realizable performance claim.
- MNQ_Yahoo_daily_20251013_20261012.csv. 251 historical daily rows.

Full continuous-futures CSV origin SHA256: 32cb3e076a236948810559734b6d63d6f3e79489ee020ee0c260feac78b4ae63. The split files use LF line endings and repeated CSV headers. See docs/MNQ_ORACLE_CODEX_HANDOFF.md in alex0204360/NQ-trading-sept branch research/mnq-oracle-prep-20261012 for per-part SHA256 values, data audit, step-by-step instructions, and exact Python CLI.

The public code's initial preparation run on these data generated:
28,311 complete minute-aligned rows; one 2026-10-12T15:40:43Z apparent partial row excluded; 75 time gaps; 26 zero-volume retained bars; 866/875 teacher timestamps matched; 813 labels with warmed-up causal features.

No market-data backtest or causal student P&L has been run. The NQ Kaggle 2025 holdout must remain sealed and separate from these 2026 MNQ experiments.

Use only for personal research in accordance with applicable exchange and data-provider licensing.
