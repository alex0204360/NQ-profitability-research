# Does price remember where participation accumulated?

**Decision: retire both challengers from advancement.** Remembering the price of a deposit reduced drawdown relative to the scalar reservoir. Waiting for a return and then an outbound close reduced turnover again. That second circuit earned $366.50 at $3 costs over 34 exposed sessions. It lost $8.50 at $6, and $293 with $6 and an additional minute. All results are hypothetical for one MNQ contract. Independently validated discoveries remain zero.

## What the networks compute

Each deposit from the reservoir's charge neuron retains its closing price and the price scale at that moment. A one-range departure latches a direction. A later return near that address permits a forecast back toward the departure level. The confirmation circuit requires price to move away from the address again before it votes. Both use exact weights programmed before their respective scores. Each has an equal-mass control with identical site trajectories. The [design](design.md), [weights](weights.json), [recurrence](circuit.py), and [first replay diagnosis](initial_diagnosis.json) specify the experiment. The original circuit freeze is commit 3eb4fdd. The confirmation freeze is c53f2b7.

## Net after costs and drawdown

Trades and drawdown span the exact September–October archive followed chronologically by the **reissued** November history. DD is peak-to-trough equity at minute closes including opening equity and fees. No account overlay changes exposure. Next open fills after the completed signal bar. Delayed adds a minute to signal-driven entry and exit.

| Model | Next-open trades | $3 net | $6 net | Delayed trades | Delayed $3 net | Delayed $6 net | Worst marked DD across four scenarios |
|---|---:|---:|---:|---:|---:|---:|---:|
| Reservoir on these same bars | 300 | $1,834 | $934 | 278 | $707.50 | −$126.50 | $2,976.50 |
| Price-addressed return | 316 | $606.50 | −$341.50 | 297 | −$747 | −$1,638 | $1,658.50 |
| Return, equal mass | 412 | $231.50 | −$1,004.50 | 383 | −$530 | −$1,679 | $1,804 |
| Confirmed return | 125 | $366.50 | −$8.50 | 121 | $70 | −$293 | $637 |
| Confirmed return, equal mass | 169 | $489.50 | −$17.50 | 165 | $149.50 | −$345.50 | $587.50 |

The confirmed head averaged $2.93/trade at base costs and about −$0.07 stressed on next-open fills. The corresponding delayed averages were $0.58 and −$2.42. At $6 next-open its daily difference from the equal-mass confirmation control was $0.26; the descriptive paired five-session block interval was −$18.37 to +$17.90 per day. The interval against cash was −$20.69 to +$18.65. The data do not resolve incremental predictive value for the charge weights. Removing the best date takes its delayed $3 net from +$70 to −$114. The $1,500 budget uses a historical minute-close measure. Intrabar or trailing account exposure could be larger.

| Confirmed return by source panel | Trades, next / delayed | Next $3 / $6 net | Delayed $3 / $6 net |
|---|---:|---:|---:|
| Sep 14–Oct 9, exact | 91 / 89 | $301 / $28 | −$13 / −$280 |
| Nov 3–13, reissued | 26 / 24 | $13 / −$65 | $230 / $158 |
| Nov 16–20, reissued | 8 / 8 | $52.50 / $28.50 | −$147 / −$171 |

## Where the signal lost value

Of 775 first returns on the September–October tape, 228 closed through the anchor immediately. Only 252 sites recorded a subsequent outbound close before extinction. Sites overlap, and multiple sites can contribute to one trade. Of the first circuit's 220 immediate trades, 75 had already lost their directional vote at the next close. After surgery the count was 31 of 91. Waiting for a turn reduced the number of trades, but the fraction with a short-lived signal stayed near one third.

In a timing counterfactual, hold the 91 September–October confirmed trades fixed. Moving just their entry fills one minute later cost $332.50 gross. Moving just their signal-driven exits one minute later added $20. The matched total fell from $574 to $261.50 gross. On Nov 3–13, delaying the entry on the 26 confirmed trades instead *added* $175.50. Entry timing sensitivity changed sign across panels. This attribution uses subsequent opens for measurement only. The full delayed replay separately accounts for changed trades and occupied slots. [Attribution](results/attribution.csv)

## Why the old reservoir looked better in November

