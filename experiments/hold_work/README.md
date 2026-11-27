# Can the reservoir tell when it is worth continuing to hold MNQ?

On 60 exposed sessions, the frozen recovered-distance exit saved $523.50 on identical entries and still lost $3,297.50 at $6 round-trip friction. The full strategy lost $4,201 on 687 trades. The original lost $3,821 on 541. Re-entry added 173 entries, missed 27 original entries and cost $876 in incremental friction. Of the added entries, 140 reopened in the same direction while the original trade would still have been open. At $3 the full strategy edged the parent by $58. At $9 it fell $818 behind it.

## Economic scoreboard

One MNQ contract, next-open fills. The 40 discovery sessions and 60 external sessions are separate, previously studied data sources. The discovery total spans disjoint calendar windows. All values below are net dollars.

| Policy | Discovery 40 at $6 | External 60 at $3 | External 60 at $6 | External 60 at $9 | External 60 at $6, one extra minute |
|---|---:|---:|---:|---:|---:|
| Original | 452.50 | −2,198 | −3,821 | −5,444 | −2,734.50 |
| Fixed entries, two-scale trail | 1,087 | −2,559 | −4,182 | −5,805 | −2,808 |
| Fixed entries, price-only | 1,073 | −1,324.50 | −2,947.50 | −4,570.50 | −1,904 |
| Fixed entries, volume | 1,233 | −1,674.50 | −3,297.50 | −4,920.50 | −1,636.50 |
| Full strategy, two-scale trail | 146 | −3,125 | −4,979 | −6,833 | −3,200.50 |
| Full strategy, price-only | 54.50 | −1,764.50 | −3,840.50 | −5,916.50 | −2,051.50 |
| Full strategy, volume | 217.50 | −2,140 | −4,201 | −6,262 | −1,993 |

At historical $3 friction on fixed next-open entries, the external head saved $6,162 on original losers and added $66.50 of loss on others. It surrendered $6,959 on original winners and gained $1,220 on other winners. The remaining change belongs to originally breakeven trades. Removing the largest three positive interventions turns its $523.50 paired gain into a $609 loss. The full external strategy had $4,445.50 marked drawdown and a $4,488.50 OHLC upper bound at $3. At $6 these rose to $5,738.50 and $5,781.50, respectively, against the historical $1,500 research budget.

## What the neurons learned about holding

The hand-coded neuron rewards excursions that extend the best close. It credits half of a repair below that close and cancels the credit if price traverses the repaired interval backward. The price-only head weights each pulse equally. The volume head asks whether more participation makes the same path more informative. They use the same frozen reservoir for entries.

At the first discretionary eligible close on 272 external next-open trades, the mean volume score was +27.68 points and the mean subsequently realized holding value was −0.25. Spearman correlation was −0.084. One extra minute changed the estimate to +0.028 on 252 trades. The volume increment in rank correlation was −0.009 at next open and +0.045 one minute later. These quantities address ranking and magnitude separately from P&L. There is no calibrated point forecast or independently validated discovery.

On identical external entries the two heads first disagreed 39 times at next open. In 34, the volume version stayed in after the price head requested exit. The position lost another 13.14 points on average from that executable decision to the eventual original exit. When each head instead followed its own subsequent policy, those 34 cases cost the volume version $297 versus price. That distinction matters when reading early-exit labels. Across all fixed entries, volume lagged price by $350, with a descriptive five-session block interval of −$12.09 to −$0.52 per day. After one extra minute, its fixed-entry advantage over price became +$267.50.

## Case review and handoff

The November 19 10:45 long first cleared its 58.62-point entry scale at 10:59. Both heads exited at 11:08 at 27,233 for +$65, versus the original exit at 12:02 for −$564 at $6 friction. The two-scale trail earned $13.50. Both heads explain the $629 improvement equally. Across all 100 dates, the largest rescue was the November 25 12:21 short (+$729.50 relative to original). The most damaged original winner was the November 10 10:18 short (−$549). [Offline case chart](results/hold-value-cases.html)

The impulse-context and Astra predecessors showed weak transfer and strong dependence on timing and extreme days. Path-order produced the frozen reservoir. Return-map and subsequent trade-memory experiments showed why altered occupancy and re-entry can reverse a fixed-entry result. Earlier adverse-response heads also failed to demonstrate a reproducible volume contribution. This experiment preserves the original Forecast and keeps the retrospective exit label out of inference.

Retire this head for execution. Two follow-ups investigated its failure. One exactly removed a negative pulse that the neuron generates on symmetric paths. The other substituted complete volume profiles from five earlier sessions at matching times. Neither produced evidence for promoting today's volume-weighted holding rule. A next design should specify whether an exit forecasts the next few executable minutes or the entire remaining parent trade, then test those horizons separately before assigning economic point units or changing the re-entry policy. The existing prospective reservoir experiment remains separate.

[Symmetry experiment](https://github.com/alex0204360/NQ-profitability-research/tree/research/hold-value-symmetric-20261127/experiments/hold_work) · [Previous-session volume experiment](https://github.com/alex0204360/NQ-profitability-research/tree/research/hold-value-volume-alignment-20261127/experiments/hold_work/alignment_results) · [Frozen protocol](protocol.md) · [Reproduction](reproduction.md) · [Detailed score, uncertainty and paired-trade results](results)
