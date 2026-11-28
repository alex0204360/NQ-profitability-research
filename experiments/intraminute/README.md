# The minute lead was concentrated before the first observable print

The publisher calls its files “tick”, but its downloader asks the gateway for unit 1 and unitNumber 1. The gateway defines unit 1 as **second**. The rows contain OHLCV; hundreds of thousands of regular-session rows span multiple prices. They carry no bid or ask, fill receipt, or row-level expiry identifier. The downloader maps both symbols to June 2026. [Publisher at pinned commit](https://github.com/axb0306/cme-futures-ohlc/blob/60abd3fb6369c6ce0b6a4a65b0f2562fc96b1264/update_data.py) · [Gateway unit enumeration](https://gateway.docs.projectx.com/docs/api-reference/market-data/retrieve-bars/)

On the 27 expected regular dates (10,530 minutes), 5,209 minutes reproduced every OHLCV field of both contracts under minute-start labeling. Moving each timestamp one second earlier produced zero joint exact matches. The common timing cohort contains 4,978 minute decisions across 23 dates, with the same rows at every tested delay. It selects on coverage through the final endpoint and is a retrospective timing diagnostic.

| Time from signal-minute end to modeled entry | Rank vs signal-close to entry move | Rank vs subsequent 60-second move | Mean subsequent signed move, pts | Paired 95% daily-block interval, pts |
|---|---:|---:|---:|---:|
| 0 seconds | 0.289 | −0.014 | −0.149 | [−0.371, +0.150] |
| 1 second | 0.051 | −0.013 | −0.113 | [−0.325, +0.158] |
| 9 seconds | −0.003 | +0.009 | −0.0002 | [−0.192, +0.239] |
| 30 seconds | −0.011 | +0.0003 | +0.019 | [−0.214, +0.267] |
| 60 seconds | +0.001 | +0.016 | +0.076 | [−0.145, +0.281] |

The original three-point threshold issued zero trades in the common cohort. The April 8 10:08 outlier lies in a gap in both finer archives, so its large minute close-to-open move cannot be timed independently here. Both last print timestamps occupied the same second for 4,722 of 4,978 decisions. Only 11 had an older MNQ print; that stratum is too small to support a trading conclusion. The score's strongest relationship involved movement into the first available print. The experiment found no reliable directional move afterward.

Rebuild with **MNQ_fine.csv** and **NQ_fine.csv** taken from each symbol directory at the pinned commit (filenames ending in tick_20260309_20260415.csv); retain the original MNQ.csv and NQ.csv minute files in the same directory. The runner enforces source hashes.

```sh
python -m experiments.intraminute.run MARKET_DIR RESULTS_DIR
```

[Frozen design](protocol.md) · [Coverage and full results](results/summary.json) · [Per-minute coverage](results/minute-coverage.csv.gz) · [Per-decision timing](results/timing.csv.gz)