The **original archived** next-open reservoir earned $1.89 gross per trade in September–October and $28.72 across 14 November dates. Median prior price scale at its entries expanded from 12.05 to 21.01 points. Mean realized signed displacement, divided by each trade's prior scale, increased from 0.094 to 0.379. Larger dollar moves alone therefore do not explain the difference. There was also selection by a fixed point hurdle, a different distribution of outcomes, and uncertain contract continuity. November's median $6 trade made $2. Removing its best date left +$1,224. Removing its best five trades instead left **−$272**, and the same diagnostic under delayed fills left −$356. This is evidence of tail dependence. Selecting those trades in advance would require a separate hypothesis. [Baseline audit](results/baseline_audit.csv)

Vendor revisions also change the result with the model held fixed. The original November $6 net was $2,112.50 immediate and $1,904 delayed. Reissued bars give $1,781.50 and $1,282.50. Matching by signal time, entry time, and side gives 77 common immediate entries out of 93 original and 94 revised. Gross fell $140.50 on those matched entries. The unmatched trades contributed another −$184.50 difference in gross. The revision explains sensitivity of the estimate, while both editions still show positive November net for the reservoir. The historical comparison cannot isolate a market cause from chance.

## Source, contract and fills

September–October uses the six original hash-verified continuous MNQ=F parts, with 7,796 of 7,800 regular-hours bars on 20 dates. The original reservoir reproduced its archived ledgers, daily changes, and marked drawdowns on these bars. For November the three original response/CSV pairs were unavailable. The exact prior URLs returned dated MNQZ26.CME charts with different SHA-256 digests. The normalized reissue contains every regular-session minute across 14 dates (5,460 bars). The audit records both editions' identities, the original URLs, and changes in the frozen replay. The dated symbol, CME exchange code, USD and one-minute granularity are known. The vendor did not supply independent expiry confirmation or definitive timestamp semantics. November is exploratory on a pinned revision. Every date had prior research exposure. The registered reservoir test remains at its original commit and no upcoming session was accessed. [Source audit](results/source_audit.json) · [Original prospective protocol](../path_order/prospective.json)

CME specifies $2 per index point and 0.25 points per tick, or $0.50. NinjaTrader's published MNQ row, checked November 22, 2026, listed exchange/NFA $0.36 and clearing $0.19 per contract side plus $0.09, $0.29 or $0.39 commission according to plan. That implies $1.28, $1.68 or $1.88 round trip before spread and slippage. The replay inherits a $2 fee allowance plus one or four adverse ticks per side, giving exactly $3 or $6. A broker schedule does not establish the user's actual fees for these dates. Minute OHLCV lacks bid/ask, depth and order fills. Spread and next-open execution remain unverified. [CME contract specifications](https://www.cmegroup.com/markets/equities/nasdaq/micro-e-mini-nasdaq-100.contractSpecs.html) · [NinjaTrader commission schedule](https://ninjatrader.com/pricing/commissions/)

## Reproduce

Run from this directory with Python 3.12, NumPy and pandas. Extract the six numbered discovery parts from Git commit 8336fe8. The private reissue input bundle contains three bounded CSVs at extension1/bars.csv, extension2/bars.csv and november/bars.csv. The runner checks each against a pinned SHA-256. The private gzip bundle for this run has SHA-256 332e92f7cab9910c367d3e10e7bdb27f72cf8f5ddd3a6f2d1674e702d7c9dca5. Omit the November arguments for an exact discovery-only replay. Use a new output directory for partial runs.

```sh
mkdir -p /tmp/mnq-exposed/discovery
for i in 01 02 03 04 05 06; do
  part=MNQ_Yahoo_1m_20260913_20261012_part${i}.csv
  git show "8336fe8:data/mnq_oracle_2026/$part" > "/tmp/mnq-exposed/discovery/$part"
done
mkdir -p /tmp/mnq-reissued
tar -xzf /path/to/mnq-reissued-20261122.tar.gz -C /tmp/mnq-reissued
python score.py --discovery /tmp/mnq-exposed/discovery --november-dir /tmp/mnq-reissued --reissued --out results
python attribution.py --discovery /tmp/mnq-exposed/discovery --november-dir /tmp/mnq-reissued --reissued --out results/attribution.csv
python baseline_audit.py
python -m pytest -q test_circuit.py ../path_order
```

The [scenario summaries](results/summaries.csv) include expectancy, gap trades, drawdown and paired daily block intervals. The [daily results](results/daily.csv) include zero-trade days. The [trade ledger](results/trades.csv) records decision-time states and fills once for each distinct panel and delay at $3. Subtract $3 from each trade to reconstruct the $6 ledger. Aggregate panels overlap their components and must not be added to them.
