# MNQ cloud campaign 01 overlay

This branch keeps the original transfer archives intact. After `python cloud-transfer/restore.py`, copy the files under `cloud-transfer/campaign01-overlay/` into `/workspace/mnq-oracle-code/`, preserving their `tools/`, `tests/`, and `docs/` paths. The overlay contains only source, tests, a registered plan, and a narrative result; private market rows, model bundles, trade journals, and event journals remain outside Git.

The completed canonical local run is `/workspace/mnq-private-results/cloud_campaign01_retry2`. `cloud-transfer/campaign01-summary/` contains a public-facing HTML dashboard and machine-readable aggregate summary generated from that run. If restoring in a new workspace, rerun the campaign into a **new empty directory** before regenerating the dashboard. From `/workspace/mnq-oracle-code` with the Python 3.12 dependencies installed:

```sh
python -c 'from tools.cloud_campaign01 import run; run("/workspace/mnq-private-results/NEW_EMPTY_RUN")'
python -m pytest -q tests/test_cloud_campaign01.py tests/test_paper_decision_service.py tests/test_cloud_paper_feed.py
```

The campaign runner and plan were copied byte-for-byte from the canonical run workspace. The run's `source_hashes.json` binds its student runner, plan, causal replay, and shared-state adapter. The model bundles and journal files are not on this Git branch. The paper CSV adapter in the overlay was added afterward; it has its own tests and has not processed a real feed. The dashboard remains descriptive development evidence; no strategy passed confirmation or prospective paper operation. Keep 2025 sealed. Do not rerun historical `fresh02` or `gate8_iteration01` in place.
