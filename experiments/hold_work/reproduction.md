# Reproduce the recovered-distance experiment

From the root of this branch, use Python 3.11 or newer with NumPy, pandas and SciPy. The archived environment used Python 3.12.14, NumPy 2.3.5, pandas 2.2.3 and SciPy 1.17.0. A local replay requires two public files plus the discovery chart already in this checkout.

```sh
mkdir -p market
base=https://raw.githubusercontent.com/axb0306/cme-futures-ohlc/60abd3fb6369c6ce0b6a4a65b0f2562fc96b1264/MNQ
curl -fLsS "$base/MNQ_1min_20260120_20260415.csv" -o market/MNQ.csv
curl -fLsS "$base/MNQ_5min_20260120_20260415.csv" -o market/MNQ_5min.csv
python -m unittest discover -s experiments/hold_work -v
python -m experiments.hold_work.replay market replay-out
python -m experiments.hold_work.metrics replay-out analyzed-out
python -m experiments.hold_work.disagreement replay-out analyzed-out
python -m experiments.hold_work.horizon --replay replay-out --market market --out analyzed-out
python -m experiments.hold_work.daily_uncertainty replay-out/trades.csv.gz analyzed-out/daily-intervals.json
```

The source loader verifies file hashes and the discovery chart. It preserves four missing minutes across the 40 discovery sessions. The external data reproduce all 4,680 same-publisher five-minute OHLCV aggregates. The replay verifies the registered brain files, every original entry and exit row in the archived next-open ledger, and both delays' baseline fills and marked equity against the existing execution engine. A new position gets fresh holding memory. A missing minute cancels pending instructions and applies the original gap rule.

The replay writes a trade ledger, all open-position activations, bar-level equity and a source receipt. The analysis writes the predictive ledger, metrics and offline HTML. In the ledgers delay 0 means fill at the next open, delay 1 means one additional minute. net_usd and archived equity_usd use $6; gross_usd minus the selected friction gives the corresponding $3 or $9 net. The archived summary reprices equity too. The original forecast is a signed market-direction score. The hold readings are side-relative points, with positive favoring continued holding.

The external source has symbol-level minute bars without row-level expiry, roll or first-seen timestamps. A matched aggregate cannot resolve those limits. Historical discovery bars come from the archived chart and retain any upstream revisions. An earlier first-seen revision audit reported that replacing volume alone changed the simulated marked result by $997.50. That audit was not rerun here. OHLC drawdown bounds describe modeled paths under fixed bar-open execution; bid/ask fills, live latency and trailing-account eligibility require independent records. All 100 target dates were already exposed. The original prospective registration and journal are outside these replays.
