# Inspecting the multi-horizon student's decisions

The campaign 02 student **failed** development evaluation. This interface is for research and paper-only diagnostics; it does not authorize a trade, connect a broker, or calculate realized account P&L.

An observation is JSON with exactly `available_at`, `ready`, and `features`. `available_at` is a timezone-aware completed-bar availability timestamp. `features` contains exactly the 18 existing causal game-state values in `tools/opportunity_research.py::FEATURES`; there are no future prices, hindsight teacher labels or outcomes. The caller must construct and validate those fields from completed bars using the shared state adapter. Historical query:

```sh
python -m tools.cloud_exit_student_decision_api \
  --run /workspace/mnq-private-results/cloud_campaign02 \
  --observation /workspace/PRIVATE_OBSERVATION.json
```

The response lists expected gross MNQ dollars for next-open and one-bar-delayed fills at 3, 5, 10 and 20 bars, the action, planned horizon, minimum predicted stressed net, reason and artifact hashes. The estimates are uncalibrated and failed the registered test; the reported horizon is not a trustworthy profit forecast.

For a local paper-only HTTP query and append-only journal, start `tools.paper_decision_service` with `--root /workspace/mnq-private-results/cloud_campaign02 --exit-student --journal /workspace/mnq-private-results/campaign02_paper_events.jsonl --port 8765`. `GET /health` and `POST /decide` use the same envelope described in [CLOUD_PAPER_API.md](CLOUD_PAPER_API.md). The service rejects stale, future, repeated and out-of-order states. The CSV adapter can use `--exit-student` instead of `--student`, with `--run /workspace/mnq-private-results/cloud_campaign02`. Its source file must grow append-only. A proposed exit is not an exchange fill; actual feed timing, costs and exits still need prospective measurement.
