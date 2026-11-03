# MNQ research handoff · November 3, 2026

Repository: `alex0204360/NQ-profitability-research`, branch `codex/mnq-cloud-transfer-2026-11`. In a fresh cloud checkout, run `python cloud-transfer/restore.py` to restore the latest verified snapshot under `/workspace`. The snapshot includes `/workspace/mnq-oracle-code`, `/workspace/mnq-private-data`, `/workspace/mnq-private-results`, and `/workspace/outputs`. The raw sealed 2025 dataset is excluded. The older transfer and individual campaign overlays remain in Git for historical lineage.

## Research objective and constraints

The user's goal is autonomous, evidence-driven discovery of a repeatable MNQ trading edge, measured by incremental prediction and positive net expectancy after realistic costs, fill delay, and risk. Retain the unchanged $8 gate as the comparison baseline. Keep 2025 sealed until explicitly authorized after candidate and acceptance criteria are frozen. Do not connect a broker or submit live orders. Model a $25,000 account and $1,500 maximum permitted firm drawdown, but the firm's exact trailing rule is unknown. The user clarified that there is no separate fixed maximum-drawdown target per contract; do not confuse that with the firm account limit.

## Current evidence

The unchanged $8 gate earned **+$196.50 immediate stressed net** on the 14-session October 13–29 upload, with **$816.50 research bar-close drawdown**, below $1,500. A one-bar signal delay produced **−$1,250 net** and **$1,657 drawdown**. On the newer two-session October 30–November 2 upload it earned +$429 immediate / +$259.50 delayed, but two sessions and missing-bar exit sensitivity are insufficient for qualification. It remains a baseline, not a live strategy.

Campaign09 was the latest bounded test. A causal 32-minute price/volume path was compressed by eight-component PCA trained only on prior data and added to the 18-feature Ridge action-value student. The two students used identical 15,508 training rows and robust ten-bar long/short labels. Incremental rank gains on the two original October development windows were only **0.009 and 0.006**, below the preregistered 0.020 in each. The path student lost **$109.50 immediate / $128.50 delayed** under stressed costs on the 14-session upload and failed extreme-cost, bootstrap, and sample-size screens. The newer two-session upload yielded one positive trade shared with the snapshot student. No candidate was promoted. See `mnq-oracle-code/docs/CLOUD_CAMPAIGN09_RESULT.md` and `outputs/mnq_path_representation_dashboard.html`.

Earlier campaigns rejected dual-delay action-value students, a multi-horizon student, an ATR bracket, 100 robust-value trials, 100 oracle variants with a failed internal holdout student, probability-gated chart retests, and drift–diffusion/persistence filters. A chart-confluence result had just two trades per window. See `mnq-oracle-code/docs/CLOUD_RESEARCH_BACKLOG.md` and the full private run ledger. Do not tune against these repeatedly opened dates until a profit appears.

## Data integrity and immediate next step

The original 2026 candles and user-supplied October–November upload are Yahoo-labeled one-minute OHLCV. The exact futures contract/roll and minute timestamp convention remain unverified. The user could not supply those details. The first fresh transfer had two conflicting overlap candles, so its original confirmation failed; later upload-only windows are opened development diagnostics, not untouched confirmation.

The highest-value next step is a **contract-identified, append-only source of new MNQ minute observations** with exchange timestamp convention, roll rule, correction log, and executable cost schedule. Freeze a small incremental prediction test before looking at those outcomes. If that feed is unavailable, report NOT READY; do not manufacture evidence by tuning the existing opened samples. Paper-trading API parity and actual firm drawdown mechanics remain important follow-ups. No paid resources, live feed, or broker are configured.

The latest private run is `mnq-private-results/cloud_campaign09_retry1`. `cloud_campaign09` preserves a pre-fit protocol-key failure; the corrected run changed no model threshold or hyperparameter. Its protocol, source hashes, model checkpoint, decision and trade journals, and manifest are retained. The dashboard and JSON aggregate live in `outputs/`. `python -m tools.cloud_campaign09_report` regenerates them. Raw 2025 was not opened, and no broker orders were submitted.
