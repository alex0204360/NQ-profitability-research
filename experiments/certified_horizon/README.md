# How many closes must the reservoir's sign survive?

A one-step lookahead uses only the stored charge. A two-step lookahead also has to account for charge that can arrive on the intervening bar. In the normalized state space of the frozen parent, the earliest possible neutral or opposite signal is the first integer h ≥ 1 satisfying

```text
|F| ≤ S + sum((7/8)^(-j), j = 1 ... h-1)
```

F is the current signed forecast divided by the current range. S is the unspent stock. The sign is guaranteed unchanged for the next h−1 contiguous updates. This statement ends at a reset. It places no bound on the price of MNQ during those minutes.

### Proof and witness

Write d for the sign at issuance and orient motion u to that sign. The scalar deficit D=dF−S measures the excess over stock available for an immediate reversal. Updating the exact frozen weights gives D′=a[D+2S max(u,0)]−q with a=7/8 and charge 0≤q≤1. Therefore D′≥aD−1. Repeating the lower bound gives the inequality above. Zero motion and maximal effort for h−1 bars attains equality in every minimum-deficit step. A saturated adverse final motion then discharges the stock to attain a neutral or opposite sign. This witness is a construction in continuous encoder space. Discrete market prices and future trade volume may delay a realizable flip.

For a currently immune state, at least a(|F|−S) new charge is required on the next bar merely to make the state reachable. Favorable motion can increase that requirement. On all 2,167 observed transitions from immune to reachable, actual charge satisfied this lower bound.

| Exposed panel | Warnings | Guaranteed ≥1 unchanged close | Guaranteed ≥2 | Guaranteed ≥3 | Violations across observed strict-prefix checks |
|---|---:|---:|---:|---:|---:|
| Discovery | 13,120 | 10,631 | 75 | 7 | 0 / 10,709 |
| External | 19,633 | 16,036 | 25 | 0 | 0 / 16,061 |

For external states with earliest possible reversal at close two, only 471 of 15,967 fully observed cases actually reversed then (2.95%). The bound answers what is mechanically possible. Rates and censoring at each horizon, including the held subset, are in the [summary](results/summary.json). The largest absolute one-step deficit identity error across panels was 1.56×10⁻¹⁵. The [per-issuance ledger](results/horizons.csv.gz) retains each current state, horizon, observed strict prefix, and charge floor.

```sh
python -m experiments.certified_horizon.run experiments /tmp/mnq-horizon
cmp /tmp/mnq-horizon/summary.json experiments/certified_horizon/results/summary.json
cmp /tmp/mnq-horizon/horizons.csv.gz experiments/certified_horizon/results/horizons.csv.gz
python -m unittest experiments.certified_horizon.test_bound
```
