# Campaign 02: learned exits from hindsight targets

**Reject the student.** The registered [plan](CLOUD_CAMPAIGN02.json) allowed one fit. It trained a multi-output extra-trees model on 19,912 matured, pre-October 7 opportunities. For every opportunity, future prices supplied eight training targets: next-open and one-bar-delayed gross MNQ value at holding horizons of 3, 5, 10 and 20 bars. All losing alternatives stayed in the training set. Hindsight outcomes were labels only; the 18 model inputs were the existing causal game state. The policy chose a direction and horizon only when both predicted fill timings cleared $6 stressed cost. The new causal-v3 replay freezes that horizon at signal time and matched the frozen causal-v2 replay for ten-bar controls in tests.

| Development window | Active sessions | Stress net, immediate | Stress net, delayed | Stress lower net/trade, immediate | Immediate drawdown |
| --- | ---: | ---: | ---: | ---: | ---: |
| Original Oct 8–12 | 3 | -$940.50 | -$1,025.50 | -$44.66 | $1,479.00 |
| Upload-only Oct 13–29 | 14 | -$4,385.50 | -$4,030.50 | -$21.89 | $5,938.00 |
| Upload-only Oct 30–Nov 2 | 2 | +$1,379.00 | -$1,349.50 | -$33.46 | $1,173.50 |

On the only window with at least ten sessions, this loses far more than the unchanged $8 gate (+$196.50 immediate stress, -$1,250 delayed stress). The newer two-session immediate gain depends on a few exceptional trades: the five best contributed $3,383 while total stressed net was $1,379; the median executed trade lost $18. It turned into a delayed loss. The 20-bar horizon was chosen for 4,320 of 4,322 active signals in the October 13–29 window, so the attempted exit learner largely collapsed to a long fixed hold. No calibrated uncertainty or repeatable advantage was established.

The teacher's hindsight choice is noncausal and cannot be used directly in the live decision API. The student's actual causal predictions and reason codes can be queried through `tools.cloud_exit_student_decision_api`; it reports all horizon values, the chosen action and holding window, model hashes, and `live_authorized: false`. This makes decisions inspectable but does not qualify them for trading.

This is another exploratory campaign on already inspected development periods. There is no untouched confirmation, prospective paper result, verified contract/roll source, or agreed maximum drawdown. Raw 2025 remains sealed. No broker was connected and no orders were placed. The poor cross-period performance rules out further threshold mutations on these opened samples. The next research opportunity is a new source-audited post-freeze cohort, with a preregistered decision rule and explicit risk policy before outcomes are opened.

External references checked during design: [CME MNQ contract specifications](https://www.cmegroup.com/markets/equities/nasdaq/micro-e-mini-nasdaq-100.contractSpecs.html) give $2 per index point and a 0.25-point tick; [scikit-learn time-series validation guidance](https://scikit-learn.org/stable/modules/cross_validation.html#time-series-split) explains why chronological separation and gaps matter. Neither reference validates the Yahoo CSV's contract or fill quality.
