# Counterfactual reservoir capacity on exposed MNQ sessions

The one-step stress margin asks whether the parent forecast would keep its sign if a half-range adverse move released available stock. The price control integrates effort out of the same routing calculation. Both were evaluated on the 40-session discovery archive and the 60-session external archive. The replay reproduced all 935 original next-open fills.

| Policy | Discovery next open | Discovery +1 minute | External next open | External +1 minute |
|---|---:|---:|---:|---:|
| Original | +$452.50 | −$323.50 | −$3,821.00 | −$2,734.50 |
| Fixed volume exit | +$1,296.00 | +$202.00 | −$3,816.50 | −$4,010.00 |
| Fixed price exit | −$26.00 | −$565.50 | −$2,836.50 | −$2,425.00 |
| Full volume exit | +$891.00 | −$211.50 | −$5,711.00 | −$4,162.00 |
| Full volume entry | +$1,063.00 | +$42.50 | −$3,806.50 | −$2,929.50 |
| Full volume joint | +$901.00 | +$115.00 | −$5,550.50 | −$4,461.50 |

The table uses $6 round-trip friction. Every external strategy was negative at $9. The $6 volume exit's paired daily edge over the original had a 95% interval of −$61.33 to −$4.37 at next open and −$47.26 to −$1.17 with an extra minute. External joint volume upper intrabar drawdown was $6,714.50 and $5,836.00. No challenger passed the registered screen.

The exact one-step sign barrier accounted for all observed contiguous close reversals on both archives. There were 781 discovery and 1,115 external adverse touches whose close retained the original sign. The chart's fixed volume exit saved $488.50 on a November 25 short and surrendered $434.00 on a November 10 winner. The November 19 10:45 long improved by $246.00. All three comparisons use identical entries. [Cases and explanatory chart](cases.html) · [Barrier audit](barriers.json)

[Registered design](../protocol.md) · [All economic and risk results](results.json) · [Daily ledger](daily.csv) · [Attribution](attribution.json) · [Prediction diagnostics](prediction.json) · [Source checksums](source.json)

The three compressed replay ledgers contain trade fills, original open-position activations, and the market-wide score tape. The source directory must contain the pinned MNQ.csv and MNQ_5min.csv inputs described in the source receipt. Use the same directory for the archive and chart commands.

```bash
python -m experiments.capacity.run MARKET_DIR RESULT_DIR
python -m experiments.capacity.audit_barrier MARKET_DIR RESULT_DIR
python -m experiments.capacity.chart RESULT_DIR RESULT_DIR
python -m experiments.capacity.prediction --market MARKET_DIR --out RESULT_DIR
python -m unittest experiments.capacity.test_neuron
```
