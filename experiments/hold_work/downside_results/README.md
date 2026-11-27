# Forecasting downside to the original reservoir exit

The frozen diffusion-time scale increased 80th-percentile pinball loss over entry range alone in all four comparisons. A larger loss means the quantile was less accurate. At next-open fills the 95% paired intervals excluded zero in both sources. All dates were previously exposed.

| Source and fills | Scored after warmup | Range only | Threshold distance | Difference, 95% interval | Distance forecast exceedance |
|---|---:|---:|---:|---:|---:|
| Discovery 40, next open | 198 | 11.73 | 14.10 | +2.36 [0.93, 4.73] | 18.2% |
| Discovery 40, extra minute | 161 | 12.80 | 15.01 | +2.21 [−0.45, 5.81] | 24.2% |
| External 60, next open | 252 | 9.20 | 10.33 | +1.13 [0.11, 2.22] | 15.1% |
| External 60, extra minute | 232 | 8.94 | 9.57 | +0.63 [−0.53, 1.79] | 16.4% |

Every cell used the same completed-trade history and the same first decision. Unit-scale and known-clock-only comparisons are in the summary. The range-only control had lower mean loss than both of those controls in every comparison. It exceeded its nominal downside forecast on 12.9% to 25.5% of scored trades across the four groups, against a target of 20%. Its reliability on new observations remains unknown.

### Why the distance rule failed

Distance through a diffusing state carries some ordering information about time. Across the four comparisons, its Spearman correlation with remaining duration ranged from 0.17 to 0.22. Its variation was too large. In the lowest and highest quartiles of the external next-open duration estimate (63 trades each), median forecast durations were 1 and 49 minutes. Actual medians were 13 and 23 minutes. The corresponding mean downside forecasts were 14.3 and 93.4 points. Entry-range forecasts averaged 43.2 and 44.2 points in those groups. These quartiles are retrospective diagnostics. The full forecast ledger preserves each value.

Retire this direct conversion of threshold distance to risk. The better-performing entry-range baseline remains a research comparator. This experiment estimated downside at the parent's exit, issued no trading policy, and supplies no evidence about gains after friction or compliance with drawdown rules.

### Reproduction

From the branch root, run the following commands. The original Forecast and signed Hold value archives stay in the inherited results directory.

```sh
python -m unittest discover -s experiments/hold_work -q
python -m experiments.hold_work.run_downside experiments/hold_work/results rerun
```

[Exact protocol](../downside_protocol.md) · [Per-decision forecasts](forecasts.csv.gz) · [Scores and paired intervals](summary.json)
