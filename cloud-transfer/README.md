# Private MNQ cloud transfer

This branch carries the existing MNQ research handoff as seven SHA-256-verified ZIPs split into Git blobs below 500 KB. It is a data transfer, not a strategy promotion. The 2025 raw archive is excluded.

In a cloud checkout with Python 3, run:

```bash
python cloud-transfer/restore.py
```

The script verifies each part's Git blob SHA-1, the complete ZIP's SHA-256 and size, guards against ZIP path traversal, and extracts under `/workspace`. Read `/workspace/outputs/MNQ_CLOUD_TRANSFER_README.md` and `/workspace/outputs/MNQ_FRESH_TRANSFER_HANDOFF.md` afterward.

The original fresh confirmation was blocked by two overlapping candle conflicts. The upload-only diagnostic and later rule tests are inspected development evidence; no strategy is ready for live trading. Do not open the sealed 2025 holdout.
