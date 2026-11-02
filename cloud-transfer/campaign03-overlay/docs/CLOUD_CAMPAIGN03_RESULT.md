# Campaign 03: causal bracket exit on frozen $8 entries

**Reject the bracket exit.** The registered [plan](CLOUD_CAMPAIGN03.json) kept the $8 entry model, coefficient, readiness, signal threshold and execution costs unchanged. It compared fixed ten-bar exits with an existing causal-v2 rule: stop at one ATR, target at 1.5 ATR, and force exit after 30 bars. The rule handles opening gaps conservatively and resolves same-bar stop/target collisions against the position. No model was fitted and no parameter was tuned after seeing results.

| Upload-only window | Exit rule | Immediate stress net | Delayed stress net | Immediate trades | Immediate bar-close drawdown | Immediate session-bootstrap lower net/trade |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| Oct 13–29, 14 sessions | Fixed ten bars | +$196.50 | -$1,250.00 | 133 | $816.50 | -$8.72 |
| Oct 13–29, 14 sessions | ATR bracket, max 30 | -$882.50 | -$1,396.50 | 192 | $1,276.50 | -$10.16 |
| Oct 30–Nov 2, 2 sessions | Fixed ten bars | +$422.00 | +$242.00 | 26 | $271.00 | +$4.07 |
| Oct 30–Nov 2, 2 sessions | ATR bracket, max 30 | -$495.00 | -$292.50 | 46 | $626.00 | -$11.79 |

The later window ends early enough to leave the bracket's 30-bar tail in the source file. For the Oct 13–29 control, all six cost/delay cells reproduced the frozen `fresh02` $8 baseline's trade count, net and drawdown exactly. The bracket traded more often because positions exited earlier, but that did not improve net results or drawdown. It failed the registered screen in both windows and is not retained. The $8 fixed-ten-bar policy remains a comparison baseline, not a qualified winner.

Both windows were inspected before this experiment. The two-upload source conflict, unverified Yahoo contract/roll metadata, small newer sample, lack of prospective paper results, and missing agreed numerical drawdown limit still block qualification. No 2025 raw data was opened and no orders were submitted. The complete protocol, decision/trade/event journals and SHA-256 manifest are private at `/workspace/mnq-private-results/cloud_campaign03`.

The closed evidence now rejects three distinct extensions on these data: two dual-delay value students, one hindsight-trained multi-horizon exit student, and one mechanical bracket exit. More threshold edits on these opened periods would only raise selection bias. The next campaign must use new source-audited observations and a preregistered policy/risk rule; until then, the useful work is prospective paper instrumentation and source verification.
