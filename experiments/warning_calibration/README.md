# Earlier observations corrected overconfidence; the improvement over a running rate was unresolved

Every probability and slope was issued using only earlier completed study dates. The joint slope started at zero and ended at 0.116 on discovery and 0.213 on the external panel. This substantially reduced the exaggerated probability differences from transplanting a prior session's input paths.

| Exposed panel | Running rate Brier | Raw joint Brier | Calibrated joint Brier | Calibrated minus rate, paired 95% interval |
|---|---:|---:|---:|---:|
| Discovery, 10,520 resolved | .0264669 | .0278858 | .0264540 | [−.0000310, +.0000050] |
| External, 15,967 resolved | .0286363 | .0288570 | .0286215 | [−.0000323, +.0000026] |

Calibration beat the raw forecast on both panels. Its incremental advantage over the equally informed running event rate was too small to distinguish on either panel. The matched effort-rotation intervals also crossed zero in both. The two-close warning therefore failed the promotion rule. The exact earliest-possible horizon remains useful for understanding the parent, and the separately registered one-close forecast remains the candidate for independent evaluation.

[Protocol](protocol.md) · [All scores and uncertainty](results/summary.json) · [Individual probabilities, slopes and counts](results/calibrated.csv.gz)

```sh
python -m experiments.warning_calibration.run experiments/two_close_warning/results/forecasts.csv.gz /tmp/mnq-calibration
cmp /tmp/mnq-calibration/summary.json experiments/warning_calibration/results/summary.json
cmp /tmp/mnq-calibration/calibrated.csv.gz experiments/warning_calibration/results/calibrated.csv.gz
```
