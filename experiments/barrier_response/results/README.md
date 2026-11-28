# Executable response to the reservoir reversal boundary

The study tested whether price recovered after reaching the published one-bar reversal boundary. The primary signal followed the prior reservoir direction when the touch bar closed back on that side of the boundary. A separate strategy followed the crossing direction after a close through it. Orders used executable opens for a five-minute hold. Controls used the candle body, always-long direction, the price-only boundary, and cash.

| Exposed source | Fill | Retained trades | Retained gross | Retained net at $6 | Crossing net at $6 |
|---|---|---:|---:|---:|---:|
| Discovery, 40 sessions | Next open | 436 | +$1,838.50 | −$777.50 | −$2,147.00 |
| Discovery, 40 sessions | One minute later | 414 | +$41.50 | −$2,442.50 | −$2,514.50 |
| External, 60 sessions | Next open | 631 | +$590.50 | −$3,195.50 | −$5,133.00 |
| External, 60 sessions | One minute later | 610 | +$1,591.00 | −$2,069.00 | −$3,795.00 |

Retained events earned positive gross dollars in all four standalone runs. Each lost money at $6 and therefore failed the stricter $9 gate. Overlapping event outcomes are diagnostic observations. The table uses trades that fit a single independently managed position under each delay.

[Registered design](../protocol.md) · [Costs, risk, and paired intervals](summary.json) · [Daily returns](daily.csv) · [Event and fill ledger](events.csv.gz) · [Source checksums](source.json)

```bash
python -m experiments.barrier_response.run MARKET_DIR RESULT_DIR
python -m unittest experiments.barrier_response.test_opportunities
```
