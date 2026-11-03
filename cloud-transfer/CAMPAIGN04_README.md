# MNQ 100-trial robust-value campaign

This is a frozen, bounded search over 100 distinct student configurations on earlier 2026 observations. The registered ranking gate rejected every trial. No policy was selected or replayed on the internal holdout, and no student replaced the paper-only API. See `campaign04-overlay/docs/CLOUD_CAMPAIGN04_RESULT.md` and the full aggregate trial ledger in `campaign04-summary/results.json`.

After the original transfer and previous overlays have been restored, copy `campaign04-overlay/` into `/workspace/mnq-oracle-code/`. Its runner uses the prior `cloud_robust_teacher.py` from `learning-overlay/`, and refuses to overwrite an existing private run:

```bash
cd /workspace/mnq-oracle-code
/workspace/NQ-profitability-research/.venv/bin/python -m pytest -q tests/test_cloud_campaign04.py
python -c 'from pathlib import Path; from tools.cloud_campaign04 import run; run(Path("/workspace/mnq-private-results/cloud_campaign04_reproduction"))'
```

The completed private run is already at `/workspace/mnq-private-results/cloud_campaign04`. The published ledger contains configurations and aggregate validation scores, no raw bars, teacher rows, or trade journals. Raw 2025 data remained sealed and no broker orders were submitted.
