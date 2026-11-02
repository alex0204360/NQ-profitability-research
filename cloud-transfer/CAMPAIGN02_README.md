# MNQ campaign 02: hindsight targets, causal decisions

The one-fit exit-learning experiment is registered in `campaign02-overlay/docs/CLOUD_CAMPAIGN02.json`. It uses only the transferred 2026 bars and frozen upload artifacts; raw 2025 stays sealed. The teacher constructs future-derived value **targets** for all opportunities at four holding horizons and two fill timings. The student receives only the existing 18 causal features. A separate causal-v3 replay freezes the chosen horizon at signal time. The old causal-v2 source and historical runs remain unchanged.

After restoring the original transfer and both prior overlays, copy `cloud-transfer/campaign02-overlay/` into `/workspace/mnq-oracle-code/` preserving paths. Run with the Python 3.12 research dependencies and a new empty output directory:

```sh
python -c 'from tools.cloud_campaign02 import run; run("/workspace/mnq-private-results/NEW_EMPTY_RUN")'
python -m pytest -q tests/test_causal_execution_v3.py tests/test_cloud_campaign02.py
```

The canonical local run is `/workspace/mnq-private-results/cloud_campaign02`, with a source-hash receipt, model bundle, decisions, trade and event journals, and SHA-256 manifest. Private artifacts are not committed here. Aggregate HTML and JSON are in `campaign02-summary/`; the [research result](campaign02-overlay/docs/CLOUD_CAMPAIGN02_RESULT.md) gives the decision and limits. The student lost on the 14-session development window and remains rejected. `campaign02-overlay/docs/CLOUD_EXIT_API.md` describes research and paper-only queries. The updated paper service and CSV adapter files in `campaign01-overlay/` can log these queries, but no feed was connected and no orders were placed.
