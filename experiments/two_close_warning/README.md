# Exact two-close dynamics and an overconfident warning

The scenario model replays one earlier session's actual paired inputs through each currently immune state whose earliest possible reversal is two closes away. Feeding the future realized pair into the algebra, solely as a verification, reproduced the terminal sign on all 26,487 scored cases. Eight additional discovery warnings were censored. Replacing unknown future inputs with the previous session's paths gave the following probabilities.

| Exposed panel | Cases | Events | Joint mean forecast | Observed | Joint Brier | Prior-session rate Brier | Joint minus rate, paired 95% interval |
|---|---:|---:|---:|---:|---:|---:|---:|
| Discovery | 10,520 | 286 | 4.63% | 2.72% | .02789 | .02652 | [.00051, .00240] |
| External | 15,967 | 471 | 3.74% | 2.95% | .02886 | .02870 | [.00004, .00031] |

The scenario forecast ranked events weakly (AUROC .554 and .551). External warnings in the 5–10% bin averaged 6.01% predicted with 3.53% observed. Discovery warnings above 10% averaged 13.14% predicted with 3.26% observed. Replacing unknown charge with its fixed price-only mean raised mean probabilities to 23% on both panels. Using mean charge inside a threshold omits the probability mass at zero charge. Rotating historical effort within price-magnitude bins had much smaller effects and both paired intervals included zero. The joint forecast failed the advancement criterion. There is no actionable price or trade endpoint here.

[Registered definition](protocol.md) · [Scores and calibration](results/summary.json) · [Warning ledger](results/forecasts.csv.gz)

```sh
python -m experiments.two_close_warning.run experiments /tmp/mnq-two-close
cmp /tmp/mnq-two-close/summary.json experiments/two_close_warning/results/summary.json
cmp /tmp/mnq-two-close/forecasts.csv.gz experiments/two_close_warning/results/forecasts.csv.gz
```
