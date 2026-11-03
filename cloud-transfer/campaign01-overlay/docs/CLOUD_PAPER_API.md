# Local research and paper decision API

This service returns proposals from hash-verified local models. It does not connect a feed or broker, submit orders, or establish paper profitability. No campaign 01 student passed its economic screen, so student queries are diagnostic. The $8 gate is available only as an explicit comparison baseline.

From `/workspace/mnq-oracle-code`, with the prepared Python 3.12 environment:

```sh
python -m tools.paper_decision_service \
  --root /workspace/mnq-private-results/cloud_campaign01_retry2 \
  --student extra_trees_dual_delay \
  --journal /workspace/mnq-private-results/paper_events.jsonl \
  --port 8765
```

The service binds only to `127.0.0.1`. `GET /health` reports paper-only status. `POST /decide` accepts an envelope with `source_id`, `data_sha256`, and `observation`. The observation must contain `available_at` (aware UTC or offset timestamp for a completed bar), boolean `ready`, and exactly the 18 causal features in `tools/opportunity_research.py::FEATURES`. The caller must construct those fields from the verified causal state adapter. `data_sha256` identifies the caller's feed artifact; the service records it but cannot independently validate the feed from that claim. Do not include target, future, or teacher fields.

The response contains a proposed action, reason, model hashes, both predicted gross values for student models, observed state age and decision computation time. States older than 120 seconds, future states, and repeated or out-of-order timestamps for the same source are rejected and journaled. The journal survives process restart. It contains private state hashes and decision records; keep it local. `POST /next-open` can attach the next observed open to a pending paper entry after that bar completes. This is a reference price, not a verified exchange fill or broker execution. No exit simulator or realized paper P&L is claimed by this endpoint.

For a caller that supplies an append-only normalized MNQ CSV, `tools.cloud_paper_feed` builds the existing causal state itself and calls the same recorder. Run it after each new bar has completed, with the same arguments and files each time:

```sh
python -m tools.cloud_paper_feed \
  --history-csv /workspace/mnq-private-results/paper_feed.csv \
  --feed-state /workspace/mnq-private-results/paper_feed_state.json \
  --journal /workspace/mnq-private-results/paper_events.jsonl \
  --source-id audited-mnq-feed-1 \
  --run /workspace/mnq-private-results/cloud_campaign01_retry2 \
  --student extra_trees_dual_delay
```

The CSV header must be `timestamp_utc,open,high,low,close,volume`. Rows must be unique, ordered, tick-aligned 2026 bars from October 30 onward. The file needs at least 61 same-source bars; each subsequent call requires exactly one appended row and verifies every earlier row against the saved prefix. The latest completed bar must arrive within 120 seconds. A pending paper proposal gets its next observed open reference when the following bar completes. If that bar is missing, the recorder writes a `paper_gap_unresolved` incident, credits no fill, and blocks further decisions for that source until an operator reviews it and starts a new audited source identity. This is a recorder for a feed supplied by the caller; it does not authenticate a source's contract or roll metadata. It cannot infer real fills, order queue position, transaction fees or exits.

For an explicit historical baseline query, launch with `--root /workspace/mnq-private-results --family hist_gradient_boosting --fold fold3 --gate 8` and a separate journal path. Baseline selection does not qualify it for paper promotion. The frozen incumbent uses the same model with gate 10; neither gate passed the fresh transfer screen.

To reproduce the development research, run `tools.cloud_campaign01.run` with a new empty output directory. The registered plan is `docs/CLOUD_CAMPAIGN01.json`; results and manifest are under `/workspace/mnq-private-results/cloud_campaign01_retry2`; the HTML dashboard is `/workspace/outputs/mnq_cloud_campaign01.html`. The two first-attempt records remain as `cloud_campaign01` (pre-fit failure) and `cloud_campaign01_retry1` (completed rerun). Keep 2025 sealed and do not overwrite any historical run.
