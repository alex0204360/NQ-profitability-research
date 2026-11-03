# MNQ learning failure audit and robust teacher targets

The aggregate diagnostic in `learning-summary/mnq_learning_diagnostic.json` shows that the two frozen ten-bar action-value students did not rank realized opportunities on the opened October 13–29 upload. The reusable audit and a gap-aware, matured dual-delay teacher target builder are in `learning-overlay/`.

After restoring the original transfer and prior overlays, copy `learning-overlay/` into `/workspace/mnq-oracle-code/` and run:

```bash
cd /workspace/mnq-oracle-code
python -m tools.cloud_learning_diagnostic
/workspace/NQ-profitability-research/.venv/bin/python -m pytest -q tests/test_cloud_learning_diagnostic.py tests/test_cloud_robust_teacher.py
```

The audit verifies frozen private hashes and writes only aggregate results to `/workspace/outputs/mnq_learning_diagnostic.json`. The teaching target builder keeps long and short outcomes for both fill timings, including losses; its hindsight class is never a live feature. The detailed result and next training gate are in `learning-overlay/docs/CLOUD_LEARNING_DIAGNOSTIC.md`. No new profitable student or live strategy is claimed. No broker orders were submitted and raw 2025 data remains sealed.
