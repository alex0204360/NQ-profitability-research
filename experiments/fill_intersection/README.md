# Can a market memory learn the part of a move that survives execution delay?

Retire both challengers. The first learned too little about future executable displacement from path shape. The second identified moves that depended on a single minute, but the other seven minutes failed to predict a profitable retracement. Every date was previously exposed.

| One MNQ, 34 sessions | Next open $3 | Next open $6 | Additional minute $3 | Additional minute $6 | Worst minute-close drawdown |
|---|---:|---:|---:|---:|---:|
| Intersection memory | −1,136 | −2,495 | 1,057.50 | −301.50 | 3,915.50 |
| Midpoint control | −548 | −2,057 | 1,457.50 | −51.50 | 4,201.50 |
| Pooled memory control | 1,377 | 606 | 1,596.50 | 825.50 | 2,616.50 |
| Single-minute deletion | −2,787.50 | −3,792.50 | −832 | −1,837 | 4,353 |
| Intact fade control | −5,378 | −7,754 | −4,871 | −7,244 | 8,850 |
| Distributed-move fade control | −4,213.50 | −5,932.50 | −4,303.50 | −6,022.50 | 7,025.50 |


## What the neurons learned

At each eligible eight-minute clock tick, the memory encodes the relative order of three closes, oriented along the last leg. For each matured example it takes the point nearest zero in the interval between the two executable signed displacements. For example, [+2,+9] contributes +2 and [−2,+9] contributes zero. Its vote comes from prior completed examples at the same address. The midpoint and pooled controls respectively remove the timing projection and the address distinction. Exact coefficients, label maturity and treatment of gaps are in neuron.py and design.md.

The 734 active intersection probes had mean signed next-open displacement −0.21 points and delayed displacement +0.93. Stress break-even for an isolated trade is +3 points. The midpoint control had +0.31 and +1.08. The projection suppresses conflicting past observations, but cancellation within a past pair provides no guarantee about the next pair. The pooled control cleared both economic stress replays, yet deleting its five best delayed trades took stress net from +825.50 to −2,147.50. Its mean delayed probe changed from −2.36 points in September–October to +4.46 in November. Its drawdown exceeded the $1,500 budget.

In the deletion experiment, erasing the strongest aligned minute reversed the sign of the eight-minute path. A neuron predicted that the remaining seven increments would reassert their direction, with the forecast capped by both observed displacements. The 384 active probes averaged −2.08 points immediate and +0.40 delayed. For the same decisions, the delayed entry contributed +0.56 points and the delayed exit +1.92. The inherited trading engine merges adjacent same-side votes, so probe averages measure the neuron on a fixed horizon while the trade ledger measures realized hypothetical exposure. Neither architecture earned a prospective slot. Sign inversion after inspecting losses would require a fresh economic hypothesis and subsequent independent evidence.

## Replication

Use the six discovery files and three bounded November reissue CSVs described in ../return_map/README.md. The exact normalized November hashes reproduced, although the downloaded response hashes differed from the prior receipts. The last window required excluding one off-minute trailing quote. Source contract and fill uncertainty carry forward from the parent study. The runner checks the six discovery hashes, original discovery reservoir ledger and the three November CSV hashes, and replays the reservoir revision audit. It keeps chronological memory across all 34 dates, including the transition from continuous to dated vendor symbols. September–October contains four missing bars. The frozen reservoir prospective protocol at the parent commit remains in force.

Run from this directory with NumPy and pandas. The two results directories contain per-minute activations, fixed-horizon probes, every trade, daily net including idle days and scenario summaries. Month rows partition the combined run with its inherited memory. Columns ending in “points” are model units. Monetary outputs are simulated USD with one $2-per-point MNQ and per-round-trip costs including assumed slippage. Drawdown is close-marked, with no account overlay.

```sh
python run.py --november /tmp/mnq-reissued --out results
python run.py --november /tmp/mnq-reissued --erasure --out erasure_results
python diagnose.py
python timing.py
python test_neurons.py
```
