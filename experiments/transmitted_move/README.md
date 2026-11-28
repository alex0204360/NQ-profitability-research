# Did the lagging contract catch up, or did the leader withdraw?

Two price paths can erase the same NQ–MNQ spread. The lagger can move toward the first contract, or the first contract can give back its move. This recurrent neuron stores both prices when the oriented gap is widest. On reunion it attributes the closed distance to the two observed price changes. The identity is exact for the observed closes; it supplies no evidence by itself that the next move will be profitable.

Across 23 dates with signals, 13,247 episodes resolved. In 5,411 the lagger supplied at least three quarters of the closure; 5,492 met the opposite threshold. The circuit abstained on the other 2,344. The combined prespecified policy followed the original move in the first group and faded it in the second. Trading one MNQ with a 60-second hold produced the following replay.

| Entry delay from completed signal | Trades | Gross USD | Net USD at $6 |
|---|---:|---:|---:|
| 0 seconds | 3,127 | −949.00 | −19,711.00 |
| 1 second | 3,085 | −211.00 | −18,721.00 |
| 9 seconds | 2,833 | −1,126.00 | −18,124.00 |
| 60 seconds | 1,876 | −760.00 | −12,016.00 |

There were no missing entries, late accepted exits or unresolved positions across these modeled delays. At one and nine seconds, the combined policy’s observed upper intrabar drawdown was $18,815.00 and $18,174.50. Both standalone continuation and standalone fade lost money at every delay. No paired $6 interval had a positive lower bound against any matched control at either one or nine seconds. Fills are opening trade-price proxies. Bid/ask quotes, within-second event ordering and actual receipt times are unavailable. Retire the combined rule; the linked exhaustive study checks whether reassigning its event categories could have overcome costs.

[Exact neuron and registered decision](protocol.md) · [Event states](results/events.csv.gz) · [Opportunity and execution archive](results/opportunities.csv.gz) · [Risk report, controls and accepted orders](results/README.md) · [Policy-class bound](https://github.com/alex0204360/NQ-profitability-research/tree/research/mnq-transfer-policy-bound/experiments/policy_bound)

From the branch root, use the authenticated-by-hash public files documented in the [source audit](https://github.com/alex0204360/NQ-profitability-research/tree/research/mnq-nq-intraminute-audit/experiments/intraminute).

```sh
python -m unittest -q experiments.transmitted_move.test_neuron
python -m experiments.transmitted_move.run MARKET_DIR RESULTS_DIR
python -m experiments.transmitted_move.metrics RESULTS_DIR/opportunities.csv.gz MARKET_DIR/MNQ_fine.csv RESULTS_DIR/schedule.json RESULTS_DIR
```
