# V2 preregistered profit-policy study

Status: frozen before V2 code. Date: 2026-09-09 UTC. Research, not an execution system.

## Question and lessons

Can a causal pattern-conditioned policy choose direction, take profit (TP), stop loss
(SL), and a holding cap of 1–45 minutes with positive modeled net expectancy and
better daily P&L than a comparable pattern-free policy on unused history?

[V1](https://github.com/alex0204360/NQ-trading-sept), final commit
`731607099729bdc1e3151b767a695e5c86aea503`, tested 45,360 directional hypotheses.
None passed its screening rules; no bootstrap shortlist or held-out outcome test
ran. That is not a profitability experiment. Sparse baseline strata, small pattern
samples, and inadequate directional lift motivated this different question. V1
remains unchanged. V2 may also find no qualifying policy. A larger target or a
higher TP hit rate alone is not the objective.

## Workflow and provenance

Follow [ECC](https://github.com/affaan-m/ECC) at
`e04ea0b9cc8248686edf5ac751cadff550e162b8`: root AGENTS, planner, plan command,
development/git workflow, search-first, TDD, verification-loop and plan-orchestrate.
Read/research, publish this plan, write failing tests, implement, independently
review, verify, publish incremental results. No V2 production or test code before
this document is committed and its commit verified on GitHub. Use descriptive
commits and update CHANGELOG and append-only history for stages and failures.
Verify at least 80% overall line and branch coverage, lint, build, and a runnable
standard-OHLCV example. Coverage is an engineering check, not financial evidence.

Root owns integration, data orchestration, publication and reports. The
`v2_protocol_review` agent reviewed this protocol before code and requested
conservative ambiguous fills, action feasibility before ranking, shared zero-trade
dates, policy-level inference, and explicit missing-execution treatment. Subsequent
component agents own bounded artifacts, recorded in history. Failed agents or
candidates are logged; remaining work continues. User authorization already covers
the project, agents, and publication; no additional plan-approval pause is needed.

## Data and chronology

Reuse V1's audited local acquisition of Kaggle
`tgtanalytics/nq-futures-1min-bar-2022-2025`, version 1. Raw SHA256:
`1577e60a7feab411e49da7a56c7052a64738cd1757cfd60aa11fd783ff43b60b`.
Reproduce acquisition from its pinned pipeline; preserve source-row IDs, quality
reports, and every documented exclusion. No raw data or credentials in Git.

Training has 706,008 canonical bars, strictly before 2025-01-01 00:00 America/New_York
(05:00 UTC); holdout has 330,516 bars at/after that fixed boundary. Initial fit ends
before 2023-04-01 ET. Four expanding-fit validation periods use ET boundaries
2023-04-01, 2023-07-01, 2024-01-01, 2024-07-01, 2025-01-01. Remove fit detection
rows in the 45 elapsed minutes before each validation boundary and require all fit
labels inside the fit period. Features require the current and 60 previous
consecutive completed bars. Gaps, contract changes, and audited segment changes
reset history. No future labels, global-fitted scales, or future pivots in features.

V1 mechanically audited/split 2025 but never evaluated its outcomes. V2 does not
read holdout prices/features/outcomes until one terminal frozen evaluation, and
only if at least one policy survives training. Source metadata may be read now.
Publisher ET timezone is documented; conversion from inferred bar-end timestamps
to canonical interval-start timestamps is not publisher verified. Continuous
contract construction/roll details and historical calendar correctness are not
independently verified. Calendar reconciliation quarantined 12,051 rows and
identified 4,146 expected missing minutes; 83 extreme-move flags were retained.
These inherited uncertainties persist even if statistical gates pass.

## Actions and executable outcome model

Freeze 1,080 actions: directions long/short × TP ATR14 multiples {0.5,1,2,3} × SL
ATR14 multiples {0.5,1,2} × every integer H from 1 to 45 inclusive. ATR is the
arithmetic mean of 14 completed true ranges at detection, using V1 causal features.
Distances are rounded half-up to the nearest 0.25 point, minimum one tick. Reject
invalid windows, including >45, as `rejected — out of scope`; do not evaluate them.
No horizon is chosen after observing its result.

Decision time is the close of a completed bar. Candidate opportunities occur on a
UTC five-minute clock (the close timestamp minute divisible by five). Enter at
the next consecutive bar's open with a single contract, fixed TP/SL offsets, and
no pyramiding or compounding. Check the entry bar through the H-th future bar.
Check the open first: an adverse stop gap fills at that worse opening price; a
favorable target gap fills at the target. If high/low touch both barriers on an
otherwise unresolved bar, book the stop and record ambiguity. A single touched
barrier fills at its level. Otherwise exit at the H-th bar's close and report a
timeout, with its actual signed payoff. H bars means no more than H elapsed
minutes; a gap never extends the holding cap. Trade direction, quantized offsets,
H, gross/net points, exit reason, and actual bars to resolution are recorded.

One position at a time per policy, freed at the next decision clock after its
observed exit; a decision at the exit bar's close is allowed. Known scheduled
closures filter infeasible actions BEFORE argmax, so shorter feasible actions may
trade near a close. The frozen schedule is information assumed known at detection,
not inferred from future missing observations. Do not filter evaluation decisions
using future completeness. An observed exit remains priced if a later gap precedes
its unused timeout. If an open trade encounters an unexpected gap, segment/contract
change, or missing required entry, mark the attempted execution censored and occupy
the planned H minutes conservatively. Report decisions, attempts, priced trades,
censored trades and coverage. Qualification requires zero censored attempts;
conditional observable-trade results can still be reported, never promoted as
complete strategy P&L. Study boundaries require the planned exit within the period.

Primary NQ round-trip friction is 1.0 point per trade; stress is 2.0 points. MNQ
transfer scenarios are 1.5 and 2.5 points on NQ price paths. These are explicit
assumptions covering fees/slippage, not quotes from a broker. Barriers use reference
prices; subtract friction from each realized trade once. Report points and dollar
equivalents (NQ $20/point, MNQ $2/point), not account returns without capital.
MNQ results are proxies, not validation on MNQ transactions. No guaranteed fills,
TP hits, or profitability claims. No live feed, orders, leverage or position sizing.

## Policy learning and tournament

Fit payoff tables on the same common cohort of causal five-minute opportunities
with 45 consecutive future bars and 45 minutes of scheduled feasibility, including
all 1,080 actions. This makes fit-action comparisons share observations. Evaluation
only requires observation through the chosen action's actual exit; this can include
near-close opportunities absent from fitting, an explicit population shift.

For each state and action compute net mean m_s and the global same-action mean m_g.
Use w=n_s/(n_s+200), shrunk prediction w*m_s+(1-w)*m_g. Compute day-cluster SE for
each mean: sqrt(D/(D-1) * sum_d (sum_d y - n_d*m)^2)/n, with D represented ET
dates and all outcomes for that state/day grouped together. Use conservative
combined SE w*SE_s+(1-w)*SE_g; the ranking score is shrunk mean minus that SE.
State support must reach 200 opportunities and 20 ET dates; otherwise no trade for
that state. Global benchmark requires the same support and uses m_g-SE_g. No
trade has score zero. Choose the highest strictly positive feasible action score;
ties prefer shorter H, smaller SL multiple, smaller TP multiple, then long before
short. This heuristic is not a prediction confidence interval. No action-size
reward, future maximum-favorable-excursion target, or forced trade.

Exactly two rounds, two distinct approaches per round, four policy hypotheses:

1. `regime8`: RTH (09:30–16:00 ET close time) versus other times × trend20_60
   nonnegative/negative × ATR14/close above/below initial-fit median. `prototype8`:
   KMeans eight prototypes on the feature vector below.
2. `regime16`: ET close-time buckets [00:00,06:00), [06:00,09:30), [09:30,16:00),
   [16:00,24:00) × the same trend/volatility flags. `prototype16`: sixteen
   prototypes on the identical vector. This prespecified refinement increases
   state resolution; no outcome-guided new families in this study.

Prototype vector: price_z20, trend20_60, body_fraction, upper_wick_fraction,
lower_wick_fraction, lag1_return_to_range, range_to_atr14, volume_z20, range_z20,
position60. Fit StandardScaler and KMeans on valid initial-fit
five-minute opportunities only (StandardScaler uses arithmetic mean and population
standard deviation; no median centering). KMeans random_state=20260909, n_init=10,
algorithm=lloyd, max_iter=300, one computational thread. Freeze these artifacts and
the regime volatility median for every subsequent fold and holdout. Payoff tables
alone refit on expanding past data for each fold. The evaluated object is the
learning procedure, not a fixed state/action with all pooled observations called
independent. The final matcher model refits its payoff table on all training only.

The pattern-free baseline learns one global action table on the same past data,
costs, decision times, feasibility and occupancy rules, with abstention permitted.
It is descriptive outside the four-policy testing family. Compare whole-policy
daily P&L using shared dates, not sparse fine-grained control strata.

## Statistical gates and exact stopping rules

Policy reports include count, distinct dates/weeks, TP/SL/timeout/ambiguous/censored
counts, positive-net trade rate and descriptive Wilson 95% interval, TP hit rate,
mean/total net points, modeled profit factor, closed-trade drawdown, gross/net
cost sensitivities, and resolution mean, median, p10/p25/p75/p90/max and histogram
for all priced trades and each exit reason. Wilson intervals are descriptive and
do not provide dependent-trade significance. Qualification is policy-level, not
an assertion that every state or selected trade is profitable. State/action
breakdowns with n<30 are explicitly low-confidence.

Training screening: >=300 priced nonoverlapping trades total; >=30 in each of four
folds; >=90 represented ET entry dates; zero censored attempts; positive total net
P&L in >=3/4 folds; pooled primary mean >=0.25 NQ point/trade; stress mean >=0.
For screened policies, 9,999 joint moving-block bootstrap draws with both 5-day
and 20-day blocks, resampling within folds without mixing fit periods. Include all
ET calendar dates within each evaluation period, including zero-trade dates, in
policy and benchmark paired arrays. Resample total daily P&L and trade counts
together for mean/trade and paired daily P&L difference. Require two-sided 95%
percentile lower bounds >0 for both mean net/trade and mean daily advantage under
both block lengths. Stable seed 20260909 plus documented deterministic policy/
period offsets. Report screen failures; do not run expensive inference on failures.

After round 2 freeze all training survivors (up to four), their exact model/data/
code hashes, the baseline, and these gates in GitHub BEFORE any held-out outcomes.
Holdout qualification: >=200 priced trades, >=60 dates, >=26 ISO entry weeks,
zero censored attempts, primary mean >=0.25 point/trade, stress mean >=0; use
99,999 joint bootstrap draws with both block lengths and require both lower bounds
>0. For each policy take the MAX of the four centered, one-sided, plus-one p-values
(absolute mean and paired daily advantage, each under both block lengths). Apply
Holm familywise correction at 0.05 across the frozen survivor family; screen
failures have p=1 and remain in that family. Zero denominators in resamples give
non-supporting mean estimates. No replacing failures or tuning after holdout.
Intervals are marginal, not simultaneous intervals. Joint resampling is paired.

Stop on any of: (a) two completed rounds (fixed budget, four policies), (b) round 2
improves best screened pooled daily advantage by <0.10 NQ point/calendar day over
round 1 (no screened library has quality 0, quality floored at 0), or (c) terminal
heldout quality gate reaches >=1 policy passing all the gates above. For clarity,
there is no interim heldout access and (c) is terminal only. Log all applicable
stop reasons and primary reason fixed_round_budget when (a) also holds. A failed
candidate still counts as attempted and is not replaced. No survivors means empty
qualified library and logged skipped Stage 2, with holdout still unopened. Metadata
uncertainty separately blocks claims of exchange-verified or live profitability.

## Deliverables and tests

Separate GitHub project with this plan, CHANGELOG, agent/stage/candidate JSONL
history, immutable round reports, all failed policies/reasons, final structured
qualified library (possibly empty), diagnostic models clearly marked unqualified,
frozen validation report, and README giving actual numbers and stop reasons.
Feed-agnostic Python matcher accepts standard timezone-aware completed one-minute
OHLCV bars, optional contract/segment IDs, and optional known-close time; outputs
abstention or policy ID, direction, TP/SL offsets, H, forecast and historical policy
stats. It never marks a diagnostic policy qualified. Absolute barrier prices are
established at the next open, not predicted as a known fill. A rolling buffer must
match batch features. Default qualified-only behavior yields no trade for an empty
library; explicit diagnostic mode can test the mechanics. No TradingView/Pine,
broker adapter, live data connection, or Stage 3 forward check.

Test-first execution cases include long/short profits/losses, opening gaps,
intrabar ambiguity, exact H=1/45, >45 rejection, partial observation, calendar
filtering before ranking, closed-before-gap trades, cost subtraction, occupancy,
causal/prefix parity, payoff shrinkage/support/abstention, paired block inference,
frozen holdout access and default qualified-only matching. Reuse V1 tested causal
features and pipeline with attribution after this plan is published. Record actual
test/lint/build evidence and independent review, never imply fixtures prove profit.

## Primary references

- [CME NQ specifications](https://www.cmegroup.com/markets/equities/nasdaq/e-mini-nasdaq-100.contractSpecs.html)
- [CME MNQ specifications](https://www.cmegroup.com/markets/equities/nasdaq/micro-e-mini-nasdaq-100.contractSpecs.html)
- [Dataset publisher](https://www.kaggle.com/datasets/tgtanalytics/nq-futures-1min-bar-2022-2025/data)
- [scikit-learn KMeans](https://scikit-learn.org/stable/modules/generated/sklearn.cluster.KMeans.html)

All gates above are preregistered design choices, not literature-guaranteed
profitability thresholds. Any necessary correction is logged and published before
affected data are evaluated; no silent rule changes.
