# Removing the recovered-distance circuit's bias on a fair price path

The first exit circuit penalized price for crossing the same ground twice. Its expected evidence pulse can be negative even when the next move has equally likely signs. The frozen correction subtracts the mean of the two counterfactual pulses at the observed magnitude and pre-bar state. This is causal. A positive output continues to favor holding either a long or a short.

## Mathematical result

For magnitude m, distance g below the prior best close and remaining provisional credit r, the uncentered pulse has conditional mean −¼[min(m,g)+min(m,r)] under sign symmetry. Subtracting that quantity makes the conditional mean zero. The positive entry prior still decays as 0.75 to the age of the position. Enumerating all 4,096 twelve-step fair paths with initial scale two gave 2,380 paths that became eligible. The first circuit stopped 1,815 paths and the corrected circuit stopped 1,632. Each stopping policy earned exactly zero aggregate incremental gross points versus the fixed horizon. This verifies the accounting correction and identifies a source of premature exits on the synthetic process. [Frozen equations](symmetric_protocol.md) · [Exhaustive receipt](results/null.json)

## Exposed market results

Both variants matched all 935 archived original reservoir trades across 100 exposed sessions. On the 40 discovery days, the corrected volume circuit moved next-open fixed-entry net from the original +$452.50 to +$1,204.50 after $6 friction. Its full strategy produced +$194.50. On the 60-session external panel the same full strategy recorded the following net dollars.

| Full external policy | Trades, next open | $3 | $6 | $9 | $6, one extra minute |
|---|---:|---:|---:|---:|---:|
| Original | 541 | −2,198 | −3,821 | −5,444 | −2,734.50 |
| Corrected price | 675 | −1,696.50 | −3,721.50 | −5,746.50 | −2,022.50 |
| Corrected volume | 675 | −1,844 | −3,869 | −5,894 | −2,540 |
| Uncentered volume | 687 | −2,140 | −4,201 | −6,262 | −1,993 |

At next open, centering improved the full volume strategy by $332 against the initial volume circuit, leaving it $48 behind the parent and $147.50 behind the corrected price control. On identical original entries, the corrected volume head produced −$3,260.50 at $6 versus −$3,168 for corrected price. Removing its three largest positive interventions turned the $560.50 fixed-entry improvement over the original into a $572 loss.

On the first eligible discretionary decision in 272 external trades, the mean corrected volume score was +31.13 points versus −0.25 points actually realized by waiting for the original exit. Its rank correlation was −0.102. The extra-minute comparison on 252 trades gave +0.039. Correcting a null-model bias did not recover the magnitude of future holding value or persistent ranking information. There is no independent evidence of tradable economics. [Detailed results and activation logs](results) · [Offline cases](results/hold-value-cases.html)

For the next research context, preserve the symmetric construction as a diagnostic for hand-coded state-dependent payoffs. Retire this specific holding policy. The parent, controls and original prospective evaluation retain their existing definitions. [Original holding experiment and handoff](https://github.com/alex0204360/NQ-profitability-research/tree/research/hold-value-work-balance-20261127/experiments/hold_work) · [Reproduce](reproduction.md)
