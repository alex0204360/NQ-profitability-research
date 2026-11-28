# Holding value at the first reachable warning

Moving the decision from the first favorable excursion to the first *reachable* warning raised external next-open flip prevalence from 5 of 272 to 111 of 268. Higher event prevalence did not establish executable value for the probability-weighted exit.

| Panel and fill | Original trades | Decisions | Next flips | Grid exits | Grid change vs original | Exit every first warning, change | Grid net at $6 |
|---|---:|---:|---:|---:|---:|---:|---:|
| Discovery, next open | 394 | 212 | 64 | 210 | +$865 | +$953 | +$1,317.50 |
| Discovery, extra minute | 361 | 174 | 52 | 166 | +$1,154 | +$1,357 | +$830.50 |
| External, next open | 541 | 268 | 111 | 187 | +$413 | +$425 | −$3,408 |
| External, extra minute | 509 | 246 | 97 | 116 | −$385 | −$1,112 | −$3,119.50 |

Each row uses the full original entry book for that panel and fill assumption. All scheduled observations had paired outcomes. At external next-open fills, subsequent signed holding value averaged −9.71 points when a reversal occurred and +5.51 points otherwise. With an extra minute those conditional averages were +0.77 and +3.23. The reversal outcome is available only after the decision. The learned grid's holding-value MSE exceeded the zero-points forecast in all four cells. External grid net at $9 was −$5,031 and −$4,646.50. The fixed-entry experiment failed its prespecified promotion gate. It supplies no independently validated trading rule or unrestricted re-entry result.

The frozen [protocol](protocol.md), [complete results](results/summary.json) and per-decision [ledger](results/predictions.csv.gz) preserve controls, dollar attribution, gain concentration and paired forecast uncertainty.

```sh
python -m experiments.reachable_value.run experiments /tmp/mnq-reachable-replay
cmp /tmp/mnq-reachable-replay/summary.json experiments/reachable_value/results/summary.json
cmp /tmp/mnq-reachable-replay/predictions.csv.gz experiments/reachable_value/results/predictions.csv.gz
```
