# Where the NQ–MNQ price difference disappeared

Across 20,768 synchronized decision bars from 59 exposed sessions, the volume-weighted discrepancy ranked the move from MNQ's final print to its next opening print (Spearman 0.265). Its correlations with the next two separately executable open-to-open minutes were −0.014 and +0.006. Equal venue weights gave essentially the same ranks.

Only one signal cleared the frozen three-point hurdle. At 10:08 New York on April 8 the NQ close stood 27 points below the MNQ close, relative to a zero-point median basis. The neuron forecast −12.63 MNQ points. MNQ moved 20.5 points down before the modeled entry open. The following minute moved 10.5 points up. One MNQ short lost $27 after $6 friction. Entering a minute later made $4 after friction on this one observation. Neither schedule qualifies. This is a last-print analysis on timestamped bars; receipt times and bid/ask execution are unavailable.

The next question is whether finer timestamped records actually reproduce those minute extremes and support measuring the first simultaneous executable price. A matching minute-close relationship alone cannot answer that.

[Prespecified protocol](protocol.md) · [Per-bar predictions](results/decision_bars.csv.gz) · [Trade ledger](results/trades.csv.gz) · [Full results](results/summary.json)

Reproduce from repository root with the two public MNQ files named in the inherited hold_work reproduction guide and NQ_1min_20260120_20260415.csv from the same pinned source commit saved as NQ.csv.

```sh
python -m experiments.dislocation.run MARKET_DIR RESULTS_DIR
```
