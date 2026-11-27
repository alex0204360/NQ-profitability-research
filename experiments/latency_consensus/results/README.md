# Latency consensus on exposed MNQ sessions

The registered consensus rule and both robust controls abstained on every eligible retained-boundary event. The next-open midpoint control cleared the hurdle on some events but lost at $6 on both sources. With one more minute of delay, its discovery result was positive across 17 trades and nine dates. Its paired interval against cash still crossed zero. The frozen rule did not qualify for prospective testing.

| Exposed source | Fill | Consensus trades / $6 net | Midpoint trades / $6 net | Always-follow trades / $6 net |
|---|---|---:|---:|---:|
| Discovery, 40 sessions | Next open | 0 / $0 | 18 / −$78.50 | 436 / −$777.50 |
| Discovery, 40 sessions | One minute later | 0 / $0 | 17 / +$312.50 | 414 / −$2,442.50 |
| External, 60 sessions | Next open | 0 / $0 | 2 / −$87.50 | 629 / −$3,109.00 |
| External, 60 sessions | One minute later | 0 / $0 | 2 / −$90.00 | 610 / −$2,069.00 |

Discovery contained 731 eligible signals and 729 paired labels. External contained 1,044 eligible signals and paired labels. After excluding the prior-free first session, the continuous full-feature midpoint's Spearman correlation with mean realized signed holding points was −0.069 on discovery and −0.053 on external. Midpoint trades all faded the event. The only positive midpoint case, discovery with delayed fills, returned $261.50 at $9 before removing any winning trades and had a $6 upper intrabar drawdown of $279. Its $6 daily difference from cash had a descriptive 95% interval of −$3.89 to +$24.23.

Inference used the completed touch bar's encoder scale. Training required an exact scheduled five-minute exit under both latencies. A gap before an actual entry cancelled that order, and a gap during an actual hold closed the position at the next observed open. All candidate forecasts for a session were projected before any labels from that session updated memory.

[Registered protocol](../protocol.md) · [Full results](summary.json) · [Daily results](daily.csv) · [Projections and outcomes](projections.csv.gz) · [Trade ledger](trades.csv.gz) · [Source checksums](source.json)

```bash
python -m experiments.latency_consensus.run MARKET_DIR RESULT_DIR
```
