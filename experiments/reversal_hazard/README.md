# A one-minute warning for the reservoir's own reversal

Distance to the exact reversal price predicted whether the next contiguous close would neutralize or reverse the current signal. The historical data support a warning about the reservoir. The additional contribution from learning the distribution of moves remains unresolved.

| Previously examined sessions | Reachable bars | Actual reversals | Feasibility-only Brier | Fixed distance curve | Learned grid | Grid minus feasibility, paired 95% interval |
|---|---:|---:|---:|---:|---:|---:|
| Discovery, 40 dates | 2,489 | 710 | .20413 | .18082 | .18043 | [−.02805, −.01854] |
| External, 60 dates | 3,597 | 1,073 | .20979 | .18744 | .18750 | [−.02622, −.01868] |

Lower Brier scores mean smaller squared probability errors. Both comparators already assign zero to geometrically impossible reversals. Restricting the table to reachable cases tests whether distance has value within that group. For example, on 1,198 external reachable bars the grid averaged 43.4% and 44.2% reversed. The intervals for the grid versus the fixed curve included zero on both panels. The grid passed its frozen gate on both full populations and both reachable subsets. Four discovery forecasts were censored. An independent verifier reconstructed all 32,753 issued forecasts from archived scores and activations.

Reproduce from this branch's root using Python with NumPy and pandas and the scoring dependencies imported by the runner.

```sh
python -m experiments.reversal_hazard.run experiments/capacity/results /tmp/mnq-warning-replay
cmp /tmp/mnq-warning-replay/summary.json experiments/reversal_hazard/results/summary.json
cmp /tmp/mnq-warning-replay/warnings.csv.gz experiments/reversal_hazard/results/warnings.csv.gz
python -m unittest experiments.reversal_hazard.test_neuron
python -m experiments.reversal_hazard.verify
```

The [frozen experiment](protocol.md) and [complete scores](results/summary.json) include counts during held positions, calibration bins, and block intervals. The [prospective registration](prospective.md) specifies 30 scheduled full MNQH27 sessions beginning February 1, 2027. Its data collection has yet to start. Economic tests have separate endpoints and executable fills. [First eligible exit](https://github.com/alex0204360/NQ-profitability-research/tree/research/reversal-conditioned-hold-value/experiments/branch_value) · [First reachable exit](https://github.com/alex0204360/NQ-profitability-research/tree/research/reachable-decision-value/experiments/reachable_value)
