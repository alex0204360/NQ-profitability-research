# MNQ support/resistance and trendline chart experiment

The fixed human-style chart rules use confirmed horizontal levels, causal two-pivot trendlines, EMA trend, and completed-candle retests. A payoff-aware Beta posterior learned only from earlier mature observations gates entries. No setup passed that conservative gate, so the primary policy made zero trades. The ungated raw control made +$317.50 on the original eight-session source and +$480 on the newer two-session upload, but lost $511.50 on the 14-session October upload under immediate stressed fills.

Open `campaign06-summary/mnq_human_chart_dashboard.html` for the aggregate dashboard and `campaign06-summary/mnq_human_chart_summary.json` for the full cost/delay matrix. A local private dashboard at `/workspace/outputs/mnq_human_chart_dashboard_PRIVATE.html` embeds `/workspace/outputs/mnq_human_chart_PRIVATE.png`, an actual October 13 level-retest chart with a raw short trade that lost $95. The private price graph and row-level journals stay outside Git.

After restoring earlier overlays, copy `campaign06-overlay/` into `/workspace/mnq-oracle-code/`. The frozen completed run is `/workspace/mnq-private-results/cloud_campaign06`. To regenerate aggregate dashboards from its hash-verified artifacts, run `python -m tools.cloud_campaign06_report` there. `python -m tools.cloud_campaign06` refuses to overwrite the completed private run; use a new output directory for reproduction.

The method and limitations are in `campaign06-overlay/docs/CLOUD_CAMPAIGN06_RESULT.md`. All windows were already opened development data, Yahoo contract/roll identity is unverified, and no policy qualified for live trading. Raw 2025 remained sealed; no broker orders were sent.
