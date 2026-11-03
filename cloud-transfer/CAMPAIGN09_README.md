# Campaign 09: causal path representation

The fixed campaign tested whether an unsupervised 32-minute price/volume path adds predictive information to the existing 18-feature Ridge student. It did not pass its preregistered rank or economic screens. The path student lost $109.50 immediate and $128.50 delayed under stressed costs on the 14-session October upload; the unchanged $8 gate made $196.50 immediate and lost $1,250 delayed. This is a rejected development result, not a production strategy.

The dashboard and aggregate results are `campaign09-summary/mnq_path_representation_dashboard.html` and `campaign09-summary/mnq_path_representation_summary.json`. Reproducible protocol, runner, report, tests, result notes, and backlog are in `campaign09-overlay/`. After restoring prior overlays, copy the overlay into `/workspace/mnq-oracle-code/`. The original runner directory `cloud_campaign09` records a pre-fit protocol-key failure; the corrected immutable private run is `cloud_campaign09_retry1`. The public report can be regenerated with `python -m tools.cloud_campaign09_report` when that private run is available.

The $8 gate remains the comparison baseline. Raw 2025 stayed sealed. The Yahoo-labeled feed's contract and roll identity remain unverified, and no broker orders were sent.
