# A better estimate of position duration does not establish holding value

A causal memory learned elapsed time from completed parent trades. It improved the estimate of how long the parent position would remain open. Multiplying risk by the square root of this duration failed the prespecified test against entry range alone. All 100 historical sessions were exposed. Every risk score below is a mean 80th-percentile pinball loss in points. Smaller is better.

| Source and fill | Scored decisions | Duration log-MSE, unconditioned | Duration log-MSE, conditioned | Downside loss, range only | Downside loss, conditioned |
|---|---:|---:|---:|---:|---:|
| Discovery 40, next open | 198 | 1.015 | 0.994 | 11.73 | 11.85 |
| Discovery 40, extra minute | 161 | 1.001 | 0.975 | 12.80 | 12.73 |
| External 60, next open | 252 | 0.992 | 0.952 | 9.20 | 9.34 |
| External 60, extra minute | 232 | 0.990 | 0.955 | 8.94 | 9.02 |

The unconditioned comparator learned from exactly the same earlier elapsed times. For the conditioned-minus-unconditioned log-duration MSE, the external next-open difference was −0.0403 with a five-session paired interval of [−0.0679, −0.0118]. With an extra minute the difference was −0.0353 [−0.0693, −0.0025]. Both discovery point estimates also favored conditioning. The next-open discovery interval spanned zero. A small improvement over unconditional duration is the single candidate for a future independent duration-only test.

Against range alone, all four downside intervals included zero. The conditioned rule's strict exceedance rates were about 12% and 11% on the external panel, below its 20% target. Retire the duration-to-downside conversion. The dollar P&L for an execution policy is untested for this diagnostic. It gives no authorization for trading or additional risk.

### Research handoff

| Research item | Verified outcome |
|---|---|
| Signed holding value | Fixed entries benefited on some exposed days. Re-entry erased the benefit at $6 on the external next-open run. The initial and symmetric scores substantially overstated the mean realized holding value. |
| Value of volume | Actual exit-head volume failed to beat a price-only exit consistently across fill schedules. Same-clock prior-session volume controls demonstrated execution sensitivity. |
| Matured-label point forecast | Chronological memory reduced the raw point bias. Zero had lower mean squared error on both panels and fill schedules. |
| Downside and uncertainty | Threshold distance ranked time weakly but generated exaggerated risk differences. Entry range remains the simpler downside benchmark. |
| Original computation worth retaining | A recurrent, four-sum duration estimator improved log-duration error against a matched historical-time control on all four exposed comparisons. Its precision on untouched trades is unknown. |
| Economic and risk qualification | No exit challenger qualified on stressed economics and the historical drawdown budget. No independent validation or live fills were claimed. |
| Local reproducibility | Exact brain code, numerical weights, session receipts, ledgers, counterfactual alternatives and executable replay are maintained on the relevant branches. The candidate duration circuit uses the Python standard library. |

The prospective protocol freezes only the duration question. Keep the original reservoir paper experiment and protected inputs separate. The next scientifically decisive observation is a first-issued duration prediction and its subsequently matured outcome from the registered unseen cohort.

[Prospective duration test](../duration_prospective.md) · [Frozen exploratory design](../duration_protocol.md) · [Scored logs and paired uncertainty](summary.json) · [Per-decision predictions](forecasts.csv.gz) · [Original exit study and case charts](https://github.com/alex0204360/NQ-profitability-research/tree/research/hold-value-work-balance-20261127/experiments/hold_work) · [Matured signed-value study](../matured_results/HANDOFF.md)

From the repository root, reproduce the duration results with the command below.

```sh
python -m experiments.hold_work.run_duration experiments/hold_work rerun
```
