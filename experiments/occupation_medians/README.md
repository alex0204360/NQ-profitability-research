# Does volume move the center of occupied prices?

The reservoir’s historical November gain depended heavily on a few trades. A different hypothesis is that where participation concentrates within a short price distribution carries directional information. A twelve-bar memory emits three equal atoms per completed bar at its low, midrange and high. One population assigns unit mass to each atom. The other assigns the bar’s volume to each atom. These are approximations derived from bars. Actual transaction volume at price is unavailable.

Pairwise threshold units at every atom count cumulative weighted mass on either side. The readout averages the two endpoints of the interval containing the weighted medians. It points from the time median toward the volume median and votes when their separation reaches half the median bar range (range floor 0.25 points). This preserves direction under a change of price origin and reverses direction under a price reflection. The initial lower-median neuron failed the second property. On twelve increasing point bars 0 through 11 with the final bar weighted twice, its displacement was +1. Reflect the same prices and it gave zero. The symmetric version gives +0.5 and −0.5. This algebraic correction was committed before scoring. The explicit network and sorted reference agreed on both centers in all 642 eligible historical windows.

A preliminary recurrent area calculation in experiment.py showed that a price-clock subtraction removes spurious activation under constant volume across 6,561 synthetic inputs (the enumeration also tests reversal and scaling). Prior path-order work already modeled ordered area. We retained this experiment and pursued the occupation distribution as the distinct trading hypothesis.

## Replay

One MNQ, $2 per point. Start windows every 20 minutes from 09:30 New York time. Observe 12 completed consecutive bars, enter at the next open, exit five opens later. Delay moves both fills one minute. Missing observation bars skip the signal. Fees and friction together total $3 or $6 per completed trade. Drawdown includes opening equity, allocated entry/exit costs and minute-close marks. Unobserved intraminute excursions and fills can differ. All 34 sessions were previously exposed. September–October uses six hash-verified archive parts. November uses bounded reissues. Their raw response hashes differ from earlier November receipts. The normalized input hash identifies the edition used here. No future session was scored.

| Symmetric readout across 26 trades | Net | Marked drawdown |
|---|---:|---:|
| Next open, $3 | $229 | $550.50 |
| Next open, $6 | $151 | $580.50 |
| Delayed, $3 | $218 | $473 |
| Delayed, $6 | $140 | $504 |

The maximum measured drawdown was below the $1,500 historical budget. Only 26 windows triggered, with 16 positive and 10 negative votes. September–October contributed +$449.50 across 18 trades at next-open $3. November contributed −$220.50 across eight. Removing September 28 leaves −$142.50 next-open and −$172.50 delayed. The lower-median prototype earned $455 next-open at $3. Nine decisions changed under the tie correction. Choosing the prototype for its larger profit would reintroduce an arbitrary dependence on the sign convention for price.

Rotating volume weights by six bars within each observed window preserves their distribution and destroys their original alignment. It earned −$115.50 next-open and −$34.50 delayed at $3. The symmetric circuit’s average daily advantage over this control was $10.13 and $7.43. Descriptive circular five-session block intervals were [−$23.16, $55.07] and [−$17.15, $43.43]. The reverse and toward-time heads appear in the summaries. Rotations change which slots trade and hence do not isolate direction alone.

**Decision.** Retire this trading readout from advancement. The mirror-symmetric median cell has a verified computational property. The tape does not establish transferable predictive value. This work used a separate branch and made no prospective registration or changes to the frozen reservoir.

## Reproduce

With authenticated GitHub CLI and Python 3.10+, run in this directory. The loader enforces the scored regular-hours digest, so a vendor revision raises an error. The compact activation ledgers preserve both medians, vote and next-open outcome even if the source becomes unavailable. The symmetric ledger also includes delayed outcomes.

```sh
python load_exposed.py
python experiment.py
python test_cells.py
python replay.py /tmp/exposed.csv
python symmetry.py /tmp/exposed.csv
python diagnose.py /tmp/exposed.csv
python network.py /tmp/exposed.csv
```
