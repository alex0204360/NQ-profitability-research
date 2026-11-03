# Campaign 07: is the $8 gate still the best candidate?

**The $8 gate remains the highest stressed immediate net among the tested policies on the 14-session October 13–29 upload, but none qualifies for live trading.** The [comparison dashboard](/workspace/outputs/mnq_gate8_comparison.html) puts the major candidates on identical source windows. The unchanged $8 gate made **+$196.50** over 133 filled trades immediately and **-$1,250** with a one-bar signal delay. The causal replay reproduced its frozen trade count and net exactly under every cost and delay setting before the new candidate was scored.

The registered [plan](CLOUD_CAMPAIGN07.json) tested one outside-the-box combination: keep the frozen $8 signal only if the already defined human-style support/resistance or confirmed trendline retest gave the same direction on one of the last three contiguous completed bars. The forecast model, $8 threshold, ten-bar exit, fills, and costs did not change.

| Upload window | Gate signals → confirmed signals | Filled confluence trades | Confluence stressed net immediate / delayed | Unchanged $8 gate stressed net immediate / delayed |
| --- | ---: | ---: | ---: | ---: |
| October 13–29, 14 sessions | 455 → 6 | 2 | +$91 / +$50 | +$196.50 / -$1,250 |
| October 30–November 2, 2 sessions | 133 → 4 | 2 | +$107 / +$77.50 | +$429 / +$259.50 |

The combination appeared more stable under a one-bar delay in the older window, but its two trades occurred on only two active sessions there and on one active session in the newer window. It failed the registered minimum of 50 trades and ten active sessions, and it did not beat the $8 gate's total immediate profit on either window. Neither confluence window had gap-exit trades. The positive nets are descriptive, not evidence of a reliable edge; widening the three-bar filter now would select on already opened outcomes.

The newer tree and multi-horizon students reported larger immediate nets of +$1,091 and +$1,379, respectively, but those totals depended on unverifiable exits after missing bars. Sensitivity calculations without the gap-exit trades are **-$1,556** and **-$1,542**. The ungated human chart rule made +$480 on the newer two-session upload but lost $511.50 on the older 14-session upload. The $8 gate therefore remains the most defensible *baseline for comparison*, not a production-ready strategy.

All windows have been inspected in prior campaigns, the Yahoo-labeled feed still lacks independently verified contract/roll and minute convention, and the user has specified no finite maximum drawdown. The next way to improve is a pre-frozen policy tested on new source-audited observations with enough trades and sessions, or genuinely new causal data with historical/live API parity. Raw 2025 remained sealed; no broker was connected and no orders were sent.
