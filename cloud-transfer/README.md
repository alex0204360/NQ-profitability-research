# Private MNQ cloud transfer

This branch carries the MNQ research handoff as SHA-256-verified ZIPs split into Git blobs below 500 KB. The latest complete snapshot includes all current code, 2026 training candles, private experiment results, and dashboards. It is a data transfer, not a strategy promotion. The 2025 raw archive is excluded.

In a cloud checkout with Python 3, run:

```bash
python cloud-transfer/restore.py
```

The script restores the latest snapshot when present; older commits retain the original seven-ZIP restore path. It verifies each part's Git blob SHA-1, the complete ZIP's SHA-256 and size, all member hashes, and safe extraction paths. Read `cloud-transfer/LATEST_SESSION_HANDOFF.md` directly in GitHub or `/workspace/outputs/MNQ_LATEST_SESSION_HANDOFF.md` after restoring.

The original fresh confirmation was blocked by two overlapping candle conflicts. The upload-only diagnostic and later rule tests are inspected development evidence; no strategy is ready for live trading. Do not open the sealed 2025 holdout.
