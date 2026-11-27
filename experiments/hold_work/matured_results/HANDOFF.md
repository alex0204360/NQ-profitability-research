# Decision on the matured-label experiment

The causal memory reduced the initial score's mean overstatement but missed its primary benchmark. A constant zero forecast had lower mean squared error in both panels at both fill schedules. On 272 external next-open observations the interaction memory shifted the mean from +27.68 to −2.56 points. The realized mean was −0.25. Its MSE was 2,703.46 points² versus 2,686.21 for zero. The paired five-session interval for the difference was −36.56 to +72.54 points². The other three comparisons with zero also spanned zero. This leaves sampling uncertainty about the population ordering.

On all 541 original external next-open trades, the one-time memory decision improved the ledger by $28, finishing at −$3,793 at $6 and −$5,416 at $9. The discovery next-open ledger lost $188.50 relative to the parent. The frozen criteria for full re-entry and prospective testing were missed. Retire this holding-value rule. A separate question is whether these states describe the *size of downside* even when they fail to predict its signed mean.

Reproduce the files from the repository root with Python, NumPy, pandas and SciPy.

```sh
python -m unittest discover -s experiments/hold_work -q
python -m experiments.hold_work.run_matured experiments/hold_work/results rerun
```

The authoritative first-decision and original trade archives are in the results directory. The predictions file records the count and last exit of labels used before each projection. The fixed ledger includes the original trades with no eligible decision. Detailed errors, rank, concentration, costs and paired intervals appear in summary.json. All 100 dates were exposed.
