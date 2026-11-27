# Contemporaneous volume versus historical volume

The study used the final 55 exposed external MNQ sessions, January 27 to April 15, 2026. Each target used the preceding five complete sessions as five separate same-minute volume donors. Prices, original decisions and scale came from the target itself. The replay reproduced all 541 archived next-open original trades across the full 60-date source. Actual-volume and unit-mass trades matched the first experiment on the 55 target dates.

At $6 per round trip, the overnight donor comparison was sensitive to the assumed fill delay. Values in brackets are descriptive 95% circular-block bootstrap intervals for the paired mean daily difference.

| Strategy | Fill | Actual net | Unit mass net | Mean donor net | Actual less donor mean | Interval, USD/day |
|---|---|---:|---:|---:|---:|---:|
| Fixed entries | Next open | −$3,892.00 | −$3,531.50 | −$3,659.20 | −$232.80 | [−$9.03, +$0.30] |
| Fixed entries | One minute later | −$2,373.50 | −$2,626.50 | −$2,652.90 | +$279.40 | [−$2.15, +$14.84] |
| Full strategy | Next open | −$4,688.50 | −$4,267.00 | −$4,609.30 | −$79.20 | [−$8.79, +$6.43] |
| Full strategy | One minute later | −$2,751.00 | −$2,781.50 | −$3,001.60 | +$250.60 | [−$3.65, +$13.79] |

Live timing was unobserved. The comparison found no robust advantage for contemporaneous volume in this head. All four intervals crossed zero and both comparisons reversed sign with an additional minute of delay. The fixed-entry next-open result was lower than each of its five donor results. This is an exploratory result on previously used data.

[Registered design](../alignment_protocol.md) · [All five lags and costs](results.json) · [Daily economics](daily.csv) · [Trade ledger](trades.csv.gz) · [Input checksums and quality checks](source.json)

From the repository root, put the two checksum-matching exposed external CSVs in MARKET_DIR under the names MNQ.csv and MNQ_5min.csv.

```bash
python -m experiments.hold_work.run_alignment MARKET_DIR RESULT_DIR
```
