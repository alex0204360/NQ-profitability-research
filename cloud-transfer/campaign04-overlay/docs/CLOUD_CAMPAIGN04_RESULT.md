# Campaign 04: 100 robust-teacher student trials

**Reject all 100 configurations.** The fixed [plan](CLOUD_CAMPAIGN04.json) trained exactly 100 unique extra-trees students on earlier 2026 causal features, using long and short net targets that include stressed costs and the worse of immediate and one-bar-delayed fills. Three purged chronological validation folds selected by rank correlation, not replay profit. No trial passed the predeclared requirement that every fold score be positive and the mean exceed 0.05. No model was selected, no holdout replay was run, and no new student was promoted to the paper API.

| Check | Result |
| --- | ---: |
| Registered and completed trials | 100 / 100 |
| Mean trial score, median | 0.0244 |
| Best mean trial score | 0.0428 |
| Trials positive in all three folds | 1 |
| Trials meeting the full selection gate | 0 |
| Fold median rank scores | +0.0586, **-0.0362**, +0.0557 |
| Trials with a positive second-fold score | 1 / 100 |

The best trial scored +0.0825, -0.0306, and +0.0765 across the three folds. The common failure on September 24–27 suggests unstable price relationships or a source/regime mismatch; these data cannot identify which. Choosing a model because it happened to profit in the already opened October/November windows would conceal this instability. The October 1–6 internal holdout was deliberately left unused after the ranking gate failed.

The next useful learning iteration needs **new information**, not another 100 variations of the same 18 minute-bar features. Contract-specific, timestamped market-depth or order-flow data and an event calendar known at decision time are hypotheses to test, with a historical/live API that constructs identical features. [DeepLOB](https://arxiv.org/abs/1808.03668) studies limit-order-book prediction on cash equities; it motivates testing such features but does not establish an MNQ edge. [CME's market-data overview](https://www.cmegroup.com/market-data.html) describes available data products. The Yahoo upload does not independently identify the MNQ contract, roll, or minute convention, so source reconciliation is a prerequisite to confirmation.

This run used no raw 2025 data and submitted no broker orders. It does not improve validated profitability. Existing $8-gate and gap-audit limitations still apply. New source-audited, post-freeze observations and an agreed finite live loss budget remain necessary for production qualification; the user has specified no numerical maximum drawdown.
