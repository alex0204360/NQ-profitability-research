# Volume auction network

The three frozen graphs were tested on 39 historical MNQ sessions, the next full MNQ session after freeze, and all 247 complete sessions of the 2023 NQ transfer year. Zero qualified volume-based economic discoveries. The new volume-weighted impulse earned $47.50 after costs on its first post-freeze MNQ session. Its equal-mass control earned $78; its price-only symmetric impulse control earned the same $47.50. Forecasts were reconstructed after the close. No first-seen November 25 calls or nine-second quotes were available.

[Offline chart and friction inspector](auction-replay.html) · [Download the weights and inference kit](volume-auction-kit.zip)

## What the frozen networks compute

* **Inventory discharge** estimates how much excess buyer and seller inventory a candle represents from reported volume and the location of its close. Separate rectified neurons track the fraction of each of 32 cohorts newly under pressure. The signed square-root impact adds to a displacement memory, with volume-time leakage and debits for already delivered price travel. Commit 461c271 froze the design. [Equations](protocol.md)
* **Forward cascade** asks how much unspent opposing inventory a hypothetical additional price move would reach. Eight propagation layers calculate a target using the same finite mass field. The decision requires room to cover the invalidation distance and three points of friction. Target and invalidation are fixed at the signal and tested on subsequent closes. Commit 900fcff froze this redesign after the first graph produced costly turnover. [Equations](cascade_protocol.md)
* **Volume-weighted launch** tests a rare two-bar impulse against the volume-weighted cost basis of older candles. Momentum, collision loss, unaccepted wick, prior range and overhead inventory are computed by separate units on both sides. The slower favorable return caps the score. A score beyond ±3 points requests a modeled next-open entry, normally held for four minutes. Commit a736654 froze it before scoring. Volume and close location are proxies; OHLCV does not identify forced orders or buyer/seller inventory. [Equations](impulse_protocol.md)

## Net results

| Full strategy | Earlier 20 MNQ | November 14 MNQ | Five disjoint MNQ | Nov 25 MNQ | 247 NQ sessions |
|---|---:|---:|---:|---:|---:|
| Original reservoir | −847.50 | +2,112.50 | −592.50 | −220 | −59,873.50 |
| Inventory discharge | −5,568.50 | −2,205 | −1,858.50 | −713 | −141,289 |
| Forward cascade | −1,343 | −1,638 | −468.50 | −287.50 | −31,118 |
| Volume-weighted launch | +52.50 | −156.50 | −297 | +47.50 | −559 |
| Equal-mass launch | −14.50 | −88 | −253 | +78 | +1,287.50 |
| Symmetric price-only launch | +90.50 | −435.50 | −307 | +47.50 | +3,321 |

Figures are USD for one contract. MNQ uses $2 per point and $6 per round trip. NQ uses $20 per point and $14.50 per round trip. Transfer holds the three-point entry hurdle and model coefficients fixed. The original and momentum controls retain their own entry policies. Native NQ stress adds $10 per round trip. The transfer summary.json uses the common $2/point, $6 normalization; native dollars are in transfer/attribution.json and the chart. Cash earns zero. The $1,500 screen uses peak-to-trough intrabar drawdown at base costs.

The weighted launch made 35 trades in the earlier MNQ window, with $353 maximum intrabar drawdown and −$52.50 net at $9 friction. In the 14 November sessions it made 13 trades with $567 drawdown; three entries added by real volume lost $115.50, while two skipped control trades had lost $47. The matched entries paid the same P&L. On the five-date panel, three additional entries lost $44 combined. On native NQ, the equal-mass launch gained $1,287.50 and the volume-weighted launch lost $559. The volume graph increased participation to 182 trades from 105. Its NQ gross was $2,080, break-even friction $11.43/trade, below $14.50 modeled cost. The positive NQ control remained exposed to $4,100 intrabar drawdown.

## The earlier profitable v08 ledger

Re-executing the existing impulse_context replay on the hash-pinned source reproduced all 245 prior v08 ledger rows. Gross travel across the modeled trades was 903.75 points, or 3.69 points per trade. At the original NQ economics those fills earned $18,075 gross less $3,552.50 friction, giving **+$14,522.50**. Applying the same moves and trade times at one MNQ's multiplier gives $1,807.50 gross less $1,470 friction, or **+$337.50**. At $9 round-trip friction it gives **−$397.50**. This is a contract-size illustration on NQ prices. Actual MNQ execution requires its own data. The full pinned ledger covers parts of 2022 through 2024 and its original entry hurdle and exit convention differ from the matched transfer study. [Repricing receipt](results/v08_contract_bridge.json)

## First post-freeze replay

November 25 had 390 complete dated MNQZ26 bars. At 13:17 ET the weighted graph entered long at 25,857.75 and exited at 25,899.75 for +$78. At 15:31 ET it entered short at 25,948.75 and exited at 25,961.00 for −$30.50. Intrabar drawdown was $108. The original traded 13 times at one MNQ and lost $220 with $1,536.50 intrabar drawdown. The earlier four-clock risk head covered 315 of 350 matured paths using the end-of-day capture. These are separate diagnostic outcomes. The recorder retained no November 25 forecasts, so availability of the signal on the intended execution clock remains unverified. [Session scorecards](results/postfreeze/)

## Inspect and reproduce

Open auction-replay.html locally, select the window and head, and change round-trip friction while keeping fill times and prices fixed. The day ledger uses the selected fee. The drawdown card always reports base-cost intrabar drawdown. The chart includes the original Forecast (pts), the selected score and its comparison. For the cascade the selected line is zero apart from qualifying release events. The chart is a retrospective inspector.

To inspect closed bars locally, use Python with NumPy and pandas. In the downloaded kit run:

```sh
python latest.py my-session.csv --contract MNQZ26
```

Supply timestamp_utc, contract, open, high, low, close and volume. Use one complete-to-date, minute-start session beginning at 09:30 ET, timezone-qualified timestamps and the correct dated contract. Output includes three heads and a comparison with volume held constant. Flat-entry diagnostics do not track an existing live position.

From the repository, run:

```sh
python -m pytest -q test_network.py
python study.py /path/to/private/scratch /tmp/discovery
python study.py /path/to/private/scratch /tmp/disjoint --track replication
python study.py /path/to/private/scratch /tmp/transfer --track transfer --nq /path/to/Dataset_NQ_1min_2022_2025.csv
python matched_economics.py /tmp/transfer --nq /path/to/Dataset_NQ_1min_2022_2025.csv
python postfreeze.py /path/to/nov25-auction-original /tmp/next-day
```

The NQ archive has SHA-256 1577e60a7feab411e49da7a56c7052a64738cd1757cfd60aa11fd783ff43b60b. It contains ET timestamps and an explicit volume column. Regular sessions were selected by 390 unique 09:31–16:00 labels and mapped from assumed bar-end stamps to minute starts. Roll handling and the timestamp convention are not independently verified. This archive was used in earlier NQ research. No publicly downloadable independent older MNQ minute source with adequate provenance was located in this run. The 39 MNQ dates are research data already used by the program. The sealed 2025 MNQ holdout was not opened. Numerical screens include $9 stress and net without best date; no head passed. The original prospective study is separate.
